# API Reference

Complete reference for commands, configuration, and environment variables.

## Telegram Commands

### Monitoring Commands

#### `/status` (alias: `/s`)
Show system overview.

**Output includes:**
- CPU usage percentage
- Memory usage (used/total GB)
- Disk usage (used/total GB)
- CPU temperature
- Active network interface
- Service status summary
- Network interface IPs

**Example:**
```
[SERVER] System Status

🖥️ CPU: 15.2%
💾 Memory: 45.3% (7.2/15.9 GB)
💿 Disk: 23.1% (110.5/478.0 GB)
🌡️ Temperature: 52.0°C
🌐 Active Interface: eth0

Services:
  ✅ docker
  ✅ nginx
  ❌ prometheus

Network Interfaces:
  • eth0: 192.168.1.100
  • docker0: 172.17.0.1
```

#### `/services` (alias: `/v`)
Show detailed service status.

**Output includes:**
- System services (active/inactive)
- Docker containers (running/stopped)

#### `/docker` (alias: `/d`)
Same as `/services` - shows Docker containers.

#### `/metrics` (alias: `/m`)
Show metrics with visual progress bars.

**Example:**
```
[SERVER] System Metrics

🖥️ CPU: █░░░░░░░░░ 12.5%
💾 RAM: ████░░░░░░ 42.3%
   Used: 6.7 GB / 15.9 GB

💿 Disk: ██░░░░░░░░ 23.1%
   Used: 110.5 GB / 478.0 GB

🌡️ Temp: 🟢 52.0°C
```

#### `/logs` (alias: `/l`)
View system logs.

**Usage:**
```
/logs                    # Last 10 system warnings/errors
/logs 20                 # Last 20 entries
/logs nginx              # Last 10 nginx logs
/logs 50 docker          # Last 50 docker logs
```

### Admin Commands

#### `/restart` (alias: `/r`)
Restart a systemd service (admin only).

**Usage:**
```
/restart nginx
```

**Flow:**
1. Check user is in admin_ids
2. Verify service is in allowed_restart list
3. Show confirmation dialog
4. User confirms or cancels
5. Execute restart
6. Report result

**Security:**
- Whitelist-based validation
- Callback data re-validated
- Action logged

### Help Commands

#### `/start`
Show welcome message with command overview.

#### `/help` (alias: `/h`)
Show all available commands.
Admins see additional admin commands.

---

## Configuration Reference

### Telegram Configuration

**File:** `config/telegram_config.yml`

```yaml
# Bot identity
bot:
  system_name: "My Server"        # Display name in messages
  system_prefix: "[SERVER]"       # Prefix for alerts
  log_level: "INFO"               # DEBUG, INFO, WARNING, ERROR

# Telegram API settings
telegram:
  token: "123:ABC..."             # Bot token from @BotFather
  chat_id: "-123456789"           # Target chat/group ID
  admin_ids:                      # Allowed admin users
    - "111111111"
    - "222222222"
  rate_limit_window: 60           # Seconds between duplicate alerts

# Timeouts (seconds)
timeouts:
  subprocess: 30                  # General command timeout
  hardware_query: 5               # Fast queries (temp, etc)
  docker: 10                      # Docker operations
  route_check: 10                 # Network route commands
  ping: 8                         # Connectivity tests

# Logging
logging:
  log_dir: "/var/log/telegram-monitor"
  max_bytes: 10485760             # 10MB
  backup_count: 3

# Memory management (for low-memory devices)
memory:
  limit_mb: 50
  gc_interval: 300                # Seconds
  threshold_mb: 45                # Trigger GC above this
```

### Service Monitoring Configuration

**File:** `config/service_monitoring.yml`

```yaml
# Services shown in /services and /status
critical_services:
  - docker
  - nginx
  - ssh

# Secondary services
important_services:
  - prometheus
  - grafana

# Services allowed for /restart
allowed_restart:
  - docker
  - nginx
  # NEVER: sshd, systemd-networkd

# Service groups for organized display
groups:
  infrastructure:
    label: "🏗️ Infrastructure"
    services:
      - docker
      - nginx

# Alert thresholds
thresholds:
  failure_count: 2                # Consecutive failures before alert
  check_interval: 60              # Seconds between checks
  quiet_hours:
    start: 22                     # 10 PM
    end: 7                        # 7 AM
```

