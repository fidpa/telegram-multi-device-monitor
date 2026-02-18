# Configuration Directory

This directory contains configuration templates for telegram-multi-device-monitor.

## Quick Start

1. Copy the example files and remove the `.example` suffix:
   ```bash
   cp telegram_config.yml.example telegram_config.yml
   cp service_monitoring.yml.example service_monitoring.yml
   # Optional:
   cp ssh_targets.yml.example ssh_targets.yml
   cp network_config.yml.example network_config.yml
   ```

2. Edit each file with your actual values (tokens, IPs, services)

3. **Important**: Keep your configured files secure (they contain credentials)
   ```bash
   chmod 600 telegram_config.yml
   ```

## Configuration Files

| File | Purpose | Required |
|------|---------|----------|
| `telegram_config.yml` | Bot token, chat ID, admin IDs, timeouts | **Yes** |
| `service_monitoring.yml` | Services to monitor and restart whitelist | **Yes** |
| `ssh_targets.yml` | Remote devices for SSH-based monitoring | Optional |
| `network_config.yml` | Network interfaces, failover, VPN | Optional |

## Environment Variable Overrides

The following environment variables override config file settings:

| Variable | Overrides | Description |
|----------|-----------|-------------|
| `TELEGRAM_BOT_TOKEN` | `telegram.token` | Bot API token |
| `TELEGRAM_CHAT_ID` | `telegram.chat_id` | Target chat ID |
| `TELEGRAM_ADMIN_IDS` | `telegram.admin_ids` | Comma-separated admin IDs |
| `LOG_LEVEL` | `bot.log_level` | Logging verbosity |
| `TELEGRAM_CONFIG_DIR` | Config directory | Path to config files |

## Security Best Practices

1. **Never commit real config files to git** - only `.example` files
2. **Restrict file permissions**: `chmod 600 telegram_config.yml`
3. **Use environment variables** for production deployments
4. **Limit admin_ids** to trusted users only
5. **Restrict allowed_restart** services to safe ones

## Configuration Priority

Settings are loaded in this order (later overrides earlier):

1. Built-in defaults
2. `telegram_config.yml` file
3. Environment variables

## Validation

Test your configuration:

```bash
python3 -c "from src.config_loader import load_config, validate_config; c = load_config(); print(validate_config(c))"
```

Empty list `[]` means configuration is valid.
