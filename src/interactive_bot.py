#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Interactive System Monitor Telegram Bot

Full-featured Telegram bot for remote system monitoring and management:
- System status (CPU, Memory, Disk, Temperature)
- Service health checks (systemd, Docker)
- Network monitoring (interfaces, routes, VPN)
- Remote service restart (admin-only with confirmation)
- Configurable alerts and rate limiting

Usage:
    # Run directly
    python3 interactive_bot.py

    # As systemd service
    systemctl start telegram-interactive-bot.service

    # With custom config
    TELEGRAM_CONFIG_DIR=/etc/mybot python3 interactive_bot.py

Configuration:
    See config/telegram_config.yml.example for configuration options.
    Bot token and chat ID can be set via environment variables.

Telegram Commands:
    /status, /services, /docker, /metrics, /logs, /restart, /help

Version: 1.0.0
"""

import asyncio
import logging
import logging.handlers
import os
import re
import signal
import socket
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Import local config loader
try:
    from config_loader import load_config, load_service_monitoring, validate_config
except ImportError:
    # Handle case when running from different directory
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import load_config, load_service_monitoring, validate_config


# ===== Configuration =====
CONFIG = load_config()
SERVICE_CONFIG = load_service_monitoring()

# Timeouts (from config)
SUBPROCESS_TIMEOUT = CONFIG.get("timeouts", {}).get("subprocess", 30)
HARDWARE_QUERY_TIMEOUT = CONFIG.get("timeouts", {}).get("hardware_query", 5)
DOCKER_TIMEOUT = CONFIG.get("timeouts", {}).get("docker", 10)
ROUTE_CHECK_TIMEOUT = CONFIG.get("timeouts", {}).get("route_check", 10)
PING_TIMEOUT = CONFIG.get("timeouts", {}).get("ping", 8)

# Rate Limiting
RATE_LIMIT_WINDOW = CONFIG.get("telegram", {}).get("rate_limit_window", 60)

# Logging configuration
LOG_CONFIG = CONFIG.get("logging", {})
LOG_MAX_BYTES = LOG_CONFIG.get("max_bytes", 10 * 1024 * 1024)
LOG_BACKUP_COUNT = LOG_CONFIG.get("backup_count", 3)
LOG_DIR = Path(LOG_CONFIG.get("log_dir", "/var/log/telegram-monitor"))

# Create log directory if possible
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    LOG_DIR = Path("/tmp/telegram-monitor")
    LOG_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
LOG_LEVEL = os.getenv("LOG_LEVEL", CONFIG.get("bot", {}).get("log_level", "INFO"))
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "bot.log",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
        ),
    ],
)
logger = logging.getLogger(__name__)

# Monitoring configuration (from service_monitoring.yml)
CRITICAL_SERVICES = SERVICE_CONFIG.get("critical_services", [])
ALLOWED_SERVICES = SERVICE_CONFIG.get("allowed_restart", []) + CRITICAL_SERVICES

# Network interfaces (from config or auto-detect)
MONITORED_INTERFACES = CONFIG.get("monitoring", {}).get("interfaces", [])
if not MONITORED_INTERFACES:
    # Auto-detect: use all non-loopback interfaces
    try:
        MONITORED_INTERFACES = [
            iface for iface in psutil.net_if_addrs().keys() if iface != "lo"
        ]
    except (OSError, AttributeError):
        MONITORED_INTERFACES = ["eth0"]

# Security: Valid systemd service name pattern
# Allows alphanumeric, underscore, hyphen, dot, and @ (for template instances)
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_@.-]+\.?[a-zA-Z0-9_@.-]*$")


class BotConfig:
    """Bot configuration management with environment override support."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.chat_id: str | None = None
        self.admin_ids: set[str] = set()

        # System identity (configurable)
        bot_config = CONFIG.get("bot", {})
        self.system_name = bot_config.get("system_name", "System Monitor")
        self.system_prefix = bot_config.get("system_prefix", "[MONITOR]")

        self.load_config()

    def load_config(self) -> None:
        """
        Load configuration from config file and environment.

        Priority:
        1. Environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        2. Config file (telegram_config.yml)
        """
        telegram_config = CONFIG.get("telegram", {})

        # Token
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN") or telegram_config.get(
            "token"
        )

        # Chat ID
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID") or telegram_config.get(
            "chat_id"
        )

        # Admin IDs
        env_admin_ids = os.environ.get("TELEGRAM_ADMIN_IDS")
        if env_admin_ids:
            self.admin_ids = set(env_admin_ids.split(","))
        else:
            admin_list = telegram_config.get("admin_ids", [])
            self.admin_ids = set(str(aid) for aid in admin_list)

        # Validation with secure logging
        if not self.token:
            logger.warning("Bot Token not configured!")
        else:
            logger.debug(f"Bot Token loaded: {self.token[:10]}*** (masked)")

        if not self.chat_id:
            logger.warning("Chat ID not configured!")
        else:
            logger.debug(f"Chat ID configured: {self.chat_id}")

        if self.admin_ids:
            logger.info(f"Admin IDs configured: {len(self.admin_ids)} admin(s)")
        else:
            logger.warning("No Admin IDs configured!")


