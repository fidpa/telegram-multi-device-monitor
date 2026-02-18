# Source Components

This directory contains the main components of telegram-multi-device-monitor.

## Component Overview

| Component | Language | Purpose | Memory |
|-----------|----------|---------|--------|
| `interactive_bot.py` | Python | Full-featured monitoring bot | ~50MB |
| `alert_bot.py` | Python | Lightweight alert bot (low-memory) | ~25MB |
| `prometheus_webhook.py` | Python | Prometheus alert receiver | ~30MB |
| `simple_sender.sh` | Bash | CLI message sender | Minimal |
| `token_fetcher.sh` | Bash | Secret manager integration | Minimal |
| `alert_sender.py` | Python | Formatted alert sender | ~20MB |
| `metrics_collector.py` | Python | Local/remote metrics | ~15MB |
| `config_loader.py` | Python | YAML configuration loader | ~5MB |

## Quick Start

### Interactive Bot (Full Features)
```bash
# Configure
cp ../config/telegram_config.yml.example ../config/telegram_config.yml
# Edit telegram_config.yml with your bot token and chat ID

# Run
python3 interactive_bot.py
```

### Lightweight Alert Bot (Low Memory)
```bash
# For devices with limited RAM (512MB or less)
python3 alert_bot.py
```

### Simple Message Sender (CLI)
```bash
# Send a message
./simple_sender.sh "Hello from my server!"

# Read from file
./simple_sender.sh -f /path/to/message.txt

# Pipe input
echo "Alert: disk full" | ./simple_sender.sh -s
```

### Prometheus Webhook
```bash
# Start webhook server
python3 prometheus_webhook.py

# Configure Alertmanager to send to http://localhost:9094/webhook
```

## Dependencies

### Python (requirements.txt)
- `python-telegram-bot>=20.0`
- `flask>=3.0.0`
- `pyyaml>=6.0`
- `psutil>=5.9.0`
- `aiohttp>=3.9.0`

### Bash
- `curl` - HTTP requests
- `jq` - JSON parsing (optional, improves encoding)
- `yq` - YAML parsing (optional, for config loading)

## Configuration

All components use the shared configuration system in `../config/`:

1. `telegram_config.yml` - Bot credentials and settings
2. `service_monitoring.yml` - Services to monitor
3. `ssh_targets.yml` - Remote SSH targets (optional)
4. `network_config.yml` - Network monitoring (optional)

## Library Files

The `lib/` subdirectory contains shared Bash libraries:

- `logging.sh` - Structured logging functions
- `alerts.sh` - Alert rate limiting and deduplication
- `file_utils.sh` - Secure file operations

## Security Notes

1. **Never commit credentials** - Use environment variables or config files
2. **Restrict config permissions** - `chmod 600 telegram_config.yml`
3. **Use admin whitelist** - Limit who can run privileged commands
4. **Audit allowed services** - Only allow safe services for restart
