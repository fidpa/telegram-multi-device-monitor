#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Telegram Alert Sender - Formatted System Status Messages

Provides pre-formatted Telegram messages for common monitoring scenarios:
- System status (CPU, Memory, Disk, Services)
- Service health checks
- Hardware metrics with severity levels

Usage:
    # Send status message
    python3 alert_sender.py status

    # Send service health
    python3 alert_sender.py services

    # Send metrics with severity
    python3 alert_sender.py metrics

    # Import as module
    from alert_sender import send_status_alert

Configuration:
    Uses config/telegram_config.yml or environment variables.

Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Import local modules
try:
    from config_loader import load_config, load_service_monitoring
    from metrics_collector import MetricsCollector
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import load_config, load_service_monitoring
    from metrics_collector import MetricsCollector

# Load configuration
CONFIG = load_config()
SERVICE_CONFIG = load_service_monitoring()


def load_credentials() -> dict[str, str]:
    """
    Load Telegram credentials from config or environment.

    Returns:
        Dictionary with 'token' and 'chat_id'
    """
    import os

    telegram_config = CONFIG.get("telegram", {})

    return {
        "token": os.environ.get("TELEGRAM_BOT_TOKEN")
        or telegram_config.get("token", ""),
        "chat_id": os.environ.get("TELEGRAM_CHAT_ID")
        or telegram_config.get("chat_id", ""),
    }


def format_status_message(metrics: dict[str, Any] | None = None) -> str:
    """
    Format comprehensive system status message.

    Args:
        metrics: Pre-collected metrics dict, or None to collect fresh

    Returns:
        Formatted Telegram message with system overview
    """
    if metrics is None:
        collector = MetricsCollector()
        metrics = collector.collect_all_metrics()

    system_name = CONFIG.get("bot", {}).get("system_name", "System")
    prefix = CONFIG.get("bot", {}).get("system_prefix", "[MONITOR]")

    message = f"📊 {prefix} System Status\n\n"

    # Hardware section
    message += "📊 Hardware:\n"

    if metrics.get("cpu_temp"):
        temp_emoji = "🌡️" if metrics["cpu_temp"] < 70 else "🔥"
        message += f"{temp_emoji} CPU: {metrics['cpu_temp']}°C\n"

    if metrics.get("memory"):
        mem_pct = metrics["memory"].get("percentage", 0)
        mem_emoji = "💾" if mem_pct < 80 else "⚠️"
        message += f"{mem_emoji} Memory: {mem_pct}% used\n"

    if metrics.get("disk"):
        disk_pct = metrics["disk"].get("percentage", 0)
        disk_emoji = "💽" if disk_pct < 85 else "⚠️"
        message += f"{disk_emoji} Disk: {disk_pct}% used\n"

    # Services section
    message += "\n🔧 Services:\n"
    if metrics.get("services"):
        for service, status in metrics["services"].items():
            status_emoji = "✅" if status == "active" else "❌"
            message += f"{status_emoji} {service}: {status}\n"
    else:
        message += "  No services configured\n"

    # Timestamp
    message += f"\n📅 {metrics.get('timestamp', 'N/A')}"

    return message


def format_services_message(metrics: dict[str, Any] | None = None) -> str:
    """
    Format service health status message.

    Args:
        metrics: Pre-collected metrics dict, or None to collect fresh

    Returns:
        Formatted Telegram message with service status
    """
    if metrics is None:
        collector = MetricsCollector()
        metrics = collector.collect_all_metrics()

    prefix = CONFIG.get("bot", {}).get("system_prefix", "[MONITOR]")

    message = f"🔧 {prefix} Service Status\n\n"

    if metrics.get("services"):
        # Get configured service groups
        critical = SERVICE_CONFIG.get("critical_services", [])
        important = SERVICE_CONFIG.get("important_services", [])

        # Critical services
        if critical:
            message += "🚨 Critical Services:\n"
            for svc in critical:
                if svc in metrics["services"]:
                    status = metrics["services"][svc]
                    emoji = "✅" if status == "active" else "❌"
                    message += f"{emoji} {svc}: {status}\n"

        # Important services
        if important:
            message += "\n⚠️ Important Services:\n"
            for svc in important:
                if svc in metrics["services"]:
                    status = metrics["services"][svc]
                    emoji = "✅" if status == "active" else "❌"
                    message += f"{emoji} {svc}: {status}\n"

        # Other services (not in critical or important)
        other_services = [
            s
            for s in metrics["services"]
            if s not in critical and s not in important
        ]
        if other_services:
            message += "\n📋 Other Services:\n"
            for svc in other_services:
                status = metrics["services"][svc]
                emoji = "✅" if status == "active" else "❌"
                message += f"{emoji} {svc}: {status}\n"

    message += f"\n📅 {metrics.get('timestamp', 'N/A')}"
    return message


