# Setup Guide

Complete installation and configuration guide for telegram-multi-device-monitor.

## Prerequisites

### System Requirements
- **OS**: Linux (tested on Ubuntu 20.04+, Debian 11+, Raspberry Pi OS)
- **Python**: 3.10 or higher
- **Bash**: 5.0 or higher
- **RAM**: Minimum 512MB (1GB+ recommended for full bot)

### Required Tools
```bash
# Check Python version
python3 --version  # Should be 3.10+

# Install required system packages
sudo apt install python3-pip curl jq
```

## Platform-Specific Notes

### Ubuntu 20.04 LTS (Focal)
```bash
# Python 3.10+ requires deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv
python3.10 -m venv venv && source venv/bin/activate
```

### Ubuntu 22.04/24.04 LTS (Jammy/Noble)
```bash
# Python 3.10+ is native
sudo apt install python3 python3-pip python3-venv
```

### Debian 11 (Bullseye)
```bash
# Python 3.9 is default; use backports for 3.10+
echo "deb http://deb.debian.org/debian bullseye-backports main" | sudo tee /etc/apt/sources.list.d/backports.list
sudo apt update
sudo apt install -t bullseye-backports python3.10 python3.10-venv
```

### Debian 12 (Bookworm)
```bash
# Python 3.11 is native - compatible
sudo apt install python3 python3-pip python3-venv
```

### Raspberry Pi OS (Bullseye/Bookworm)
```bash
# 64-bit OS recommended for Python 3.10+ native support
# Check architecture:
uname -m  # Should show aarch64 for 64-bit

# For Pi Zero 2W with limited RAM, use alert_bot.py (~25MB)
# Adjust MemoryMax in systemd service if needed:
# MemoryMax=150M  (default: 200M)
```

### Telegram Bot Setup
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **API Token** (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. Get your **Chat ID**:
   - Message [@userinfobot](https://t.me/userinfobot)
   - It will reply with your user ID

## Quick Install

### Option 1: Automated Installation
```bash
# Clone repository
git clone https://github.com/fidpa/telegram-multi-device-monitor.git
cd telegram-multi-device-monitor

# Run installer
sudo ./install.sh
```

### Option 2: Manual Installation
```bash
# Clone repository
git clone https://github.com/fidpa/telegram-multi-device-monitor.git
cd telegram-multi-device-monitor

# Install Python dependencies
pip3 install -r requirements.txt

# Create directories
sudo mkdir -p /opt/telegram-monitor /etc/telegram-monitor /var/log/telegram-monitor

# Copy files
sudo cp -r src /opt/telegram-monitor/
sudo cp config/*.example /etc/telegram-monitor/
```

## Configuration

### 1. Main Configuration (Required)

Copy and edit the main config:
```bash
sudo cp config/telegram_config.yml.example /etc/telegram-monitor/telegram_config.yml
sudo nano /etc/telegram-monitor/telegram_config.yml
```

Essential settings:
```yaml
bot:
  system_name: "My Server"
  system_prefix: "[SERVER]"

telegram:
  token: "YOUR_BOT_TOKEN_HERE"
  chat_id: "YOUR_CHAT_ID_HERE"
  admin_ids:
    - "YOUR_USER_ID"  # Get from @userinfobot
```

### 2. Service Monitoring (Recommended)

Configure which services to monitor:
```bash
sudo cp config/service_monitoring.yml.example /etc/telegram-monitor/service_monitoring.yml
sudo nano /etc/telegram-monitor/service_monitoring.yml
```

Example:
```yaml
critical_services:
  - docker
  - nginx
  - ssh

allowed_restart:
  - docker
  - nginx
```

### 3. SSH Targets (Optional)

For remote monitoring via SSH:
```bash
sudo cp config/ssh_targets.yml.example /etc/telegram-monitor/ssh_targets.yml
sudo nano /etc/telegram-monitor/ssh_targets.yml
```

### 4. Secure Configuration Files
```bash
sudo chmod 600 /etc/telegram-monitor/*.yml
sudo chown root:root /etc/telegram-monitor/*.yml
```

## Running the Bot

### Direct Execution
```bash
# Set config directory
export TELEGRAM_CONFIG_DIR=/etc/telegram-monitor

# Run interactive bot
python3 /opt/telegram-monitor/src/interactive_bot.py

# Or run lightweight alert bot
python3 /opt/telegram-monitor/src/alert_bot.py
```

### As systemd Service

```bash
# Copy service file
sudo cp systemd/telegram-interactive-bot.service.example \
     /etc/systemd/system/telegram-interactive-bot.service

# Edit if needed
sudo nano /etc/systemd/system/telegram-interactive-bot.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable telegram-interactive-bot
sudo systemctl start telegram-interactive-bot

# Check status
sudo systemctl status telegram-interactive-bot
```

## Verification

### Test Configuration
```bash
# Test config loading
python3 -c "
from src.config_loader import load_config, validate_config
c = load_config()
errors = validate_config(c)
print('Errors:', errors if errors else 'None')
"
```

### Test Telegram Connection
```bash
# Send test message
./src/simple_sender.sh "Test message from telegram-monitor"
```

### Test Commands
1. Open Telegram
2. Message your bot with `/start`
3. Try `/status` to see system metrics

## Environment Variables

Override config file settings with environment variables:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot API token |
| `TELEGRAM_CHAT_ID` | Target chat ID |
| `TELEGRAM_ADMIN_IDS` | Comma-separated admin IDs |
| `TELEGRAM_CONFIG_DIR` | Config directory path |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) |

## Security Best Practices

### 1. Restrict Admin Access
Only add trusted users to `admin_ids`:
```yaml
telegram:
  admin_ids:
    - "123456789"  # Only your ID
```

### 2. Limit Restartable Services
Only allow safe services:
```yaml
# service_monitoring.yml
allowed_restart:
  - nginx
  - docker
  # NEVER add: sshd, systemd-networkd
```

### 3. Use systemd Hardening
The provided service files include security restrictions:
- `ProtectSystem=strict`
- `NoNewPrivileges=true`
- `PrivateTmp=true`

### 4. Secure Token Storage
For production, consider using:
- Environment files with restricted permissions
- Secret managers (Vaultwarden, HashiCorp Vault)
- `token_fetcher.sh` for dynamic token retrieval

## Updating

```bash
# Pull latest
cd /path/to/telegram-multi-device-monitor
git pull

# Update dependencies
pip3 install -r requirements.txt --upgrade

# Restart service
sudo systemctl restart telegram-interactive-bot
```

## Uninstallation

```bash
# Stop service
sudo systemctl stop telegram-interactive-bot
sudo systemctl disable telegram-interactive-bot

# Remove files
sudo rm /etc/systemd/system/telegram-*.service
sudo rm -rf /opt/telegram-monitor

# Keep config and logs (optional)
# sudo rm -rf /etc/telegram-monitor /var/log/telegram-monitor
```

## Next Steps

- [ARCHITECTURE.md](ARCHITECTURE.md) - Understand the system design
- [API_REFERENCE.md](API_REFERENCE.md) - All commands and options
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
