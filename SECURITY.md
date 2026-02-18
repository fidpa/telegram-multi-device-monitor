# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

### How to Report

Use [GitHub Security Advisories](https://github.com/fidpa/telegram-multi-device-monitor/security/advisories/new) to report vulnerabilities privately.

Include in your report:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to Expect

| Stage | Timeline |
|-------|----------|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 7 days |
| Fix for critical issues | Within 30 days |
| Fix for other issues | Within 90 days |

You will be kept informed of progress and may be credited in the fix (unless you prefer to remain anonymous).

## Security Best Practices

When deploying telegram-multi-device-monitor:

### Token Management

- **Never commit tokens** to version control
- Store tokens in environment files with `chmod 600`
- Use `token_fetcher.sh` for secret manager integration
- Rotate tokens periodically

```bash
# Correct: Environment file with restricted permissions
sudo touch /etc/telegram-monitor/env
sudo chmod 600 /etc/telegram-monitor/env
echo "TELEGRAM_BOT_TOKEN=your_token" | sudo tee /etc/telegram-monitor/env
```

### Access Control

- Limit `admin_ids` to necessary users only
- Use service whitelist for restart commands
- Enable 2FA for admin commands if available

```yaml
# config/telegram_config.yml
security:
  admin_ids:
    - "123456789"  # Only trusted users
  restart_whitelist:
    - "nginx"
    - "docker"     # Only specific services
```

### systemd Security

The provided service files include hardening:

- `ProtectSystem=strict` - Read-only filesystem
- `NoNewPrivileges=true` - Cannot gain privileges
- `PrivateTmp=true` - Isolated temp directory
- `MemoryMax=100M` - Resource limits

Do not remove these security measures.

### SSH Security

For remote monitoring:

- Use key-based authentication only
- Restrict SSH keys to specific commands if possible
- Monitor known_hosts for unexpected changes

## Known Security Considerations

### StrictHostKeyChecking

Remote SSH connections use `StrictHostKeyChecking=accept-new` (Trust On First Use). This accepts new host keys automatically but will reject if a key changes.

For higher security environments, manually add host keys and use `StrictHostKeyChecking=yes`.

### Debug Output

Debug output logs credential status but never exposes actual token values. Production deployments should disable debug logging.

## Security Audits

This project has undergone security review including:

- Static analysis (shellcheck, mypy --strict)
- Dependency scanning
- Code review for injection vulnerabilities

## Contact

For security questions that don't require private disclosure, use [GitHub Discussions](https://github.com/fidpa/telegram-multi-device-monitor/discussions).