def format_metrics_message(metrics: dict[str, Any] | None = None) -> str:
    """
    Format hardware metrics with severity levels.

    Args:
        metrics: Pre-collected metrics dict, or None to collect fresh

    Returns:
        Formatted Telegram message with severity-colored metrics
    """
    if metrics is None:
        collector = MetricsCollector()
        metrics = collector.collect_all_metrics()

    prefix = CONFIG.get("bot", {}).get("system_prefix", "[MONITOR]")

    message = f"📊 {prefix} Hardware Metrics\n\n"

    # CPU Temperature with severity
    if metrics.get("cpu_temp"):
        temp = metrics["cpu_temp"]
        if temp > 80:
            message += f"🔥 CRITICAL CPU: {temp}°C\n"
        elif temp > 70:
            message += f"⚠️ WARNING CPU: {temp}°C\n"
        else:
            message += f"🌡️ CPU: {temp}°C ✅\n"

    # Memory with severity
    if metrics.get("memory"):
        mem_pct = metrics["memory"].get("percentage", 0)
        if mem_pct > 90:
            message += f"🚨 CRITICAL Memory: {mem_pct}%\n"
        elif mem_pct > 80:
            message += f"⚠️ WARNING Memory: {mem_pct}%\n"
        else:
            message += f"💾 Memory: {mem_pct}% ✅\n"

        used = metrics["memory"].get("used_mb", 0)
        total = metrics["memory"].get("total_mb", 0)
        message += f"   {used}/{total} MB\n"

    # Disk with severity
    if metrics.get("disk"):
        disk_pct = metrics["disk"].get("percentage", 0)
        if disk_pct > 95:
            message += f"🚨 CRITICAL Disk: {disk_pct}%\n"
        elif disk_pct > 85:
            message += f"⚠️ WARNING Disk: {disk_pct}%\n"
        else:
            message += f"💽 Disk: {disk_pct}% ✅\n"

        used = metrics["disk"].get("used", "?")
        size = metrics["disk"].get("size", "?")
        message += f"   {used}/{size}\n"

    # Load average
    if metrics.get("load"):
        load = metrics["load"]
        message += f"\n📈 Load: {load.get('load_1min', 0):.2f} / {load.get('load_5min', 0):.2f} / {load.get('load_15min', 0):.2f}\n"

    message += f"\n📅 {metrics.get('timestamp', 'N/A')}"
    return message


async def send_telegram_message(message_text: str) -> bool:
    """
    Send message to Telegram bot.

    Args:
        message_text: Formatted message text to send

    Returns:
        True if message sent successfully, False otherwise
    """
    credentials = load_credentials()
    token = credentials.get("token")
    chat_id = credentials.get("chat_id")

    # Log credential status without exposing values
    token_status = "loaded" if token else "MISSING"
    chat_status = "configured" if chat_id else "MISSING"
    logger.debug(f"Bot token: {token_status}, Chat ID: {chat_status}")

    if not token or not chat_id:
        logger.error("Missing credentials - cannot send message")
        return False

    try:
        from telegram import Bot

        bot = Bot(token=token)
        result = await bot.send_message(chat_id=chat_id, text=message_text)
        logger.info(f"Message sent successfully - ID {result.message_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return False


def send_status_alert(metrics: dict[str, Any] | None = None) -> bool:
    """
    Send system status alert.

    Args:
        metrics: Pre-collected metrics, or None to collect fresh

    Returns:
        True if sent successfully
    """
    message = format_status_message(metrics)
    return asyncio.run(send_telegram_message(message))


def send_services_alert(metrics: dict[str, Any] | None = None) -> bool:
    """
    Send service health alert.

    Args:
        metrics: Pre-collected metrics, or None to collect fresh

    Returns:
        True if sent successfully
    """
    message = format_services_message(metrics)
    return asyncio.run(send_telegram_message(message))


def send_metrics_alert(metrics: dict[str, Any] | None = None) -> bool:
    """
    Send hardware metrics alert.

    Args:
        metrics: Pre-collected metrics, or None to collect fresh

    Returns:
        True if sent successfully
    """
    message = format_metrics_message(metrics)
    return asyncio.run(send_telegram_message(message))


def main() -> int:
    """Main entry point for CLI usage."""
    if len(sys.argv) < 2:
        print("Usage: python3 alert_sender.py [status|services|metrics]")
        return 1

    command = sys.argv[1].lower()

    if command == "status":
        success = send_status_alert()
    elif command == "services":
        success = send_services_alert()
    elif command == "metrics":
        success = send_metrics_alert()
    else:
        print("Available commands: status, services, metrics")
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
