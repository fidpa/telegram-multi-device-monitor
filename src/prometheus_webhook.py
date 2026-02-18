#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Prometheus Telegram Webhook Receiver

Receives Prometheus alerts via HTTP POST and forwards them to Telegram.
Includes alert deduplication, customizable templates, and rate limiting.

Features:
- Receives alerts from Prometheus Alertmanager
- Formats alerts with emoji-based severity
- Deduplication to prevent alert fatigue
- Configurable alert templates
- Health check endpoint

Usage:
    python3 prometheus_webhook.py

    # Test with curl:
    curl -X POST http://localhost:9094/webhook \
        -H "Content-Type: application/json" \
        -d '{"alerts": [{"status": "firing", "labels": {"alertname": "Test"}}]}'

Environment Variables:
    FLASK_HOST: Bind address (default: 127.0.0.1)
    FLASK_PORT: Port number (default: 9094)

Version: 1.0.0
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
SCRIPT_DIR = Path(__file__).parent
TELEGRAM_SCRIPT = SCRIPT_DIR / "simple_sender.sh"

# Alert Deduplication State
STATE_DIR = Path(os.environ.get("STATE_DIR", "/tmp/prometheus-webhook"))
STATE_FILE = STATE_DIR / "alert_state.json"
DEDUP_WINDOW_HOURS = int(os.environ.get("DEDUP_WINDOW_HOURS", "24"))

# Alert Templates (customizable)
ALERT_TEMPLATES: dict[str, dict[str, str]] = {
    # Default template for unknown alerts
    "default": {
        "emoji": "🔔",
        "format": "{emoji} {alertname}\n\n📋 Status: {status}\nSeverity: {severity}\n\nSummary: {summary}",
    },
    # Service down alerts
    "ServiceDown": {
        "emoji": "🚨",
        "format": (
            "{emoji} CRITICAL: {alertname}\n\n"
            "📋 Details:\n"
            "  Status: {status}\n"
            "  {summary}\n\n"
            "🔧 Check service status and logs"
        ),
    },
    # High resource usage
    "HighCPU": {
        "emoji": "🔥",
        "format": (
            "{emoji} WARNING: High CPU Usage\n\n"
            "📋 Details:\n"
            "  {summary}\n\n"
            "🔧 Check running processes"
        ),
    },
    "HighMemory": {
        "emoji": "💾",
        "format": (
            "{emoji} WARNING: High Memory Usage\n\n"
            "📋 Details:\n"
            "  {summary}\n\n"
            "🔧 Check memory-intensive processes"
        ),
    },
    "DiskSpaceLow": {
        "emoji": "💽",
        "format": (
            "{emoji} WARNING: Low Disk Space\n\n"
            "📋 Details:\n"
            "  {summary}\n\n"
            "🔧 Clean up disk space or expand storage"
        ),
    },
}


def get_alert_fingerprint(alert: dict[str, Any]) -> str:
    """
    Generate unique fingerprint for alert deduplication.

    Args:
        alert: Prometheus alert dictionary

    Returns:
        MD5 hash of alert labels
    """
    labels = alert.get("labels", {})
    fingerprint_data = {
        "alertname": labels.get("alertname", "unknown"),
        "instance": labels.get("instance", "unknown"),
        "component": labels.get("component", ""),
        "severity": labels.get("severity", ""),
    }
    fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
    return hashlib.md5(fingerprint_str.encode()).hexdigest()


def load_alert_state() -> dict[str, float]:
    """Load previously sent alerts from state file."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load alert state: {e}")
    return {}


def save_alert_state(state: dict[str, float]) -> None:
    """Save sent alerts to state file."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save alert state: {e}")


def should_send_alert(alert: dict[str, Any], state: dict[str, float]) -> bool:
    """
    Check if alert should be sent based on deduplication logic.

    Args:
        alert: Prometheus alert dictionary
        state: Current state of sent alerts

    Returns:
        True if alert should be sent, False if duplicate
    """
    fingerprint = get_alert_fingerprint(alert)
    current_time = time.time()

    if fingerprint in state:
        last_sent = state[fingerprint]
        hours_since_sent = (current_time - last_sent) / 3600

        if hours_since_sent < DEDUP_WINDOW_HOURS:
            alertname = alert.get("labels", {}).get("alertname", "Unknown")
            logger.info(
                f"Alert {alertname} suppressed (sent {hours_since_sent:.1f}h ago)"
            )
            return False

    state[fingerprint] = current_time
    return True