### SSH Targets Configuration

**File:** `config/ssh_targets.yml`

```yaml
# Default SSH settings
defaults:
  key_path: "~/.ssh/id_ed25519"
  connect_timeout: 10
  command_timeout: 15
  max_retries: 3
  retry_base_delay: 2

# Remote hosts to monitor
targets:
  - name: "primary_device"
    host: "192.168.1.10"
    user: "admin"
    type: "raspberry_pi"          # linux, raspberry_pi, router
    services:
      - docker
      - nginx

  - name: "nas_server"
    host: "192.168.1.20"
    user: "admin"
    type: "linux"
    services:
      - smbd
      - docker

# Connection pool
pool:
  max_connections: 3
  keepalive_interval: 30
```

### Network Configuration

**File:** `config/network_config.yml`

```yaml
# Interfaces to monitor
interfaces:
  - name: "eth0"
    type: "wan"
    label: "Primary WAN"
  - name: "eth1"
    type: "lan"
    label: "LAN"

# Failover settings
failover:
  enabled: true
  primary_interface: "eth0"
  backup_interface: "eth1"
  ping_targets:
    - "8.8.8.8"
    - "1.1.1.1"
  failure_threshold: 3

# VPN monitoring
vpn:
  enabled: false
  interface: "wg0"
  type: "wireguard"
```

---

## Environment Variables

Override configuration with environment variables:

| Variable | Config Path | Description |
|----------|-------------|-------------|
| `TELEGRAM_BOT_TOKEN` | `telegram.token` | Bot API token |
| `TELEGRAM_CHAT_ID` | `telegram.chat_id` | Target chat ID |
| `TELEGRAM_ADMIN_IDS` | `telegram.admin_ids` | Comma-separated admin IDs |
| `TELEGRAM_CONFIG_DIR` | N/A | Path to config directory |
| `LOG_LEVEL` | `bot.log_level` | Logging verbosity |
| `FLASK_HOST` | N/A | Webhook bind address |
| `FLASK_PORT` | N/A | Webhook port |
| `STATE_DIR` | N/A | Alert state directory |
| `DEDUP_WINDOW_HOURS` | N/A | Alert deduplication window |

**Priority:** Environment > Config File > Defaults

---

## Exit Codes

### Python Scripts
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (config, runtime) |
| 130 | SIGINT (Ctrl+C) |
| 143 | SIGTERM (systemd stop) |

### Bash Scripts
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Missing argument |
| 3 | Config not found |

---

## Prometheus Webhook API

### POST /webhook or /api/v2/alerts

Receive Prometheus alerts.

**Request:**
```json
{
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighCPU",
        "severity": "warning"
      },
      "annotations": {
        "summary": "CPU usage above 90%",
        "description": "Server CPU at 95%"
      }
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "total": 1,
  "sent": 1,
  "suppressed": 0
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{"status": "healthy"}
```

### GET /templates

List available alert templates.

**Response:**
```json
{
  "templates": ["default", "ServiceDown", "HighCPU", ...],
  "count": 7
}
```

---

## Library Functions

### logging.sh

```bash
source lib/logging.sh

log_debug "Debug message"
log_info "Info message"
log_warn "Warning message"
log_error "Error message"

log_info_structured "Operation complete" "DURATION=5s" "ITEMS=42"
```

### alerts.sh

```bash
source lib/alerts.sh

alerts_init                              # Initialize state
send_alert "WARNING" "Disk low" "disk"   # Send with dedup
send_critical "Server down!"              # Convenience function
clear_alert "disk"                        # Clear for recovery
```

### file_utils.sh

```bash
source lib/file_utils.sh

safe_write "/path/file" "content" 600    # Atomic write
temp=$(create_temp_file "prefix")         # Create temp file
age=$(file_age_seconds "/path/file")      # Check file age
value=$(read_config_value "file" "KEY")   # Read config
```
