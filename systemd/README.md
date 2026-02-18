# systemd Service Templates

This directory contains systemd service templates for running the bot components as system services.

## Installation

1. Copy the template to systemd directory:
   ```bash
   sudo cp telegram-interactive-bot.service.example /etc/systemd/system/telegram-interactive-bot.service
   ```

2. Edit the service file to set correct paths:
   ```bash
   sudo nano /etc/systemd/system/telegram-interactive-bot.service
   ```

3. Create the required user and directories:
   ```bash
   sudo useradd -r -s /sbin/nologin telegram-monitor
   sudo mkdir -p /etc/telegram-monitor /var/log/telegram-monitor
   sudo chown telegram-monitor:telegram-monitor /etc/telegram-monitor /var/log/telegram-monitor
   ```

4. Copy and configure your config files:
   ```bash
   sudo cp config/*.yml /etc/telegram-monitor/
   sudo chmod 600 /etc/telegram-monitor/*.yml
   sudo chown telegram-monitor:telegram-monitor /etc/telegram-monitor/*.yml
   ```

5. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable telegram-interactive-bot.service
   sudo systemctl start telegram-interactive-bot.service
   ```

## Service Files

| Template | Component | Resource Usage |
|----------|-----------|----------------|
| `telegram-interactive-bot.service.example` | Full bot | ~50MB RAM |
| `telegram-alert-bot.service.example` | Lightweight bot | ~25MB RAM |
| `telegram-prometheus-webhook.service.example` | Webhook server | ~30MB RAM |
| `telegram-metrics-collector.service.example` | Metrics timer | Minimal |

## Security Hardening

All templates include security hardening:

- `ProtectSystem=strict` - Read-only filesystem
- `ProtectHome=read-only` - Protect home directories
- `PrivateTmp=true` - Isolated /tmp
- `NoNewPrivileges=true` - Prevent privilege escalation
- `MemoryMax=` - Memory limits

## Logs

View logs with journalctl:
```bash
sudo journalctl -u telegram-interactive-bot -f
```

## Troubleshooting

If the service fails to start:

1. Check logs: `journalctl -u telegram-interactive-bot -n 50`
2. Verify permissions on config files
3. Test manually: `sudo -u telegram-monitor python3 /opt/telegram-monitor/src/interactive_bot.py`
