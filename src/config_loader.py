#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Configuration Loader for telegram-multi-device-monitor.

Provides centralized YAML configuration loading with environment variable
override support, validation, and sensible defaults.

Usage:
    from config_loader import load_config, get_config_dir

    config = load_config()  # Auto-discovers config file
    config = load_config(Path("/etc/mybot/config.yml"))  # Explicit path

Environment Variables:
    TELEGRAM_CONFIG_DIR: Override default config directory
    TELEGRAM_BOT_TOKEN: Override token from config file
    TELEGRAM_CHAT_ID: Override chat ID from config file
    LOG_LEVEL: Override log level (DEBUG, INFO, WARNING, ERROR)
"""

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULTS: dict[str, Any] = {
    "bot": {
        "system_name": "System Monitor",
        "system_prefix": "[MONITOR]",
        "log_level": "INFO",
    },
    "telegram": {
        "token": "",
        "chat_id": "",
        "admin_ids": [],
        "rate_limit_window": 60,
    },
    "monitoring": {
        "interfaces": [],
        "critical_services": [],
        "allowed_restart_services": [],
    },
    "timeouts": {
        "subprocess": 30,
        "hardware_query": 5,
        "docker": 10,
        "route_check": 10,
        "ping": 8,
    },
    "logging": {
        "max_bytes": 10485760,  # 10MB
        "backup_count": 3,
        "log_dir": "/var/log/telegram-monitor",
    },
    "ssh": {
        "targets": [],
        "key_path": "",
        "connect_timeout": 10,
        "command_timeout": 15,
        "max_retries": 3,
    },
    "memory": {
        "limit_mb": 50,
        "gc_interval": 300,
        "threshold_mb": 45,
    },
}


def get_config_dir() -> Path:
    """
    Get configuration directory from environment or default locations.

    Priority:
        1. TELEGRAM_CONFIG_DIR environment variable
        2. ./config/ (relative to script)
        3. /etc/telegram-monitor/
        4. ~/.config/telegram-monitor/

    Returns:
        Path to configuration directory
    """
    # Check environment variable first
    env_dir = os.environ.get("TELEGRAM_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)

    # Check common locations
    locations = [
        Path(__file__).parent.parent / "config",  # ./config/ relative to src/
        Path("/etc/telegram-monitor"),
        Path.home() / ".config" / "telegram-monitor",
    ]

    for loc in locations:
        if loc.exists() and loc.is_dir():
            return loc

    # Return first option even if doesn't exist (for creation)
    return locations[0]


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary with defaults
        override: Override dictionary with user values

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_file: Path | None = None) -> dict[str, Any]:
    """
    Load YAML configuration file with defaults and environment overrides.

    Args:
        config_file: Optional explicit path to config file.
                    If None, auto-discovers from config directory.

    Returns:
        Configuration dictionary with all settings

    Raises:
        FileNotFoundError: If config file specified but not found
        yaml.YAMLError: If config file has invalid YAML syntax
    """
    # Use deepcopy to avoid mutating DEFAULTS (nested dicts)
    config = copy.deepcopy(DEFAULTS)

    # Determine config file path
    if config_file is None:
        config_dir = get_config_dir()
        config_file = config_dir / "telegram_config.yml"

    # Load from file if exists
    if config_file.exists():
        logger.info(f"Loading configuration from {config_file}")
        with open(config_file, "r") as f:
            file_config = yaml.safe_load(f) or {}
        config = deep_merge(config, file_config)
    else:
        logger.warning(f"Config file not found: {config_file}, using defaults")

    # Environment variable overrides (highest priority)
    env_overrides = {
        "TELEGRAM_BOT_TOKEN": ("telegram", "token"),
        "TELEGRAM_CHAT_ID": ("telegram", "chat_id"),
        "TELEGRAM_ADMIN_IDS": ("telegram", "admin_ids"),
        "LOG_LEVEL": ("bot", "log_level"),
    }

    for env_var, path in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            if path[1] == "admin_ids":
                # Parse comma-separated list
                value = [v.strip() for v in value.split(",") if v.strip()]
            # Navigate to nested key and set value
            section = config.get(path[0], {})
            section[path[1]] = value
            config[path[0]] = section
            logger.debug(f"Config override from {env_var}")

    return config


def load_ssh_targets(config_file: Path | None = None) -> list[dict[str, Any]]:
    """
    Load SSH targets configuration.

    Args:
        config_file: Optional explicit path to ssh_targets.yml

    Returns:
        List of SSH target dictionaries with host, user, key_path, etc.
    """
    if config_file is None:
        config_dir = get_config_dir()
        config_file = config_dir / "ssh_targets.yml"

    if not config_file.exists():
        logger.warning(f"SSH targets file not found: {config_file}")
        return []

    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    return data.get("targets", [])


def load_service_monitoring(config_file: Path | None = None) -> dict[str, Any]:
    """
    Load service monitoring configuration.

    Args:
        config_file: Optional explicit path to service_monitoring.yml

    Returns:
        Dictionary with critical_services, important_services, allowed_restart lists
    """
    if config_file is None:
        config_dir = get_config_dir()
        config_file = config_dir / "service_monitoring.yml"

    defaults = {
        "critical_services": [],
        "important_services": [],
        "allowed_restart": [],
    }

    if not config_file.exists():
        logger.warning(f"Service monitoring file not found: {config_file}")
        return defaults

    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    return deep_merge(defaults, data)


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate configuration and return list of errors.

    Args:
        config: Configuration dictionary to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Required fields
    telegram = config.get("telegram", {})
    if not telegram.get("token"):
        errors.append("telegram.token is required")
    if not telegram.get("chat_id"):
        errors.append("telegram.chat_id is required")

    # Token format validation
    token = telegram.get("token", "")
    if token and ":" not in token:
        errors.append("telegram.token format invalid (expected: <bot_id>:<secret>)")

    return errors


def mask_sensitive(config: dict[str, Any]) -> dict[str, Any]:
    """
    Return config with sensitive values masked for logging.

    Args:
        config: Configuration dictionary

    Returns:
        Copy of config with tokens/secrets masked
    """
    masked = config.copy()

    if "telegram" in masked:
        telegram = masked["telegram"].copy()
        if telegram.get("token"):
            token = telegram["token"]
            telegram["token"] = f"{token[:10]}***" if len(token) > 10 else "***"
        if telegram.get("admin_ids"):
            telegram["admin_ids"] = f"[{len(telegram['admin_ids'])} IDs]"
        masked["telegram"] = telegram

    return masked


if __name__ == "__main__":
    # CLI test mode
    import json

    logging.basicConfig(level=logging.DEBUG)

    config = load_config()
    print("=== Configuration (masked) ===")
    print(json.dumps(mask_sensitive(config), indent=2))

    errors = validate_config(config)
    if errors:
        print("\n=== Validation Errors ===")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ Configuration valid")
