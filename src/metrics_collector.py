#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
"""
Hardware Metrics Collector

Collects system metrics locally or from remote devices via SSH.
Supports multiple platforms and graceful degradation.

Features:
- Local metrics collection (psutil-based)
- Remote SSH metrics collection (agent-less)
- Configurable SSH targets
- Retry logic with exponential backoff
- Platform-specific temperature reading

Usage:
    # Collect local metrics
    collector = MetricsCollector()
    metrics = collector.collect_all_metrics()

    # Collect remote metrics
    collector = RemoteMetricsCollector(host="your-host", user="your-user")
    metrics = collector.collect_all_metrics()

    # CLI usage
    python3 metrics_collector.py [--remote HOST]

Configuration:
    SSH targets can be configured in config/ssh_targets.yml

Version: 1.0.0
"""

import json
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to import psutil (optional for local metrics)
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Import local config loader
try:
    from config_loader import load_config, load_ssh_targets, load_service_monitoring
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import load_config, load_ssh_targets, load_service_monitoring

# Configuration
CONFIG = load_config()
SERVICE_CONFIG = load_service_monitoring()

# SSH Configuration
SSH_CONFIG = CONFIG.get("ssh", {})
SSH_CONNECT_TIMEOUT = SSH_CONFIG.get("connect_timeout", 10)
SSH_COMMAND_TIMEOUT = SSH_CONFIG.get("command_timeout", 15)
MAX_RETRIES = SSH_CONFIG.get("max_retries", 3)
RETRY_BASE_DELAY = 2


class MetricsCollector:
    """Local system metrics collector using psutil."""

    def __init__(self) -> None:
        if not HAS_PSUTIL:
            raise ImportError("psutil is required for local metrics collection")

    def get_cpu_temperature(self) -> float | None:
        """
        Get CPU temperature using multiple methods.

        Tries (in order):
        1. vcgencmd (Raspberry Pi)
        2. /sys/class/thermal (Linux generic)
        3. psutil sensors

        Returns:
            Temperature in Celsius, or None if unavailable
        """
        # Try vcgencmd (Raspberry Pi)
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and "=" in result.stdout:
                temp_str = result.stdout.strip()
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

        return None

    def get_memory_stats(self) -> dict[str, Any] | None:
        """Get memory usage statistics."""
        try:
            mem = psutil.virtual_memory()
            return {
                "total_mb": mem.total // (1024 * 1024),
                "used_mb": mem.used // (1024 * 1024),
                "free_mb": mem.available // (1024 * 1024),
                "percentage": round(mem.percent, 1),
            }
        except OSError:
            return None

    def get_disk_stats(self, path: str = "/") -> dict[str, Any] | None:
        """Get disk usage for specified path."""
        try:
            disk = psutil.disk_usage(path)
            return {
                "filesystem": path,
                "size": f"{disk.total / (1024**3):.1f}G",
                "used": f"{disk.used / (1024**3):.1f}G",
                "available": f"{disk.free / (1024**3):.1f}G",
                "percentage": disk.percent,
            }
        except OSError:
            return None

    def get_load_average(self) -> dict[str, float] | None:
        """Get system load average."""
        try:
            load = psutil.getloadavg()
            return {
                "load_1min": load[0],
                "load_5min": load[1],
                "load_15min": load[2],
            }
        except (OSError, AttributeError):
            return None

    def get_service_status(
        self, services: list[str] | None = None
    ) -> dict[str, str]:
        """
        Get status of systemd services.

        Args:
            services: List of service names, or None to use configured services

        Returns:
            Dict mapping service name to status (active/inactive/failed)
        """
        if services is None:
            services = SERVICE_CONFIG.get("critical_services", []) + SERVICE_CONFIG.get(
                "important_services", []
            )

        if not services:
            return {}

        result: dict[str, str] = {}
        for service in services:
            try:
                proc = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                result[service] = proc.stdout.strip() or "unknown"
            except (subprocess.SubprocessError, OSError):
                result[service] = "error"

        return result

    def collect_all_metrics(self) -> dict[str, Any]:
        """Collect all available metrics."""
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_temp": self.get_cpu_temperature(),
            "memory": self.get_memory_stats(),
            "disk": self.get_disk_stats(),
            "load": self.get_load_average(),
            "services": self.get_service_status(),
        }


