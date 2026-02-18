# Troubleshooting

Common issues and solutions for telegram-multi-device-monitor.

## Quick Diagnostics

Run these commands to diagnose issues:

```bash
# Check service status
sudo systemctl status telegram-interactive-bot

# View recent logs
sudo journalctl -u telegram-interactive-bot -n 50

# Test config loading
python3 -c "from src.config_loader import load_config, validate_config; print(validate_config(load_config()))"

# Test Telegram connection
./src/simple_sender.sh "Test message"
```

---

## Bot Won't Start

### Symptom: Service fails immediately

**Check 1: Python version**
```bash
python3 --version
# Requires 3.10+
```

**Fix:** Install Python 3.10+
```bash
sudo apt update
sudo apt install python3.10
```

### Symptom: "No module named 'telegram'"

**Fix:** Install dependencies
```bash
pip3 install -r requirements.txt
```

### Symptom: "Bot Token not configured"

**Check:** Verify config file exists and has token
```bash
cat /etc/telegram-monitor/telegram_config.yml | grep token
```

**Fix:** Add your token
```yaml
telegram:
  token: "YOUR_BOT_TOKEN_HERE"
```

### Symptom: Permission denied on config file

**Fix:** Correct permissions
```bash
sudo chown telegram-monitor:telegram-monitor /etc/telegram-monitor/*.yml
sudo chmod 640 /etc/telegram-monitor/*.yml
```

---

## Messages Not Sending

### Symptom: "Unauthorized" error

**Cause:** Invalid bot token

**Fix:**
1. Verify token with @BotFather
2. Check for typos or extra whitespace
3. Regenerate token if compromised

### Symptom: "Chat not found"

**Cause:** Invalid chat ID or bot not in chat

**Fix:**
1. Verify chat ID with @userinfobot
2. For groups, ensure bot is added
3. For groups, use negative ID (e.g., `-123456789`)

### Symptom: "Bad Request: can't parse entities"

**Cause:** Invalid Markdown in message

**Fix:** Check message formatting
```python
# Escape special characters
message = message.replace("_", "\\_")
```

### Symptom: Network timeout

**Cause:** Network issues or firewall

**Fix:**
```bash
# Test Telegram API connectivity
curl -s https://api.telegram.org/bot<TOKEN>/getMe

# Check firewall
sudo ufw status
```

---

## High Memory Usage

### Symptom: Bot using >100MB RAM

**Cause:** Using interactive_bot.py on low-memory device

**Fix:** Switch to alert_bot.py
```bash
# Edit service file
ExecStart=/usr/bin/python3 /opt/telegram-monitor/src/alert_bot.py
```

### Symptom: Memory grows over time

**Cause:** Logging or data accumulation

**Fix:**
1. Set `LOG_LEVEL=WARNING`
2. Enable memory limits in systemd:
   ```ini
   MemoryMax=50M
   MemoryHigh=40M
   ```
3. Restart service periodically

### Symptom: Out of memory errors

**Fix:** Configure system swappiness
```bash
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## Service Restart Fails

### Symptom: "Service not allowed"

**Cause:** Service not in whitelist

**Fix:** Add to allowed_restart in config
```yaml
# service_monitoring.yml
allowed_restart:
  - nginx
  - docker
  - your-service
```

### Symptom: "Permission denied" on restart

**Cause:** Bot user can't run sudo

**Fix:** Configure sudoers for bot user
```bash
# /etc/sudoers.d/telegram-monitor
telegram-monitor ALL=(ALL) NOPASSWD: /bin/systemctl restart nginx, /bin/systemctl restart docker
```

### Symptom: "Unauthorized" on restart command

**Cause:** Your Telegram ID not in admin_ids

**Fix:**
1. Get your ID from @userinfobot
2. Add to config:
   ```yaml
   telegram:
     admin_ids:
       - "YOUR_ID_HERE"
   ```

---

## SSH Metrics Collection Fails

### Symptom: "Connection refused"

**Fix:** Check SSH is running on remote host
```bash
ssh user@remote-host
```

### Symptom: "Permission denied (publickey)"

**Fix:** Set up SSH key authentication
```bash
# Generate key if needed
ssh-keygen -t ed25519

# Copy to remote host
ssh-copy-id user@remote-host
```

### Symptom: "Connection timed out"

**Cause:** Network or firewall issue

**Fix:**
1. Check connectivity: `ping remote-host`
2. Check SSH port: `nc -zv remote-host 22`
3. Check firewall on remote host

### Symptom: Slow SSH commands

**Fix:** Increase timeouts in config
```yaml
ssh:
  connect_timeout: 20
  command_timeout: 30
  max_retries: 5
```

---

## Prometheus Webhook Issues

### Symptom: "Connection refused" from Alertmanager

**Fix:** Check webhook is running and bound correctly
```bash
# Check process
ps aux | grep prometheus_webhook

# Check binding
ss -tlnp | grep 9094
```

### Symptom: Alerts not being sent

**Check:** Deduplication might be suppressing
```bash
# Check state file
cat /var/lib/telegram-monitor/alert_state.json
```

**Fix:** Clear old state
```bash
rm /var/lib/telegram-monitor/alert_state.json
```

### Symptom: Wrong alert format

**Fix:** Customize templates in `prometheus_webhook.py`:
```python
ALERT_TEMPLATES["MyAlert"] = {
    "emoji": "🚨",
    "format": "Custom format here"
}
```

---

## Configuration Issues

### Symptom: Config changes not taking effect

**Fix:** Restart service after config changes
```bash
sudo systemctl restart telegram-interactive-bot
```

### Symptom: "Invalid YAML"

**Fix:** Validate YAML syntax
```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/telegram-monitor/telegram_config.yml'))"
```

### Symptom: Environment variables not working

**Check:** Verify in systemd
```bash
sudo systemctl show telegram-interactive-bot | grep Environment
```

**Fix:** Add to service file or environment file
```ini
# In service file
Environment=TELEGRAM_BOT_TOKEN=...

# Or use EnvironmentFile
EnvironmentFile=/etc/telegram-monitor/env
```

---

## systemd Issues

### Symptom: Service keeps restarting

**Check:** View full logs
```bash
sudo journalctl -u telegram-interactive-bot --since "10 minutes ago"
```

**Common causes:**
- Python syntax error
- Missing dependency
- Config error
- Permission denied

### Symptom: "Failed to start" with no error

**Fix:** Run manually to see errors
```bash
sudo -u telegram-monitor python3 /opt/telegram-monitor/src/interactive_bot.py
```

### Symptom: Service killed by OOM

**Fix:** Increase memory limit or use lightweight bot
```ini
# In service file
MemoryMax=150M
```

---

## Debug Mode

Enable debug logging for more information:

### Python
```bash
export LOG_LEVEL=DEBUG
python3 src/interactive_bot.py
```

### Bash
```bash
export LOG_LEVEL=DEBUG
./src/simple_sender.sh "test"
```

### systemd
```ini
# In service file
Environment=LOG_LEVEL=DEBUG
```

---

## Getting Help

If you're still stuck:

1. **Check existing issues:** [GitHub Issues](https://github.com/fidpa/telegram-multi-device-monitor/issues)

2. **Create new issue with:**
   - Error message
   - Python version (`python3 --version`)
   - Config (with token masked)
   - Steps to reproduce

3. **Useful info to include:**
   ```bash
   # System info
   uname -a
   python3 --version
   pip3 list | grep telegram

   # Service status
   sudo systemctl status telegram-interactive-bot

   # Recent logs
   sudo journalctl -u telegram-interactive-bot -n 100 --no-pager
   ```
