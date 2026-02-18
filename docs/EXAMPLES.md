# Practical Examples

Real-world examples for common telegram-multi-device-monitor setups.

---

## Example 1: Single Home Server Monitoring

A typical setup for a home server running Docker containers.

### Configuration

**config/telegram_config.yml**
```yaml
bot:
  system_name: "Home Server"
  system_prefix: "[HOME]"

telegram:
  token: "YOUR_BOT_TOKEN_HERE"
  chat_id: "YOUR_CHAT_ID_HERE"
  admin_ids:
    - "YOUR_USER_ID"

monitoring:
  interfaces:
    - eth0
```

**config/service_monitoring.yml**
```yaml
critical_services:
  - docker
  - nginx
  - ssh

important_services:
  - containerd
  - fail2ban

allowed_restart:
  - docker
  - nginx
```

### Run
```bash
python3 src/interactive_bot.py
```

### Commands to Use
- `/status` - Overall system health
- `/docker` - Container status
- `/services` - Service health check
- `/restart nginx` - Restart nginx (admin only)

---

## Example 2: Raspberry Pi Fleet Monitoring

Monitor multiple Raspberry Pi devices from a central point using SSH.

### Network Setup
```
Central Monitor (Pi 4)     Remote Devices
     │                         │
     ├──────SSH────────> Pi Zero #1 (192.168.1.11)
     ├──────SSH────────> Pi Zero #2 (192.168.1.12)
     └──────SSH────────> Pi 3 (192.168.1.13)
```

### SSH Key Setup
```bash
# On central monitor, generate key
ssh-keygen -t ed25519 -C "telegram-monitor"

# Copy to each device
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@192.168.1.11
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@192.168.1.12
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@192.168.1.13
```

### Configuration

**config/ssh_targets.yml**
```yaml
ssh_user: pi
ssh_timeout: 10

ssh_targets:
  - host: 192.168.1.11
    name: "Pi Zero Bedroom"
  - host: 192.168.1.12
    name: "Pi Zero Kitchen"
  - host: 192.168.1.13
    name: "Pi 3 Garage"
```

### Commands
```bash
# Collect metrics from all devices
python3 src/metrics_collector.py --remote 192.168.1.11
python3 src/metrics_collector.py --remote 192.168.1.12
python3 src/metrics_collector.py --remote 192.168.1.13
```

---

## Example 3: Prometheus Alertmanager Integration

Receive Prometheus alerts via Telegram.

### Architecture
```
Prometheus ──> Alertmanager ──> telegram-webhook ──> Telegram
```

### Prometheus Alert Rule
**prometheus/rules/host.yml**
```yaml
groups:
  - name: host
    rules:
      - alert: HighCPU
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
          description: "CPU usage is above 80% for 5 minutes"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 10
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Less than 10% disk space remaining"
```

### Alertmanager Configuration
**alertmanager.yml**
```yaml
global:
  resolve_timeout: 5m

route:
  receiver: telegram
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: telegram
    webhook_configs:
      - url: http://localhost:9094/webhook
        send_resolved: true
```

### Start Webhook Receiver
```bash
# Using systemd
sudo systemctl start telegram-prometheus-webhook

# Or directly
python3 src/prometheus_webhook.py
```

### Telegram Output
```
🚨 FIRING [critical]
DiskSpaceLow

💻 myserver:9100
📝 Less than 10% disk space remaining

🕐 Started: 2025-01-15 14:32:00
```

---

## Example 4: Alert-Only Mode for Constrained Devices

Ultra-lightweight setup for Raspberry Pi Zero or similar devices with limited RAM.

### Memory Comparison
| Mode | RAM Usage | Features |
|------|-----------|----------|
| `interactive_bot.py` | ~50MB | Full features |
| `alert_bot.py` | ~25MB | Alerts + basic commands |
| `simple_sender.sh` | <1MB | Send only |

### Configuration for Pi Zero
**config/telegram_config.yml**
```yaml
bot:
  system_name: "Pi Zero Sensor"
  system_prefix: "[SENSOR]"
  memory_threshold_mb: 45  # Alert at 45MB (of 512MB total)

telegram:
  token: "YOUR_BOT_TOKEN_HERE"
  chat_id: "YOUR_CHAT_ID_HERE"
  admin_ids:
    - "YOUR_USER_ID"

# Aggressive rate limiting for low-power device
alerts:
  rate_limit_window: 300     # 5 minutes between alerts
  max_alerts_per_window: 2

  # Quiet hours (e.g., nighttime)
  quiet_hours:
    enabled: true
    start: "23:00"
    end: "07:00"
```

### Run Alert Bot
```bash
# Ensure low memory mode
python3 src/alert_bot.py
```

### Monitor Memory Usage
```bash
# Check bot memory
/memory  # Telegram command

# Watch memory in terminal
watch -n 5 'ps aux | grep alert_bot'
```

---

## Example 5: Custom Service Monitoring

Monitor specific application services with custom health checks.

### Configuration

**config/service_monitoring.yml**
```yaml
critical_services:
  - nginx
  - postgresql
  - redis-server

important_services:
  - docker
  - fail2ban
  - cron

allowed_restart:
  - nginx
  - redis-server
  # Note: postgresql NOT in allowed_restart for safety
```

**config/telegram_config.yml**
```yaml
monitoring:
  # Check services every 60 seconds
  check_interval: 60

  # Network interfaces to monitor
  interfaces:
    - eth0
    - wlan0
```

### Custom Health Check Script

Create a script that runs alongside the bot:

**custom_check.sh**
```bash
#!/bin/bash
set -uo pipefail

# Custom health check for your app
APP_HEALTH=$(curl -sf http://localhost:8080/health || echo "FAIL")

if [[ "$APP_HEALTH" != "OK" ]]; then
    ./src/simple_sender.sh "🚨 Application health check failed: $APP_HEALTH"
fi
```

Add to crontab:
```bash
*/5 * * * * /opt/telegram-monitor/custom_check.sh
```

---

## Example 6: Secure Production Deployment

Best practices for production environments.

### Directory Structure
```
/opt/telegram-monitor/
├── src/                    # Application code
│   ├── interactive_bot.py
│   ├── alert_bot.py
│   └── ...
├── config/                 # Example configs (unused)
└── venv/                   # Python virtual environment

/etc/telegram-monitor/
├── telegram_config.yml     # Main config (600 root:root)
├── service_monitoring.yml  # Service config (600 root:root)
└── ssh_targets.yml         # SSH config (600 root:root)

/var/log/telegram-monitor/
└── bot.log                 # Log files
```

### Secure File Permissions
```bash
# Config files: owner-only read
sudo chmod 600 /etc/telegram-monitor/*.yml
sudo chown root:root /etc/telegram-monitor/*.yml

# Log directory
sudo chmod 750 /var/log/telegram-monitor
sudo chown root:telegraf /var/log/telegram-monitor
```

### systemd Service with Hardening
See `systemd/telegram-interactive-bot.service.example` for production-ready configuration with:
- `ProtectSystem=strict`
- `PrivateTmp=true`
- `NoNewPrivileges=true`
- `CapabilityBoundingSet=CAP_NET_BIND_SERVICE`

### Token from Secret Manager
Instead of storing tokens in config files, use environment:
```bash
# /etc/telegram-monitor/token.env
TELEGRAM_BOT_TOKEN=your_secure_token_here
```

```ini
# systemd service
[Service]
EnvironmentFile=/etc/telegram-monitor/token.env
```

---

## Next Steps

- [SETUP.md](SETUP.md) - Full installation guide
- [API_REFERENCE.md](API_REFERENCE.md) - All commands and options
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
