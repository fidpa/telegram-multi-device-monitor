# telegram-multi-device-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Bash](https://img.shields.io/badge/Bash-5.0%2B-green?logo=gnu-bash)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux)](https://kernel.org/)
[![CI](https://github.com/fidpa/telegram-multi-device-monitor/actions/workflows/lint.yml/badge.svg)](https://github.com/fidpa/telegram-multi-device-monitor/actions)
![Last Commit](https://img.shields.io/github/last-commit/fidpa/telegram-multi-device-monitor)

Production-ready Telegram bot framework for multi-device system monitoring. Monitor servers, Raspberry Pis, NAS devices, and more through Telegram with alerts, metrics, and remote management.

**The Problem**: Managing multiple Linux devices means SSH-ing into each one separately to check status, restart services, or investigate alerts. From a phone with a small keyboard and unreliable mobile connection, this becomes impractical. After months of running this on a Pi 5 router, a NAS server, and a fleet of Pi Zeros, I've extracted the monitoring stack into a reusable framework with 5 independently deployable components — from a full-featured 50MB interactive bot down to a 25MB alert bot that fits on a Pi Zero with 512MB RAM.

## Features

- **Interactive Bot** — Full monitoring with 15+ commands (`/status`, `/services`, `/docker`, `/metrics`, `/logs`, `/restart`)
- **Alert Bot** — Lightweight variant for devices with 512MB RAM (~25MB footprint, `__slots__` optimized)
- **Prometheus Webhook** — Alertmanager integration with deduplication and customizable templates
- **SSH-Based Collection** — Agent-less remote monitoring (no software installation on target devices)
- **Alert Deduplication** — Rate limiting and state persistence across restarts to prevent alert fatigue
- **Security Hardened** — Admin whitelist, optional 2FA, service restart whitelist, systemd sandboxing
- **YAML Configuration** — Centralized config with environment variable overrides and validation

## Known Limitations

> **Transparent documentation of trade-offs**:
>
> - SSH remote monitoring uses `StrictHostKeyChecking=accept-new` (Trust On First Use) — secure enough for homelabs, but not for zero-trust environments. Use `StrictHostKeyChecking=yes` with pre-distributed keys for higher security.
> - Alert state is file-based (JSON). For high-volume environments (>100 alerts/hour), consider a proper database.
> - The interactive bot polls Telegram (long polling). For webhook-based deployments behind a reverse proxy, additional configuration is needed.
> - 2FA is optional and token-based. It is not a replacement for SSH key-based authentication on the target devices.

## Quick Start

### Prerequisites

- Python 3.10+
- Bash 5.0+
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Optional: `jq`, `curl` (for Bash components)

### Setup

```bash
# Clone the repository
git clone https://github.com/fidpa/telegram-multi-device-monitor.git
cd telegram-multi-device-monitor

# Install dependencies
pip3 install -r requirements.txt

# Configure
cp config/telegram_config.yml.example config/telegram_config.yml
# Edit with your bot token, chat ID, and admin IDs

# Run the interactive bot
python3 src/interactive_bot.py

# Or the lightweight alert bot (for Pi Zero / low-memory devices)
python3 src/alert_bot.py
```

### Automated Installation

```bash
# Interactive installer (creates user, config dirs, systemd services)
sudo ./install.sh

# Verify dependencies only
./install.sh --check

# Uninstall
sudo ./install.sh --uninstall
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram API                             │
└─────────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Interactive Bot │ │   Alert Bot     │ │ Prometheus      │
│ (Full Features) │ │ (Low Memory)    │ │ Webhook         │
│    ~50MB RAM    │ │    ~25MB RAM    │ │    ~30MB RAM    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
           │                  │                  │
           └──────────────────┼──────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Local Metrics  │ │  Remote (SSH)   │ │  Alertmanager   │
│    (psutil)     │ │   Metrics       │ │    Alerts       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Design Decisions

**Why 5 components instead of 1 monolith?** A Pi Zero with 512MB RAM cannot run a 50MB bot alongside its primary workload. The alert bot (~25MB) handles the common case. The interactive bot runs on the server where resources are available. The Prometheus webhook integrates with existing monitoring stacks. Each component is independently deployable — you pick what you need.

**Why Python + Bash?** Python for the bots (async I/O, Telegram library, psutil for metrics). Bash for the CLI sender and libraries (zero dependencies, runs in cron jobs and scripts without a Python runtime). The YAML config loader bridges both worlds.

**Why long polling instead of webhooks?** Long polling works behind NAT without a public IP or reverse proxy. Most homelab setups don't expose services to the internet. Webhook mode can be configured for environments that need it.

**Why file-based alert state?** SQLite or Redis would add dependencies and complexity. A JSON file in `/var/lib/telegram-monitor/` survives reboots (StateDirectory, not RuntimeDirectory) and is sufficient for <100 alerts/hour.

## Components

| Component | File | Purpose | RAM | Use Case |
|-----------|------|---------|-----|----------|
| **Interactive Bot** | `interactive_bot.py` | Full monitoring with 15+ commands | ~50MB | Servers, workstations |
| **Alert Bot** | `alert_bot.py` | Lightweight alert processing | ~25MB | Raspberry Pi Zero, constrained devices |
| **Prometheus Webhook** | `prometheus_webhook.py` | Alertmanager receiver | ~30MB | Existing Prometheus stacks |
| **Metrics Collector** | `metrics_collector.py` | Local + SSH metric collection | ~15MB | Agent-less remote monitoring |
| **Simple Sender** | `simple_sender.sh` | CLI message sender | Minimal | Cron jobs, scripts, one-liners |
| **Alert Sender** | `alert_sender.py` | Pre-formatted status messages | ~15MB | Scheduled system reports |
| **Config Loader** | `config_loader.py` | YAML config with env overrides | Library | Used by all Python components |

### Bash Libraries

| Library | Lines | Purpose |
|---------|-------|---------|
| `lib/alerts.sh` | 266 | Alert deduplication and rate limiting with state persistence |
| `lib/file_utils.sh` | 261 | Atomic file operations, safe path handling, temp file management |
| `lib/logging.sh` | 206 | Structured logging with configurable targets and levels |

## Command Quick Reference

| Command | Description | Access |
|---------|-------------|--------|
| `/status` (`/s`) | System overview (CPU, RAM, disk, temp) | All |
| `/services` | systemd service health check | All |
| `/docker` | Docker container status | All |
| `/metrics` | Performance with visual bars | All |
| `/logs [n] [svc]` | View recent service logs | All |
| `/restart <svc>` | Restart service (with confirmation) | Admin |
| `/memory` | Bot memory usage | All |
| `/help` | Show all commands | All |

Full command reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

## Configuration

Configuration files are in YAML format with environment variable overrides:

```yaml
# config/telegram_config.yml
bot:
  system_name: "My Server"
  system_prefix: "[SERVER]"
  log_level: "INFO"

telegram:
  token: "YOUR_BOT_TOKEN"       # or env: TELEGRAM_BOT_TOKEN
  chat_id: "YOUR_CHAT_ID"       # or env: TELEGRAM_CHAT_ID
  admin_ids:
    - "123456789"

security:
  restart_whitelist:
    - "nginx"
    - "docker"
  enable_2fa: false
```

Additional config templates:
- `service_monitoring.yml.example` — Critical service definitions
- `ssh_targets.yml.example` — Remote monitoring targets
- `network_config.yml.example` — Network monitoring thresholds

See [docs/SETUP.md](docs/SETUP.md) for all configuration options.

## Use Cases

### Perfect for

- ✅ **Homelab monitoring** — Check all devices from Telegram, no SSH needed
- ✅ **Raspberry Pi fleets** — Alert bot runs on 512MB devices alongside primary workload
- ✅ **Self-hosted infrastructure** — Docker, systemd, network monitoring in one bot
- ✅ **Prometheus integration** — Forward Alertmanager events to Telegram
- ✅ **Script integration** — `simple_sender.sh` for cron jobs and backup scripts

### Not recommended for

- ❌ **Enterprise monitoring** (1000+ nodes) — Use Datadog, Grafana Cloud, or PagerDuty
- ❌ **Public-facing alerting** — This is for private Telegram chats/groups
- ❌ **Windows servers** — Linux-only (psutil basics work, but systemd/SSH features don't)
- ❌ **Real-time dashboards** — Use Grafana for visualization, this is for alerts and quick checks

### vs. Alternatives

| Solution | Pros | Cons |
|----------|------|------|
| **Uptime Kuma** | Web UI, beautiful dashboard | No Telegram commands, no remote management |
| **Grafana OnCall** | Enterprise-grade, escalation | Complex setup, overkill for homelab |
| **Healthchecks.io** | Simple cron monitoring | No system metrics, no interactive commands |
| **Netdata** | Deep metrics, auto-discovery | Heavy (300MB+), no Telegram interaction |
| **This project** | Interactive commands, low-memory, 5 components | No web UI, Linux-only |

## Security

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| 1 | Admin whitelist | Only approved Telegram user IDs can run privileged commands |
| 2 | Service whitelist | Only explicitly allowed services can be restarted |
| 3 | Optional 2FA | Token-based second factor for admin commands |
| 4 | Token masking | Credential status logged without exposing values |
| 5 | systemd sandboxing | `ProtectSystem=strict`, `NoNewPrivileges`, `PrivateTmp`, `MemoryMax` |
| 6 | SSH key-only auth | Remote monitoring uses key-based authentication |
| 7 | Config permissions | Config files created with `chmod 600` |
| 8 | Input sanitization | sed/grep injection prevention in all user-facing inputs |

Full security policy: [SECURITY.md](SECURITY.md)

## Repository Structure

```
telegram-multi-device-monitor/
├── src/
│   ├── interactive_bot.py      # Full-featured monitoring bot (922 LOC)
│   ├── alert_bot.py            # Lightweight alert bot (588 LOC)
│   ├── prometheus_webhook.py   # Alertmanager receiver (387 LOC)
│   ├── metrics_collector.py    # Local + SSH metric collection (453 LOC)
│   ├── alert_sender.py         # Formatted status messages (345 LOC)
│   ├── config_loader.py        # YAML config with env overrides (307 LOC)
│   ├── simple_sender.sh        # CLI message sender (332 LOC)
│   ├── token_fetcher.sh        # Secret manager integration (269 LOC)
│   └── lib/
│       ├── alerts.sh           # Alert deduplication and rate limiting
│       ├── file_utils.sh       # Atomic file operations
│       └── logging.sh          # Structured logging
├── config/
│   ├── telegram_config.yml.example
│   ├── service_monitoring.yml.example
│   ├── ssh_targets.yml.example
│   └── network_config.yml.example
├── systemd/
│   ├── telegram-interactive-bot.service.example
│   ├── telegram-alert-bot.service.example
│   ├── telegram-metrics-collector.service.example
│   └── telegram-prometheus-webhook.service.example
├── docs/
│   ├── SETUP.md                # Installation and configuration
│   ├── ARCHITECTURE.md         # Design and component overview
│   ├── API_REFERENCE.md        # Commands and configuration reference
│   ├── EXAMPLES.md             # Usage examples
│   └── TROUBLESHOOTING.md      # Common issues and solutions
├── .github/workflows/
│   └── lint.yml                # CI: black, mypy, shellcheck, yamllint
├── install.sh                  # Interactive installer
├── requirements.txt            # Python dependencies
├── SECURITY.md                 # Security policy and best practices
├── CONTRIBUTING.md             # Contribution guidelines
├── CODE_OF_CONDUCT.md          # Community standards
├── CHANGELOG.md                # Version history
└── LICENSE                     # MIT License
```

## Documentation

| Document | Description |
|----------|-------------|
| [SETUP.md](docs/SETUP.md) | Installation, configuration, systemd setup |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design goals, component interaction, data flow |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | All commands, config options, environment variables |
| [EXAMPLES.md](docs/EXAMPLES.md) | Practical usage examples |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |

## Requirements

**Minimum**:
- Python 3.10+ (for type hints and modern syntax)
- Bash 5.0+ (for Bash components)
- 512MB RAM (alert bot) or 256MB+ free (interactive bot)
- systemd (for service management)

**Python packages**:
- `python-telegram-bot` >= 21.0
- `psutil` >= 5.9.0
- `flask` >= 3.0.0 (Prometheus webhook only)
- `pyyaml` >= 6.0
- `aiohttp` >= 3.9.0

**Optional**:
- `jq`, `curl` (for Bash components)
- Prometheus + Alertmanager (for webhook integration)

## Compatibility

**Fully supported**:
- Ubuntu 22.04 LTS, 24.04 LTS
- Debian 11 (Bullseye), 12 (Bookworm)
- Raspberry Pi OS (32-bit and 64-bit)

**Should work** (untested):
- Other systemd-based distributions
- Fedora, Rocky Linux, Arch Linux
- WSL2 (without systemd features)

**Not supported**:
- macOS, Windows (use [cc-telegram-bot](https://github.com/fidpa/cc-telegram-bot) for macOS)
- Alpine Linux (musl libc, psutil may need compilation)

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas where help is appreciated**:
- Additional metric collectors (GPU monitoring, ZFS pool status)
- Webhook mode for environments behind reverse proxies
- Grafana dashboard templates for collected metrics
- Testing on additional platforms (Fedora, Rocky Linux, Arch)
- Internationalization (currently English-only bot messages)
- Container-based deployment (Dockerfile)

## License

MIT License — see [LICENSE](LICENSE)

## Author

Marc Allgeier ([@fidpa](https://github.com/fidpa))

**Why I Built This**: I run a Pi 5 as a network gateway, a NAS with 38 Docker containers, and 5 Pi Zeros for monitoring tasks. Checking each device meant SSH-ing in separately — impractical from a phone. I needed something that lets me type `/status` in Telegram and see all devices at a glance, with alerts that don't flood my chat. The 5-component architecture emerged from a real constraint: the Pi Zeros have 512MB RAM and can't run a full monitoring bot. So I built a 25MB alert bot for constrained devices and a full-featured interactive bot for the server.

## See Also

- [cc-telegram-bot](https://github.com/fidpa/cc-telegram-bot) — Claude Code remote access via Telegram (24 security layers)
- [ubuntu-server-security](https://github.com/fidpa/ubuntu-server-security) — Server hardening (14 components, CIS Benchmark)
- [bash-production-toolkit](https://github.com/fidpa/bash-production-toolkit) — Production-ready Bash libraries
- [linux-monitoring-templates](https://github.com/fidpa/linux-monitoring-templates) — Bash/Python monitoring templates

## Support

- **Issues**: [GitHub Issues](https://github.com/fidpa/telegram-multi-device-monitor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/fidpa/telegram-multi-device-monitor/discussions)

---

**Production-tested since 2025** | 11 source files | ~4,300 lines of code | ~2,500 lines of documentation