class SystemMonitor:
    """System monitoring utilities with graceful degradation."""

    @staticmethod
    def get_system_status() -> dict[str, Any]:
        """
        Get comprehensive system status with graceful degradation.

        Returns partial data if individual checks fail. Never crashes.

        Returns:
            dict with guaranteed structure including 'timestamp', 'healthy',
            and various system metrics (with None/defaults on errors)
        """
        status: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "healthy": True,
        }

        # CPU and Memory
        try:
            status["cpu_percent"] = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            status["memory_percent"] = memory.percent
            status["memory_used_gb"] = memory.used / (1024**3)
            status["memory_total_gb"] = memory.total / (1024**3)
        except OSError as e:
            logger.warning(f"CPU/Memory check failed: {e}")
            status["cpu_percent"] = 0.0
            status["memory_percent"] = 0.0
            status["memory_used_gb"] = 0.0
            status["memory_total_gb"] = 0.0
            status["healthy"] = False

        # Disk usage
        try:
            disk = psutil.disk_usage("/")
            status["disk_percent"] = disk.percent
            status["disk_used_gb"] = disk.used / (1024**3)
            status["disk_total_gb"] = disk.total / (1024**3)
        except OSError as e:
            logger.warning(f"Disk check failed: {e}")
            status["disk_percent"] = 0.0
            status["disk_used_gb"] = 0.0
            status["disk_total_gb"] = 0.0
            status["healthy"] = False

        # Network interfaces
        interfaces: dict[str, str] = {}
        try:
            for iface, addrs in psutil.net_if_addrs().items():
                if iface in MONITORED_INTERFACES:
                    for addr in addrs:
                        if hasattr(socket, "AF_INET") and addr.family == socket.AF_INET:
                            interfaces[iface] = addr.address
                            break
        except OSError as e:
            logger.warning(f"Error getting network interfaces: {e}")
            status["healthy"] = False
        status["interfaces"] = interfaces

        # Temperature (platform-specific)
        status["temperature"] = SystemMonitor._get_temperature()

        # Service status
        services: dict[str, bool] = {}
        try:
            for service in CRITICAL_SERVICES:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=HARDWARE_QUERY_TIMEOUT,
                    check=False,
                )
                services[service] = result.stdout.strip() == "active"
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Service check failed: {e}")
            status["healthy"] = False
        status["services"] = services

        # Docker containers
        docker_status: list[dict[str, Any]] = []
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}:{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=DOCKER_TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            name, container_status = parts
                            docker_status.append(
                                {"name": name, "running": "Up" in container_status}
                            )
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Docker check failed: {e}")
        status["docker"] = docker_status

        # Current default route
        try:
            route_output = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=HARDWARE_QUERY_TIMEOUT,
                check=False,
            )
            # Extract interface from route output
            for iface in MONITORED_INTERFACES:
                if f"dev {iface}" in route_output.stdout:
                    status["current_wan"] = iface
                    break
            else:
                status["current_wan"] = "unknown"
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Route check failed: {e}")
            status["current_wan"] = "unknown"

        return status

    @staticmethod
    def _get_temperature() -> float:
        """
        Get CPU temperature (platform-specific).

        Tries multiple methods:
        1. vcgencmd (Raspberry Pi)
        2. /sys/class/thermal (Linux generic)
        3. psutil sensors

        Returns:
            Temperature in Celsius, or 0.0 if unavailable
        """
        # Try vcgencmd (Raspberry Pi)
        try:
            temp_output = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
                timeout=HARDWARE_QUERY_TIMEOUT,
                check=False,
            )
            if temp_output.returncode == 0 and "=" in temp_output.stdout:
                temp_str = temp_output.stdout.strip()
                return float(temp_str.split("=")[1].replace("'C", ""))
        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            pass

        # Try /sys/class/thermal (Linux generic)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return float(f.read().strip()) / 1000
        except (OSError, ValueError):
            pass

        # Try psutil sensors
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        return entries[0].current
        except (AttributeError, OSError):
            pass

        return 0.0

    @staticmethod
    def check_interface_connectivity(interface: str) -> bool:
        """Test connectivity on specific interface."""
        try:
            result = subprocess.run(
                ["/bin/ping", "-c", "1", "-W", "3", "-I", interface, "8.8.8.8"],
                capture_output=True,
                timeout=PING_TIMEOUT,
                check=False,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Error testing {interface} connectivity: {e}")
            return False


class AlertManager:
    """Manages alerts and rate limiting."""

    def __init__(self, bot_config: BotConfig) -> None:
        self.config = bot_config
        self.alert_queue: deque = deque(maxlen=100)
        self.last_alerts: dict[str, datetime] = {}

    def should_send_alert(self, alert_type: str) -> bool:
        """Check if alert should be sent based on rate limiting."""
        now = datetime.now(timezone.utc)
        if alert_type in self.last_alerts:
            time_diff = (now - self.last_alerts[alert_type]).total_seconds()
            if time_diff < RATE_LIMIT_WINDOW:
                return False
        self.last_alerts[alert_type] = now
        return True

    def format_alert(
        self, level: str, message: str, details: dict[str, Any] | None = None
    ) -> str:
        """Format alert message with emoji and details."""
        emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "SUCCESS": "✅",
            "RECOVERY": "🔄",
        }

        emoji = emojis.get(level, "📢")
        formatted = f"{self.config.system_prefix} {emoji} *{level}*\n\n{message}"

        if details:
            formatted += "\n\n*Details:*\n"
            for key, value in details.items():
                formatted += f"• {key}: `{value}`\n"

        formatted += f"\n_Time: {datetime.now(timezone.utc).strftime('%H:%M:%S')}_"
        return formatted


