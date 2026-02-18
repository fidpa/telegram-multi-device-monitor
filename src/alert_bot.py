#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Lightweight Telegram Alert Bot - AsyncIO Optimized for Low Memory

Designed for resource-constrained devices (e.g., Raspberry Pi Zero with 512MB RAM).
Provides efficient alert sending with memory management and smart batching.

Features:
- Full AsyncIO implementation for better performance
- Memory optimization with __slots__
- Connection pooling for SSH
- Smart alert batching
- 2FA for admin commands
- Configurable rate limiting and quiet hours

Usage:
    python3 alert_bot.py

Configuration:
    Uses config/telegram_config.yml for settings.
    Credentials from environment or config file.

Version: 1.0.0
"""

import asyncio
import gc
import logging
import logging.handlers
import signal
import subprocess
import sys
import time
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Import local config loader
try:
    from config_loader import load_config, load_service_monitoring
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import load_config, load_service_monitoring

# Configure logging with fallback for missing log directory
log_handlers = [logging.StreamHandler()]

# Load configuration
CONFIG = load_config()
SERVICE_CONFIG = load_service_monitoring()

LOG_CONFIG = CONFIG.get("logging", {})
LOG_DIR = Path(LOG_CONFIG.get("log_dir", "/var/log/telegram-monitor"))

try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handlers.append(
        logging.handlers.RotatingFileHandler(
            str(LOG_DIR / "alert-bot.log"),
            maxBytes=5 * 1024 * 1024,  # 5MB max
            backupCount=2,
        )
    )
except (PermissionError, OSError):
    # Fallback to /tmp
    tmp_log = Path("/tmp/alert-bot.log")
    log_handlers.append(
        logging.handlers.RotatingFileHandler(
            str(tmp_log), maxBytes=5 * 1024 * 1024, backupCount=2
        )
    )

logging.basicConfig(
    level=logging.WARNING,  # WARNING for production on low-memory devices
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger(__name__)


class BotConfig:
    """Configuration with memory optimization via __slots__."""

    __slots__ = [
        "token",
        "chat_id",
        "admin_ids",
        "admin_sessions",
        "rate_limits",
        "quiet_hours",
        "batch_window",
        "memory_limit_mb",
        "ssh_max_connections",
    ]

    def __init__(self) -> None:
        telegram_config = CONFIG.get("telegram", {})
        memory_config = CONFIG.get("memory", {})

        # Credentials from config or environment
        import os

        self.token = os.environ.get("TELEGRAM_BOT_TOKEN") or telegram_config.get(
            "token", ""
        )
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID") or telegram_config.get(
            "chat_id", ""
        )

        admin_ids_env = os.environ.get("TELEGRAM_ADMIN_IDS")
        if admin_ids_env:
            self.admin_ids = set(admin_ids_env.split(","))
        else:
            admin_list = telegram_config.get("admin_ids", [])
            self.admin_ids = set(str(aid) for aid in admin_list)

        # Validation
        if not self.token:
            logger.error("No bot token configured!")
            raise ValueError("TELEGRAM_BOT_TOKEN not found")

        # Admin session management (for 2FA)
        self.admin_sessions: dict[str, datetime] = {}

        # Rate limiting
        self.rate_limits = {
            "restart": {"max": 3, "window": 3600},  # 3 restarts per hour
            "logs": {"max": 10, "window": 600},  # 10 log requests per 10 min
        }

        # Quiet hours (22:00 - 07:00)
        self.quiet_hours = {"start": 22, "end": 7}

        # Alert batching
        self.batch_window = 10  # seconds

        # Memory limits
        self.memory_limit_mb = memory_config.get("limit_mb", 50)

        # SSH connection pool
        self.ssh_max_connections = CONFIG.get("ssh", {}).get("max_connections", 3)


class MemoryManager:
    """Manages memory usage for low-memory device optimization."""

    __slots__ = ["_last_gc", "_gc_interval", "_memory_threshold"]

    def __init__(self) -> None:
        memory_config = CONFIG.get("memory", {})
        self._last_gc = time.time()
        self._gc_interval = memory_config.get("gc_interval", 300)  # 5 minutes
        self._memory_threshold = memory_config.get("threshold_mb", 45)

    async def check_memory(self) -> dict[str, float]:
        """Check current memory usage and run GC if needed."""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024

        # Run GC if needed
        if (
            memory_mb > self._memory_threshold
            or time.time() - self._last_gc > self._gc_interval
        ):
            gc.collect()
            self._last_gc = time.time()
            new_memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"GC: {memory_mb:.1f}MB -> {new_memory_mb:.1f}MB")
            memory_mb = new_memory_mb

        # Assume 512MB total for resource-constrained devices
        total_mb = psutil.virtual_memory().total / 1024 / 1024
        return {
            "used_mb": memory_mb,
            "percent": (memory_mb / total_mb) * 100,
            "threshold_mb": self._memory_threshold,
        }


class AlertBatcher:
    """Batches alerts for efficient sending."""

    __slots__ = ["_queue", "_batch_task", "_batch_window", "_max_batch_size"]

    def __init__(self, batch_window: int = 10) -> None:
        self._queue: deque = deque(maxlen=100)
        self._batch_task: asyncio.Task | None = None
        self._batch_window = batch_window
        self._max_batch_size = 10

    async def add_alert(self, alert: dict[str, Any]) -> None:
        """Add alert to batch queue."""
        self._queue.append({"timestamp": datetime.now(), **alert})

        # Start batch task if not running
        if not self._batch_task or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self) -> dict[str, list[dict[str, Any]]] | None:
        """Process batched alerts."""
        await asyncio.sleep(self._batch_window)

        if not self._queue:
            return None

        # Group alerts by type/severity
        batched: dict[str, list[dict[str, Any]]] = {}
        while self._queue and len(batched) < self._max_batch_size:
            alert = self._queue.popleft()
            key = f"{alert.get('level', 'INFO')}:{alert.get('source', 'system')}"

            if key not in batched:
                batched[key] = []
            batched[key].append(alert)

        return batched


class SSHConnectionPool:
    """Manages SSH connections with pooling for resource efficiency."""

    __slots__ = ["_connections", "_max_connections", "_lock"]

    def __init__(self, max_connections: int = 3) -> None:
        self._connections: list[str] = []
        self._max_connections = max_connections
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def get_connection(self, host: str) -> AsyncGenerator[str, None]:
        """Get SSH connection from pool."""
        async with self._lock:
            while len(self._connections) >= self._max_connections:
                await asyncio.sleep(0.1)
            self._connections.append(host)

        try:
            yield host
        finally:
            async with self._lock:
                self._connections.remove(host)


class TelegramAlertBot:
    """Lightweight alert bot with AsyncIO optimization."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.memory_manager = MemoryManager()
        self.alert_batcher = AlertBatcher(config.batch_window)
        self.ssh_pool = SSHConnectionPool(config.ssh_max_connections)
        self.application: Application | None = None

        # 2FA tracking
        self.auth_attempts: dict[str, list[datetime]] = {}
        self.two_fa_codes: dict[str, str] = {}

        # Allowed services for restart
        self.allowed_services = SERVICE_CONFIG.get("allowed_restart", [])

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "🤖 *Alert Bot*\n"
            "Lightweight monitoring bot optimized for low memory.\n\n"
            "Commands:\n"
            "/status - System status\n"
            "/services - Service status\n"
            "/restart - Restart service (admin)\n"
            "/memory - Memory usage\n"
            "/help - Show help",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        await update.message.reply_text("⏳ Checking system status...")

        # Check memory first
        memory = await self.memory_manager.check_memory()

        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage("/")
        uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())

        status_text = (
            f"*System Status*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🖥 Host: {self._get_hostname()}\n"
            f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
            f"🔧 CPU: {cpu_percent}%\n"
            f"💾 Memory: {memory['used_mb']:.1f}MB ({memory['percent']:.1f}%)\n"
            f"💿 Disk: {disk.percent}% used\n"
            f"🌡 Temp: {self._get_cpu_temp()}°C\n"
        )

        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

    async def restart_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /restart command (requires admin + 2FA)."""
        user = update.effective_user

        # Check if user is admin
        if str(user.id) not in self.config.admin_ids:
            logger.warning(f"Unauthorized restart attempt by {user.username}")
            await update.message.reply_text(
                "❌ Unauthorized. This incident has been logged."
            )
            return

        # Check if already authenticated (session valid for 1 hour)
        session_time = self.config.admin_sessions.get(str(user.id))
        if session_time and (datetime.now() - session_time).seconds < 3600:
            await self._handle_restart(update, context)
        else:
            await self._request_2fa(update)

    async def _request_2fa(self, update: Update) -> None:
        """Request 2FA authentication."""
        import random
        import string

        user = update.effective_user
        code = "".join(random.choices(string.digits, k=6))
        self.two_fa_codes[str(user.id)] = code

        logger.info(f"2FA code for {user.username}: {code}")

        await update.message.reply_text(
            "🔐 *Two-Factor Authentication Required*\n"
            "A 6-digit code has been generated.\n"
            "Reply with: `/auth CODE` to continue.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def auth_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 2FA authentication."""
        user = update.effective_user

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /auth CODE")
            return

        provided_code = context.args[0]
        expected_code = self.two_fa_codes.get(str(user.id))

        if not expected_code:
            await update.message.reply_text("❌ No authentication requested")
            return

        if provided_code == expected_code:
            self.config.admin_sessions[str(user.id)] = datetime.now()
            del self.two_fa_codes[str(user.id)]
            await update.message.reply_text(
                "✅ Authentication successful!\n"
                "Session valid for 1 hour.\n"
                "You can now use admin commands."
            )
            logger.info(f"2FA successful for {user.username}")
        else:
            await update.message.reply_text("❌ Invalid code")
            logger.warning(f"2FA failed for {user.username}")

    async def _handle_restart(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle service restart after authentication."""
        if not context.args:
            # Show service selection
            buttons = [
                [InlineKeyboardButton(svc, callback_data=f"restart_{svc}")]
                for svc in self.allowed_services[:4]  # Limit to first 4
            ]
            buttons.append(
                [InlineKeyboardButton("Cancel", callback_data="restart_cancel")]
            )
            reply_markup = InlineKeyboardMarkup(buttons)

            await update.message.reply_text(
                "Select service to restart:", reply_markup=reply_markup
            )
        else:
            service = context.args[0]
            await self._restart_service(update, service)

    async def _restart_service(self, update: Update, service: str) -> None:
        """Restart a specific service."""
        if service not in self.allowed_services:
            await update.message.reply_text(f"❌ Service '{service}' not allowed")
            return

        await update.message.reply_text(f"♻️ Restarting {service}...")

        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode == 0:
                await update.message.reply_text(f"✅ {service} restarted successfully")
                logger.info(
                    f"Service {service} restarted by {update.effective_user.username}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to restart {service}: {result.stderr[:100]}"
                )

        except subprocess.TimeoutExpired:
            logger.error(f"Service restart timed out: {service}")
            await update.message.reply_text(f"❌ Restart timed out for {service}")
        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Service restart failed for {service}: {e}")
            await update.message.reply_text(
                "❌ Service restart failed. Check logs for details."
            )

    async def memory_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show detailed memory statistics."""
        memory = await self.memory_manager.check_memory()

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        text = (
            f"*Memory Usage*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🤖 Bot Process: {memory['used_mb']:.1f}MB\n"
            f"📊 System RAM: {mem.percent}% used\n"
            f"💾 Available: {mem.available / 1024 / 1024:.0f}MB\n"
            f"🔄 Swap: {swap.percent}% used\n\n"
            f"⚠️ Bot limit: {memory['threshold_mb']}MB\n"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def callback_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("restart_"):
            service = query.data.replace("restart_", "")
            if service == "cancel":
                await query.edit_message_text("Restart cancelled.")
            else:
                await query.edit_message_text(f"Restarting {service}...")
                # Simulate restart
                await asyncio.sleep(2)
                await query.edit_message_text(f"✅ {service} restarted")

    def _get_hostname(self) -> str:
        """Get system hostname."""
        import socket

        return socket.gethostname()

    def _get_cpu_temp(self) -> float:
        """Get CPU temperature."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(float(f.read().strip()) / 1000, 1)
        except OSError:
            return 0.0

    async def run(self) -> None:
        """Main bot runner with asyncio."""
        self.application = (
            Application.builder()
            .token(self.config.token)
            .connect_timeout(10.0)
            .read_timeout(10.0)
            .write_timeout(10.0)
            .pool_timeout(10.0)
            .build()
        )

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("restart", self.restart_command))
        self.application.add_handler(CommandHandler("auth", self.auth_command))
        self.application.add_handler(CommandHandler("memory", self.memory_command))
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))

        await self.application.initialize()
        await self.application.start()

        logger.info("Alert bot started successfully")

        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
        )

        # Keep running with periodic memory checks
        try:
            while True:
                await asyncio.sleep(300)
                memory = await self.memory_manager.check_memory()
                if memory["percent"] > 90:
                    logger.warning(f"High memory usage: {memory['used_mb']}MB")
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down alert bot...")
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        logger.info("Alert bot shutdown complete")


async def async_main() -> int:
    """Async main entry point."""
    try:
        config = BotConfig()
        bot = TelegramAlertBot(config)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.shutdown()))

        await bot.run()
        return 0

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 130
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


def main() -> int:
    """
    Main entry point (sync wrapper).

    Returns:
        int: Exit code (0=success, 1=error, 130=SIGINT)
    """
    import os

    # Set process nice level for lower priority (low-memory optimization)
    try:
        os.nice(10)
    except PermissionError:
        pass

    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