def cleanup_old_state(state: dict[str, float]) -> dict[str, float]:
    """Remove alerts older than dedup window from state."""
    current_time = time.time()
    cutoff_time = current_time - (DEDUP_WINDOW_HOURS * 3600)

    cleaned_state = {fp: ts for fp, ts in state.items() if ts > cutoff_time}

    removed_count = len(state) - len(cleaned_state)
    if removed_count > 0:
        logger.info(f"Cleaned {removed_count} old alerts from state")

    return cleaned_state


def format_telegram_message(alert: dict[str, Any]) -> str:
    """
    Format Prometheus alert for Telegram.

    Args:
        alert: Prometheus alert dictionary

    Returns:
        Formatted Telegram message string
    """
    status = alert.get("status", "unknown")
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    alertname = labels.get("alertname", "UnknownAlert")
    severity = labels.get("severity", "info")
    summary = annotations.get("summary", "No summary provided")
    description = annotations.get("description", "")

    # Get template for this alert type
    template = ALERT_TEMPLATES.get(alertname, ALERT_TEMPLATES["default"])

    message = template["format"].format(
        emoji=template["emoji"],
        alertname=alertname,
        status=status.upper(),
        severity=severity,
        summary=summary,
        description=description,
    )

    # Add description if present and not in template
    if description and "{description}" not in template["format"]:
        message += f"\n\nDescription:\n{description}"

    return message


def send_telegram_alert(message: str) -> bool:
    """
    Send Telegram alert via simple_sender.sh script.

    Args:
        message: Formatted Telegram message

    Returns:
        True on success, False on failure
    """
    try:
        if not TELEGRAM_SCRIPT.exists():
            logger.error(f"Telegram script not found: {TELEGRAM_SCRIPT}")
            return False

        result = subprocess.run(
            [str(TELEGRAM_SCRIPT), message],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode == 0:
            logger.info("Telegram alert sent successfully")
            return True
        else:
            logger.error(f"Telegram script failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Telegram script timed out after 30s")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


@app.route("/webhook", methods=["POST"])
@app.route("/api/v2/alerts", methods=["POST"])
def webhook():
    """
    Webhook endpoint for Prometheus alerts.

    Supports both /webhook and /api/v2/alerts (Prometheus native).

    Expected JSON payload:
    {
        "alerts": [
            {
                "status": "firing",
                "labels": {...},
                "annotations": {...}
            }
        ]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        # Handle both dict (with 'alerts' key) and list (direct alerts array)
        if isinstance(data, list):
            alerts = data
        else:
            alerts = data.get("alerts", [])

        if not alerts:
            logger.warning("Received webhook call without alerts")
            return jsonify({"status": "ok", "message": "No alerts to process"}), 200

        logger.info(f"Received {len(alerts)} alert(s)")

        # Load and clean alert state
        alert_state = load_alert_state()
        alert_state = cleanup_old_state(alert_state)

        sent_count = 0
        suppressed_count = 0

        for alert in alerts:
            alertname = alert.get("labels", {}).get("alertname", "Unknown")
            status = alert.get("status", "unknown")

            logger.info(f"Processing alert: {alertname} (status: {status})")

            if not should_send_alert(alert, alert_state):
                suppressed_count += 1
                continue

            message = format_telegram_message(alert)
            success = send_telegram_alert(message)

            if success:
                logger.info(f"Alert {alertname} sent to Telegram")
                sent_count += 1
            else:
                logger.error(f"Failed to send alert {alertname}")
                # Remove from state if send failed
                fingerprint = get_alert_fingerprint(alert)
                alert_state.pop(fingerprint, None)

        save_alert_state(alert_state)

        logger.info(
            f"Processed {len(alerts)} alerts: {sent_count} sent, {suppressed_count} suppressed"
        )
        return jsonify(
            {
                "status": "ok",
                "total": len(alerts),
                "sent": sent_count,
                "suppressed": suppressed_count,
            }
        ), 200

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Invalid webhook payload: {e}")
        return jsonify({"error": "Invalid payload format"}), 400
    except OSError as e:
        logger.error(f"Network/IO error processing webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/templates", methods=["GET"])
def list_templates():
    """List available alert templates."""
    return jsonify(
        {"templates": list(ALERT_TEMPLATES.keys()), "count": len(ALERT_TEMPLATES)}
    ), 200


def main() -> int:
    """Main entry point."""
    # Get Flask config from environment
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "9094"))

    logger.info(f"Starting Prometheus Telegram Webhook on {host}:{port}")

    app.run(host=host, port=port, debug=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