class InteractiveBot:
    """Main interactive bot class."""

    def __init__(self) -> None:
        self.config = BotConfig()
        self.monitor = SystemMonitor()
        self.alerts = AlertManager(self.config)
        self.application: Application | None = None
        self.admin_sessions: dict[str, Any] = {}

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        welcome_msg = (
            f"🤖 *{self.config.system_name} Bot*\n\n"
            "Remote system monitoring and control.\n\n"
            "*Available commands:*\n"
            "/status - System overview\n"
            "/services - Service status\n"
            "/docker - Docker containers\n"
            "/metrics - Performance metrics\n"
            "/logs - View recent logs\n"
            "/restart - Restart a service (admin)\n"
            "/help - Show all commands\n"
        )
        await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        status = self.monitor.get_system_status()

        if not status.get("healthy", True):
            await update.message.reply_text(
                "⚠️ System status degraded - partial data available"
            )

        msg = f"*{self.config.system_prefix} System Status*\n\n"
        msg += f"🖥️ *CPU:* {status.get('cpu_percent', 0):.1f}%\n"
        msg += f"💾 *Memory:* {status.get('memory_percent', 0):.1f}% "
        msg += f"({status.get('memory_used_gb', 0):.1f}/{status.get('memory_total_gb', 0):.1f} GB)\n"
        msg += f"💿 *Disk:* {status.get('disk_percent', 0):.1f}% "
        msg += f"({status.get('disk_used_gb', 0):.1f}/{status.get('disk_total_gb', 0):.1f} GB)\n"
        msg += f"🌡️ *Temperature:* {status.get('temperature', 0):.1f}°C\n"
        msg += f"🌐 *Active Interface:* {status.get('current_wan', 'unknown')}\n\n"

        # Services
        msg += "*Services:*\n"
        for service, active in status.get("services", {}).items():
            emoji = "✅" if active else "❌"
            msg += f"  {emoji} {service}\n"

        # Network interfaces
        msg += "\n*Network Interfaces:*\n"
        for iface, ip in status.get("interfaces", {}).items():
            msg += f"  • {iface}: `{ip}`\n"

        msg += f"\n_Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')}_"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def services_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /services command."""
        status = self.monitor.get_system_status()

        msg = f"*{self.config.system_prefix} Service Status*\n\n"

        # System services
        msg += "*System Services:*\n"
        for service, active in status.get("services", {}).items():
            emoji = "✅" if active else "❌"
            msg += f"  {emoji} {service}\n"

        # Docker containers
        if status.get("docker"):
            msg += "\n*Docker Containers:*\n"
            for container in status["docker"]:
                emoji = "🟢" if container["running"] else "🔴"
                msg += f"  {emoji} {container['name']}\n"

        msg += f"\n_Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')}_"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def metrics_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /metrics command with visual bars."""
        status = self.monitor.get_system_status()

        def get_bar(percent: float, width: int = 10) -> str:
            filled = int(percent / 100 * width)
            return "█" * filled + "░" * (width - filled)

        msg = f"*{self.config.system_prefix} System Metrics*\n\n"

        # CPU
        cpu_bar = get_bar(status.get("cpu_percent", 0))
        msg += f"🖥️ *CPU:* {cpu_bar} {status.get('cpu_percent', 0):.1f}%\n"

        # Memory
        mem_bar = get_bar(status.get("memory_percent", 0))
        msg += f"💾 *RAM:* {mem_bar} {status.get('memory_percent', 0):.1f}%\n"
        msg += f"   Used: {status.get('memory_used_gb', 0):.1f} GB / {status.get('memory_total_gb', 0):.1f} GB\n\n"

        # Disk
        disk_bar = get_bar(status.get("disk_percent", 0))
        msg += f"💿 *Disk:* {disk_bar} {status.get('disk_percent', 0):.1f}%\n"
        msg += f"   Used: {status.get('disk_used_gb', 0):.1f} GB / {status.get('disk_total_gb', 0):.1f} GB\n\n"

        # Temperature
        temp = status.get("temperature", 0)
        temp_emoji = "🟢" if temp < 60 else "🟡" if temp < 70 else "🔴"
        msg += f"🌡️ *Temp:* {temp_emoji} {temp:.1f}°C\n"

        msg += f"\n_Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')}_"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def restart_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /restart command (admin only)."""
        user_id = str(update.effective_user.id)

        if user_id not in self.config.admin_ids:
            await update.message.reply_text("❌ Unauthorized: Admin access required")
            return

        if not context.args:
            allowed_preview = ALLOWED_SERVICES[:5]
            await update.message.reply_text(
                "Usage: `/restart <service>`\n"
                "Example: `/restart nginx`\n\n"
                f"Allowed services: {', '.join(allowed_preview)}...",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        service_name = context.args[0]

        # Security: Whitelist validation
        if service_name not in ALLOWED_SERVICES:
            await update.message.reply_text(
                f"❌ *Service not allowed*\n\n"
                f"Service '{service_name}' is not in the allowed list.\n\n"
                f"Allowed services:\n"
                + "\n".join([f"• `{s}`" for s in sorted(ALLOWED_SERVICES)]),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Confirmation with inline keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Confirm", callback_data=f"restart_confirm_{service_name}"
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="restart_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ *Confirm Service Restart*\n\n"
            f"Service: `{service_name}`\n\n"
            f"Are you sure you want to restart this service?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def handle_restart_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle restart confirmation callback."""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data == "restart_cancel":
            await query.edit_message_text("❌ Restart cancelled")
            return

        if data.startswith("restart_confirm_"):
            service_name = data.replace("restart_confirm_", "")

            # Re-validate (callback data could be manipulated)
            if service_name not in ALLOWED_SERVICES:
                await query.edit_message_text(
                    f"❌ Security Error: Service '{service_name}' not allowed"
                )
                return

            await query.edit_message_text(f"🔄 Restarting {service_name}...")

            try:
                result = subprocess.run(
                    ["sudo", "systemctl", "restart", service_name],
                    capture_output=True,
                    text=True,
                    timeout=SUBPROCESS_TIMEOUT,
                    check=False,
                )

                if result.returncode == 0:
                    check = subprocess.run(
                        ["systemctl", "is-active", service_name],
                        capture_output=True,
                        text=True,
                        timeout=HARDWARE_QUERY_TIMEOUT,
                        check=False,
                    )

                    if check.stdout.strip() == "active":
                        await query.edit_message_text(
                            f"✅ Service `{service_name}` restarted successfully!",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    else:
                        await query.edit_message_text(
                            f"⚠️ Service `{service_name}` restarted but not active\n"
                            f"Check logs with: `/logs {service_name}`",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                else:
                    await query.edit_message_text(
                        f"❌ Failed to restart `{service_name}`\n"
                        f"Error: {result.stderr[:200]}",
                        parse_mode=ParseMode.MARKDOWN,
                    )

            except (subprocess.SubprocessError, OSError) as e:
                logger.error(f"Restart failed: {e}")
                await query.edit_message_text(f"❌ Error restarting service: {str(e)}")

    async def logs_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /logs command."""
        lines = 10
        service = None

        if context.args:
            try:
                lines = int(context.args[0])
                if len(context.args) > 1:
                    service = context.args[1]
            except ValueError:
                service = context.args[0]
                if len(context.args) > 1:
                    try:
                        lines = int(context.args[1])
                    except ValueError:
                        pass

        lines = min(lines, 50)

        # Security: Validate service name to prevent command injection
        if service and not SERVICE_NAME_PATTERN.match(service):
            await update.message.reply_text(
                "❌ Invalid service name. Use only letters, numbers, "
                "underscores, hyphens, dots, and @."
            )
            return

        try:
            if service:
                cmd = [
                    "journalctl",
                    "-u",
                    service,
                    "-n",
                    str(lines),
                    "--no-pager",
                    "-o",
                    "short",
                ]
            else:
                cmd = [
                    "journalctl",
                    "-p",
                    "4",
                    "-n",
                    str(lines),
                    "--no-pager",
                    "-o",
                    "short",
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DOCKER_TIMEOUT,
                check=False,
            )

            if result.stdout.strip():
                log_lines = result.stdout.strip().split("\n")[-lines:]
                msg = f"*📋 System Logs*"
                if service:
                    msg += f" *[{service}]*\n"
                else:
                    msg += " *(Warnings & Errors)*\n"
                msg += f"_Last {len(log_lines)} entries:_\n\n"
                msg += "```\n" + "\n".join(log_lines[-10:]) + "\n```"
                await update.message.reply_text(
                    msg[:4000], parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text("No logs found")

        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Logs retrieval failed: {e}")
            await update.message.reply_text(f"❌ Error retrieving logs: {str(e)}")

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        user_id = str(update.effective_user.id)
        is_admin = user_id in self.config.admin_ids

        msg = f"*{self.config.system_name} Bot Commands*\n\n"
        msg += "*📊 Monitoring:*\n"
        msg += "`/status` (`/s`) - System overview\n"
        msg += "`/services` (`/v`) - Service status\n"
        msg += "`/docker` (`/d`) - Docker containers\n"
        msg += "`/metrics` (`/m`) - Performance metrics\n"
        msg += "`/logs` (`/l`) [lines] [service] - View logs\n\n"

        if is_admin:
            msg += "*🔧 Admin Commands:*\n"
            msg += "`/restart` (`/r`) <service> - Restart a service\n\n"

        msg += "*ℹ️ Info:*\n"
        msg += "`/help` (`/h`) - Show this message\n\n"
        msg += "_💡 Tip: Use short aliases for faster access!_\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def send_alert(
        self, level: str, message: str, details: dict[str, Any] | None = None
    ) -> bool:
        """
        Send alert to configured chat.

        Returns:
            True if sent successfully, False otherwise.
            Never raises - all errors are logged and swallowed.
        """
        if not self.config.token or not self.config.chat_id:
            logger.warning("Cannot send alert - bot not configured")
            return False

        if not self.alerts.should_send_alert(f"{level}_{message[:20]}"):
            logger.debug(f"Rate limited alert: {level} - {message}")
            return False

        formatted_message = self.alerts.format_alert(level, message, details)

        try:
            bot = Bot(token=self.config.token)
            await bot.send_message(
                chat_id=self.config.chat_id,
                text=formatted_message,
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info(f"Alert sent: {level} - {message}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send alert (non-fatal): {e}")
            return False

    def setup_handlers(self) -> None:
        """Register command handlers."""
        if not self.application:
            return

        # Command handlers with aliases
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("s", self.status_command))
        self.application.add_handler(CommandHandler("services", self.services_command))
        self.application.add_handler(CommandHandler("v", self.services_command))
        self.application.add_handler(CommandHandler("docker", self.services_command))
        self.application.add_handler(CommandHandler("d", self.services_command))
        self.application.add_handler(CommandHandler("metrics", self.metrics_command))
        self.application.add_handler(CommandHandler("m", self.metrics_command))
        self.application.add_handler(CommandHandler("logs", self.logs_command))
        self.application.add_handler(CommandHandler("l", self.logs_command))
        self.application.add_handler(CommandHandler("restart", self.restart_command))
        self.application.add_handler(CommandHandler("r", self.restart_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("h", self.help_command))

        # Callback handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_restart_callback))

    async def start_bot(self) -> None:
        """Start the bot."""
        if not self.config.token:
            logger.error("Bot Token not configured - cannot start")
            return

        logger.info(f"Starting {self.config.system_name} Telegram Bot...")

        if not self.application:
            self.application = Application.builder().token(self.config.token).build()
            self.setup_handlers()

        # Send startup message
        await self.send_alert(
            "INFO",
            "Bot Started",
            {
                "System": self.config.system_name,
                "Time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)

        logger.info("Bot started successfully")

    async def stop_bot(self) -> None:
        """Gracefully stop the bot."""
        logger.info("Stopping bot...")

        if self.application:
            await self.send_alert(
                "INFO", "Bot Stopping", {"Reason": "Service shutdown"}
            )
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        logger.info("Bot stopped")


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0=success, 1=error, 130=SIGINT)
    """
    # Validate configuration
    errors = validate_config(CONFIG)
    if errors:
        for error in errors:
            logger.error(f"Config error: {error}")
        return 1

    bot = InteractiveBot()

    # Signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} received")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(bot.stop_bot())
        except RuntimeError:
            pass
        sys.exit(128 + sig)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.start_bot())
        loop.run_forever()
        return 0

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        return 130
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(bot.stop_bot())
        except (OSError, RuntimeError) as stop_error:
            logger.error(f"Error stopping bot: {stop_error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