class RemoteMetricsCollector:
    """Remote metrics collector via SSH."""

    def __init__(
        self,
        host: str,
        user: str = "admin",
        key_path: str | None = None,
    ) -> None:
        self.host = host
        self.user = user
        self.key_path = key_path or SSH_CONFIG.get("key_path", "~/.ssh/id_ed25519")

    def ssh_command(
        self, command: str, timeout: int = SSH_COMMAND_TIMEOUT
    ) -> str | None:
        """
        Execute command via SSH with retry logic.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds

        Returns:
            Command stdout, or None on failure
        """
        ssh_args = [
            "ssh",
            "-i",
            str(Path(self.key_path).expanduser()),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
            f"{self.user}@{self.host}",
            command,
        ]

        for attempt in range(MAX_RETRIES):
            try:
                result = subprocess.run(
                    ssh_args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )

                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    print(f"SSH command failed (rc={result.returncode}): {result.stderr.strip()}")
                    return None

            except subprocess.TimeoutExpired:
                print(f"SSH timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY**attempt
                    print(f"Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    return None

            except OSError as e:
                print(f"SSH error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY**attempt
                    time.sleep(delay)
                else:
                    return None

        return None

    def get_cpu_temperature(self) -> float | None:
        """Get CPU temperature from remote device."""
        output = self.ssh_command("vcgencmd measure_temp 2>/dev/null || cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
        if output:
            # Try vcgencmd format first
            if "temp=" in output:
                try:
                    return float(output.replace("temp=", "").replace("'C", ""))
                except ValueError:
                    pass
            # Try raw millidegrees format
            try:
                return float(output) / 1000
            except ValueError:
                pass
        return None

    def get_memory_stats(self) -> dict[str, Any] | None:
        """Get memory usage from remote device."""
        output = self.ssh_command("free -m | head -2 | tail -1")
        if output:
            parts = output.split()
            if len(parts) >= 3:
                try:
                    total = int(parts[1])
                    used = int(parts[2])
                    return {
                        "total_mb": total,
                        "used_mb": used,
                        "free_mb": total - used,
                        "percentage": round((used / total) * 100, 1),
                    }
                except (ValueError, ZeroDivisionError):
                    pass
        return None

    def get_disk_stats(self) -> dict[str, Any] | None:
        """Get disk usage from remote device."""
        output = self.ssh_command("df -h / | tail -1")
        if output:
            parts = output.split()
            if len(parts) >= 5:
                try:
                    return {
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "percentage": int(parts[4].replace("%", "")),
                    }
                except (ValueError, IndexError):
                    pass
        return None

    def get_load_average(self) -> dict[str, float] | None:
        """Get load average from remote device."""
        output = self.ssh_command("uptime")
        if output and "load average:" in output:
            match = re.search(r"load average: ([\d.]+), ([\d.]+), ([\d.]+)", output)
            if match:
                try:
                    return {
                        "load_1min": float(match.group(1)),
                        "load_5min": float(match.group(2)),
                        "load_15min": float(match.group(3)),
                    }
                except ValueError:
                    pass
        return None

    def get_service_status(
        self, services: list[str] | None = None
    ) -> dict[str, str]:
        """Get service status from remote device."""
        if services is None:
            services = SERVICE_CONFIG.get("critical_services", []) + SERVICE_CONFIG.get(
                "important_services", []
            )

        if not services:
            return {}

        # Security: Quote service names to prevent command injection
        service_list = " ".join(shlex.quote(s) for s in services)
        output = self.ssh_command(f"systemctl is-active {service_list}")
        if output:
            statuses = output.split("\n")
            return dict(zip(services, statuses, strict=False))
        return {}

    def collect_all_metrics(self) -> dict[str, Any]:
        """Collect all metrics from remote device."""
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "host": self.host,
            "cpu_temp": self.get_cpu_temperature(),
            "memory": self.get_memory_stats(),
            "disk": self.get_disk_stats(),
            "load": self.get_load_average(),
            "services": self.get_service_status(),
        }


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Collect system metrics")
    parser.add_argument(
        "--remote",
        "-r",
        metavar="HOST",
        help="Collect from remote host via SSH",
    )
    parser.add_argument(
        "--user",
        "-u",
        default="admin",
        help="SSH username (default: admin)",
    )
    parser.add_argument(
        "--key",
        "-k",
        help="SSH key path",
    )
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if args.remote:
        collector = RemoteMetricsCollector(
            host=args.remote,
            user=args.user,
            key_path=args.key,
        )
    else:
        collector = MetricsCollector()

    metrics = collector.collect_all_metrics()

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(f"Timestamp: {metrics.get('timestamp')}")
        if metrics.get("host"):
            print(f"Host: {metrics['host']}")
        print(f"CPU Temp: {metrics.get('cpu_temp', 'N/A')}°C")
        if metrics.get("memory"):
            print(f"Memory: {metrics['memory']['percentage']}% ({metrics['memory']['used_mb']}/{metrics['memory']['total_mb']} MB)")
        if metrics.get("disk"):
            print(f"Disk: {metrics['disk']['percentage']}% ({metrics['disk']['used']}/{metrics['disk']['size']})")
        if metrics.get("load"):
            print(f"Load: {metrics['load']['load_1min']:.2f} / {metrics['load']['load_5min']:.2f} / {metrics['load']['load_15min']:.2f}")
        if metrics.get("services"):
            print("Services:")
            for svc, status in metrics["services"].items():
                emoji = "✅" if status == "active" else "❌"
                print(f"  {emoji} {svc}: {status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
