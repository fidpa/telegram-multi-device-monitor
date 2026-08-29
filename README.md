# telegram-multi-device-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Bash](https://img.shields.io/badge/Bash-5.0%2B-green?logo=gnu-bash)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux)](https://kernel.org/)
[![CI](https://github.com/fidpa/telegram-multi-device-monitor/actions/workflows/lint.yml/badge.svg)](https://github.com/fidpa/telegram-multi-device-monitor/actions)
![Last Commit](https://img.shields.io/github/last-commit/fidpa/telegram-multi-device-monitor)

A Telegram bot framework for monitoring several Linux devices: servers, Raspberry
Pis, NAS boxes. It sends alerts, reports metrics, and restarts whitelisted
services from a chat window.

Checking a handful of devices means opening an SSH session per device, which is
awkward from a phone on a mobile connection. This repository is the monitoring
stack I run on a Pi 5 router, a NAS, and a few Pi Zeros, extracted into eight
components under `src/`. Four of them ship a systemd unit, one is a plain CLI
sender for cron jobs, and the split exists because a Pi Zero with 512MB RAM
cannot host the full interactive bot next to its actual workload.

## Features

- **Interactive bot** with eight commands: `/start`, `/status`, `/services`,
  `/docker`, `/metrics`, `/logs`, `/restart`, `/help`. All but `/start` carry a
  single-letter alias
- **Alert bot** for low-memory devices: `__slots__` on the config, GC, and
  batching classes, plus a `MemoryMax=50M` systemd unit
- **Prometheus webhook**: an Alertmanager receiver with fingerprint-based
  deduplication and a message template per alertname (`ServiceDown`, `HighCPU`,
  `HighMemory`, and a default)
- **SSH-based collection**: remote metrics over `ssh` with key auth, no agent
  installed on the target device
- **Alert deduplication**: a dedup window plus a per-hour rate limit, both backed
  by a JSON state file that survives a restart
- **Access control**: admin IDs for privileged commands, a restart whitelist read
  from `service_monitoring.yml`, and systemd sandboxing in every unit
- **YAML configuration** with environment variable overrides and startup
  validation

## Known Limitations

> - SSH remote monitoring uses `StrictHostKeyChecking=accept-new` (trust on first
>   use). That is fine for a homelab, not for a zero-trust network. Set
>   `StrictHostKeyChecking=yes` with pre-distributed host keys if you need more.
> - Two-factor auth for `/restart` exists in the alert bot only. The interactive
>   bot checks the admin ID and the service whitelist, and nothing else.
> - Alert state is a JSON file. Above roughly 100 alerts per hour a real database
>   would be the better fit.
> - The webhook writes its dedup state to `/tmp/prometheus-webhook` unless
>   `STATE_DIR` says otherwise. The shipped systemd unit points it at
>   `/var/lib/telegram-monitor`; a manual start does not.
> - The interactive bot uses long polling. Webhook mode behind a reverse proxy is
>   not wired up in this repository.
> - The RAM figures below are rough resident-set observations from my own
>   devices (Raspberry Pi OS and Ubuntu, CPython 3.11), not a benchmark. Treat
>   them as an order of magnitude.

## Quick Start

### Prerequisites

- Python 3.10+
- Bash 5.0+
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Optional: `jq`, `curl` (for the Bash components)

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
chmod 600 config/telegram_config.yml

# Run the interactive bot
python3 src/interactive_bot.py

# Or the lightweight alert bot (for Pi Zero and other low-memory devices)
python3 src/alert_bot.py
```

### Automated Installation

`install.sh --help`, quoted:

```
Usage: ./install.sh [OPTION]

Options:
    (no option)     Interactive installation
    --check         Check dependencies only
    --uninstall     Remove installation
    --help          Show this help
```

The interactive run creates the `telegram-monitor` service user, the config, log,
and state directories under `/etc`, `/var/log`, and `/var/lib`, copies `src/` to
`/opt/telegram-monitor`, and installs the systemd units. Those paths and the user
name are constants in the script, not options.

```bash
sudo ./install.sh          # full installation
./install.sh --check       # dependencies only, no changes
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

**Why several components instead of one binary?** A Pi Zero with 512MB RAM cannot
run the interactive bot next to its primary workload, so the alert bot covers the
common case there and the interactive bot runs on the server. The webhook exists
for hosts that already have Alertmanager. Each component starts on its own; you
deploy the ones you need.

**Why Python and Bash?** The bots need async I/O, the Telegram library, and
psutil, so they are Python. The CLI sender and the three libraries under
`src/lib/` are Bash, which lets a cron job or a backup script send a message
without a Python runtime. `config_loader.py` and the YAML files are what the two
halves share.

**Why long polling instead of webhooks?** Long polling works behind NAT without a
public IP or a reverse proxy, which is what most homelab setups have.

**Why file-based alert state?** SQLite or Redis would add a dependency for a
handful of timestamps. The Bash library writes to
`$XDG_STATE_HOME/telegram-monitor` (`~/.local/state/telegram-monitor` by
default), and the webhook writes to `$STATE_DIR`, which its systemd unit sets to
`/var/lib/telegram-monitor` with `StateDirectory=`, so the state outlives a
reboot.

## Components

RAM figures are resident-set observations, see Known Limitations above.

| Component | File | Purpose | RAM | Use Case |
|-----------|------|---------|-----|----------|
| **Interactive Bot** | `interactive_bot.py` | Full monitoring with eight commands | ~50MB | Servers, workstations |
| **Alert Bot** | `alert_bot.py` | Alert processing plus `/restart` with 2FA | ~25MB | Raspberry Pi Zero, constrained devices |
| **Prometheus Webhook** | `prometheus_webhook.py` | Alertmanager receiver (Flask) | ~30MB | Existing Prometheus stacks |
| **Metrics Collector** | `metrics_collector.py` | Local and SSH metric collection | ~15MB | Agent-less remote monitoring |
| **Simple Sender** | `simple_sender.sh` | CLI message sender | Minimal | Cron jobs, scripts, one-liners |
| **Alert Sender** | `alert_sender.py` | Pre-formatted status messages | ~15MB | Scheduled system reports |
| **Token Fetcher** | `token_fetcher.sh` | `ExecStartPre` hook that pulls the token from a secret manager into the runtime dir | Minimal | Hosts that keep the token out of `/etc` |
| **Config Loader** | `config_loader.py` | YAML config with env overrides | Library | Used by all Python components |

### Bash Libraries

| Library | Purpose |
|---------|---------|
| `lib/alerts.sh` | Alert deduplication and rate limiting with state persistence |
| `lib/file_utils.sh` | Atomic file operations, safe path handling, temp file management |
| `lib/logging.sh` | Structured logging with configurable targets and levels |

## Command Quick Reference

Interactive bot. The aliases below are the ones `/help` prints; `/start` has none:

| Command | Description | Access |
|---------|-------------|--------|
| `/status` (`/s`) | System overview (CPU, RAM, disk, temp) | All |
| `/services` (`/v`) | systemd services and Docker containers | All |
| `/docker` (`/d`) | Same handler as `/services`, kept as a habit alias | All |
| `/metrics` (`/m`) | Performance with visual bars | All |
| `/logs` (`/l`) `[lines] [service]` | View recent service logs | All |
| `/restart` (`/r`) `<service>` | Restart a whitelisted service, with a confirmation button | Admin |
| `/help` (`/h`) | Show all commands | All |
| `/start` | Welcome message | All |

The alert bot answers a smaller set and without aliases: `/start`, `/status`,
`/restart`, `/auth` (the 2FA code), and `/memory`.

Full command reference for both bots: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

## Configuration

YAML files with environment variable overrides, excerpt from
`config/telegram_config.yml.example`:

```yaml
bot:
  system_name: "My Server"
  system_prefix: "[SERVER]"
  log_level: "INFO"

telegram:
  token: "YOUR_BOT_TOKEN_HERE"    # or env: TELEGRAM_BOT_TOKEN
  chat_id: "YOUR_CHAT_ID_HERE"    # or env: TELEGRAM_CHAT_ID
  admin_ids:                      # or env: TELEGRAM_ADMIN_IDS
    - "123456789"
  rate_limit_window: 60           # seconds between duplicate alerts
```

The restart whitelist lives in `service_monitoring.yml`, not in the bot config:
`/restart` accepts what `allowed_restart` and `critical_services` list there.

Additional config templates:
- `service_monitoring.yml.example`: critical services and the restart whitelist
- `ssh_targets.yml.example`: remote monitoring targets
- `network_config.yml.example`: network monitoring thresholds

Every option with its default: [config/README.md](config/README.md) and
[docs/SETUP.md](docs/SETUP.md).

## Use Cases

### Perfect for

- ✅ **Homelab monitoring**: check every device from Telegram instead of SSH
- ✅ **Raspberry Pi fleets**: the alert bot fits on a 512MB device next to its
  primary workload
- ✅ **Self-hosted infrastructure**: Docker, systemd, and network checks in one bot
- ✅ **Prometheus integration**: forward Alertmanager events to Telegram
- ✅ **Script integration**: `simple_sender.sh` for cron jobs and backup scripts

### Not recommended for

- ❌ **Enterprise monitoring** (1000+ nodes): use Datadog, Grafana Cloud, or PagerDuty
- ❌ **Public-facing alerting**: this is built for private chats and groups
- ❌ **Windows servers**: Linux only. psutil basics work, systemd and SSH features do not
- ❌ **Real-time dashboards**: use Grafana for visualization, this is for alerts
  and quick checks

### vs. Alternatives

| Solution | Pros | Cons |
|----------|------|------|
| **Uptime Kuma** | Web UI, good-looking dashboard | No Telegram commands, no remote management |
| **Grafana OnCall** | Enterprise-grade, escalation | Complex setup, more than a homelab needs |
| **Healthchecks.io** | Simple cron monitoring | No system metrics, no interactive commands |
| **Netdata** | Deep metrics, auto-discovery | Heavy (300MB+), no Telegram interaction |
| **This project** | Interactive commands, runs on 512MB devices | No web UI, Linux only, 2FA in the alert bot only |

## Security

| Layer | Mechanism | Where |
|-------|-----------|-------|
| 1 | Admin whitelist: only listed Telegram user IDs reach `/restart` | `interactive_bot.py`, `alert_bot.py` |
| 2 | Service whitelist: `/restart` refuses anything outside `allowed_restart` plus `critical_services` | `interactive_bot.py` |
| 3 | Optional 2FA: a one-time code before a restart, alert bot only | `alert_bot.py` |
| 4 | Token masking: logs keep the first 10 characters and drop the rest, admin IDs are logged as a count | `config_loader.py` |
| 5 | systemd sandboxing: `ProtectSystem=strict`, `NoNewPrivileges`, `PrivateTmp`, `MemoryMax` in all four units | `systemd/*.example` |
| 6 | SSH key-only auth for remote collection | `metrics_collector.py` |
| 7 | The installer creates config, log, and state dirs as `chmod 750` owned by the service user; `chmod 600` on the config file itself is a documented setup step | `install.sh`, `config/README.md` |
| 8 | Input handling: service names must match a systemd name pattern, remote command arguments go through `shlex.quote` | `interactive_bot.py`, `metrics_collector.py` |

Full security policy: [SECURITY.md](SECURITY.md)

## Repository Structure

```
telegram-multi-device-monitor/
├── src/
│   ├── interactive_bot.py      # Full-featured monitoring bot
│   ├── alert_bot.py            # Lightweight alert bot with 2FA
│   ├── prometheus_webhook.py   # Alertmanager receiver
│   ├── metrics_collector.py    # Local + SSH metric collection
│   ├── alert_sender.py         # Formatted status messages
│   ├── config_loader.py        # YAML config with env overrides
│   ├── simple_sender.sh        # CLI message sender
│   ├── token_fetcher.sh        # Secret manager integration
│   └── lib/
│       ├── alerts.sh           # Alert deduplication and rate limiting
│       ├── file_utils.sh       # Atomic file operations
│       └── logging.sh          # Structured logging
├── config/
│   ├── telegram_config.yml.example
│   ├── service_monitoring.yml.example
│   ├── ssh_targets.yml.example
│   ├── network_config.yml.example
│   └── README.md               # Every option with its default
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
│   ├── lint.yml                # CI: black, mypy, shellcheck, yamllint
│   └── release.yml             # Release automation
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
| [config/README.md](config/README.md) | Config files, env overrides, file permissions |

## Requirements

**Minimum**:
- Python 3.10+ (for the type-hint syntax used throughout `src/`)
- Bash 5.0+ (for the Bash components)
- 512MB RAM (alert bot) or 256MB+ free (interactive bot)
- systemd (for the shipped units and the service checks)

**Python packages** (see `requirements.txt` for the upper bounds):
- `python-telegram-bot` >= 21.0
- `psutil` >= 5.9.0
- `flask` >= 3.0.0 (Prometheus webhook only)
- `pyyaml` >= 6.0
- `aiohttp` >= 3.9.0
- `requests` >= 2.31.0

**Optional**:
- `jq`, `curl` (for the Bash components)
- Prometheus and Alertmanager (for the webhook)
- `paramiko` >= 3.0.0, commented out in `requirements.txt`, for
  `RemoteMetricsCollector`

## Compatibility

**Fully supported**:
- Ubuntu 22.04 LTS, 24.04 LTS
- Debian 11 (Bullseye), 12 (Bookworm)
- Raspberry Pi OS (32-bit and 64-bit)

**Should work** (untested):
- Other systemd-based distributions
- Fedora, Rocky Linux, Arch Linux
- WSL2 (without the systemd features)

**Not supported**:
- macOS, Windows (use [cc-telegram-bot](https://github.com/fidpa/cc-telegram-bot) on macOS)
- Alpine Linux (musl libc, psutil may need to be compiled)

## Contributing

Contributions welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).

**Areas where help is appreciated**:
- Additional metric collectors (GPU monitoring, ZFS pool status)
- Webhook mode for setups behind a reverse proxy
- 2FA in the interactive bot, matching the alert bot
- Grafana dashboard templates for the collected metrics
- Testing on additional platforms (Fedora, Rocky Linux, Arch)
- Internationalization, the bot messages are English only
- Container-based deployment (Dockerfile)

## License

MIT License, see [LICENSE](LICENSE)

## Author

Marc Allgeier ([@fidpa](https://github.com/fidpa))

The framework grew out of one constraint. The Pi Zeros in my setup have 512MB RAM
and no room for a full bot, so the alert bot had to be small enough to sit next
to their actual job, while the server could carry the interactive one. Everything
else here, the shared config loader, the Bash sender, the dedup state, followed
from having to keep those two in sync.

## See Also

- [cc-telegram-bot](https://github.com/fidpa/cc-telegram-bot): Claude Code remote access via Telegram (24 security layers)
- [ubuntu-server-security](https://github.com/fidpa/ubuntu-server-security): server hardening (14 components, CIS Benchmark)
- [bash-production-toolkit](https://github.com/fidpa/bash-production-toolkit): production-ready Bash libraries
- [linux-monitoring-templates](https://github.com/fidpa/linux-monitoring-templates): Bash and Python monitoring templates

## Support

- **Issues**: [GitHub Issues](https://github.com/fidpa/telegram-multi-device-monitor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/fidpa/telegram-multi-device-monitor/discussions)
