# Architecture

System design and component overview for telegram-multi-device-monitor.

## Design Goals

1. **Modularity** - Components can be used independently
2. **Low Resource** - Run on devices with limited RAM
3. **Security** - Principle of least privilege
4. **Reliability** - Graceful degradation when checks fail
5. **Extensibility** - Easy to add new commands and metrics

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User's Device                                  │
│                          (Telegram App)                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Telegram Bot API                                 │
│                      (api.telegram.org)                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│   Interactive Bot   │ │    Alert Bot    │ │  Prometheus Webhook │
│   ┌─────────────┐   │ │   (Lightweight) │ │   ┌─────────────┐   │
│   │ Command     │   │ │                 │ │   │ Flask App   │   │
│   │ Handlers    │   │ └─────────────────┘ │   └─────────────┘   │
│   └─────────────┘   │                     │          │          │
│   ┌─────────────┐   │                     │          ▼          │
│   │ System      │   │                     │   ┌─────────────┐   │
│   │ Monitor     │   │                     │   │ Alert       │   │
│   └─────────────┘   │                     │   │ Formatter   │   │
│   ┌─────────────┐   │                     │   └─────────────┘   │
│   │ Alert       │   │                     └─────────────────────┘
│   │ Manager     │   │
│   └─────────────┘   │
└─────────────────────┘
           │
           │ Collects
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Metrics Collector                                │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐    │
│  │       Local Metrics         │    │      Remote Metrics          │    │
│  │         (psutil)            │    │         (SSH)                │    │
│  │   • CPU, Memory, Disk       │    │   • Remote hosts             │    │
│  │   • Temperature             │    │   • Service status           │    │
│  │   • Service status          │    │   • Hardware metrics         │    │
│  └─────────────────────────────┘    └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Interactive Bot (`interactive_bot.py`)

The main, full-featured bot with extensive monitoring capabilities.

**Features:**
- 15+ Telegram commands
- Service management (view, restart)
- Docker container monitoring
- Network interface monitoring
- Visual metrics display
- Admin authentication
- Rate-limited alerts

**Memory Usage:** ~50MB

**Key Classes:**
- `BotConfig` - Configuration management
- `SystemMonitor` - Metrics collection
- `AlertManager` - Rate limiting and formatting
- `InteractiveBot` - Command handlers

### Alert Bot (`alert_bot.py`)

Lightweight alternative for resource-constrained devices.

**Features:**
- Essential commands only
- AsyncIO optimized
- Memory management with GC
- 2FA for admin commands
- Connection pooling

**Memory Usage:** ~25MB

**Optimizations:**
- `__slots__` for classes
- Automatic garbage collection
- Minimal logging in production

### Prometheus Webhook (`prometheus_webhook.py`)

HTTP webhook receiver for Prometheus Alertmanager.

**Features:**
- Receives alerts via HTTP POST
- Custom alert templates
- Deduplication (24h window)
- Health check endpoint

**Endpoints:**
- `POST /webhook` - Receive alerts
- `POST /api/v2/alerts` - Alertmanager native
- `GET /health` - Health check

### Metrics Collector (`metrics_collector.py`)

Collects system metrics locally or via SSH.

**Local Metrics:**
- CPU usage and temperature
- Memory statistics
- Disk usage
- Load average
- Service status

**Remote Metrics:**
- SSH-based collection
- Retry with exponential backoff
- Configurable timeouts

### Simple Sender (`simple_sender.sh`)

Lightweight bash script for sending messages.

**Use Cases:**
- Cron job alerts
- Script notifications
- Quick testing

**Features:**
- No Python dependency
- YAML/environment config
- Rate limiting support

### Config Loader (`config_loader.py`)

Centralized configuration management.

**Features:**
- YAML file loading
- Environment variable overrides
- Deep merge with defaults
- Validation

**Priority Order:**
1. Environment variables (highest)
2. Config file
3. Built-in defaults (lowest)

## Data Flow

### Command Processing
```
User sends /status
       │
       ▼
Telegram API
       │
       ▼
Long Polling
       │
       ▼
CommandHandler
       │
       ▼
SystemMonitor.get_system_status()
       │
       ├── psutil.cpu_percent()
       ├── psutil.virtual_memory()
       ├── psutil.disk_usage()
       ├── subprocess(vcgencmd)
       └── subprocess(systemctl)
       │
       ▼
Format message
       │
       ▼
reply_text()
       │
       ▼
User sees response
```

### Alert Processing
```
Prometheus fires alert
       │
       ▼
Alertmanager
       │
       ▼
POST /webhook
       │
       ▼
Check deduplication
       │
       ├── Duplicate? → Suppress
       │
       └── New? → Format message
                       │
                       ▼
              simple_sender.sh
                       │
                       ▼
              Telegram API
                       │
                       ▼
              User receives alert
```

## Security Architecture

### Authentication Layers
1. **Bot Token** - Access to Telegram API
2. **Chat ID** - Target for messages
3. **Admin Whitelist** - Privileged command access
4. **Service Whitelist** - Restartable services

### systemd Hardening
```ini
# Security directives in service files
ProtectSystem=strict       # Read-only filesystem
ProtectHome=read-only      # Protected home directories
PrivateTmp=true            # Isolated /tmp
NoNewPrivileges=true       # Prevent privilege escalation
MemoryMax=100M             # Memory limit
```

### Token Security
- Masked in logs (first 10 chars only)
- Stored with 600 permissions
- Optional secret manager integration

## Retry and Error Handling

### Graceful Degradation
```python
# SystemMonitor.get_system_status()
status = {"timestamp": ..., "healthy": True}

try:
    status["cpu_percent"] = psutil.cpu_percent()
except OSError:
    status["cpu_percent"] = 0.0
    status["healthy"] = False

# Always returns, never crashes
```

### SSH Retry Logic
```
Attempt 1 → Fail → Wait 2s
Attempt 2 → Fail → Wait 4s
Attempt 3 → Fail → Return None
```

## Memory Optimization

### For Low-Memory Devices
1. Use `alert_bot.py` instead of `interactive_bot.py`
2. Set `LOG_LEVEL=WARNING`
3. Configure systemd `MemoryMax=50M`
4. Use `__slots__` in custom classes

### Garbage Collection
```python
# alert_bot.py MemoryManager
if memory_mb > threshold:
    gc.collect()
```

## Extensibility

### Adding New Commands
```python
# In InteractiveBot class
async def mycommand_command(self, update, context):
    await update.message.reply_text("Hello!")

# In setup_handlers
self.application.add_handler(
    CommandHandler("mycommand", self.mycommand_command)
)
```

### Adding New Metrics
```python
# In MetricsCollector class
def get_custom_metric(self):
    # Your collection logic
    return {"value": 42}
```

## File Structure

```
telegram-multi-device-monitor/
├── src/
│   ├── interactive_bot.py    # Full bot
│   ├── alert_bot.py          # Lightweight bot
│   ├── prometheus_webhook.py # Alert receiver
│   ├── simple_sender.sh      # CLI sender
│   ├── token_fetcher.sh      # Secret manager
│   ├── alert_sender.py       # Formatted alerts
│   ├── metrics_collector.py  # Metrics collection
│   ├── config_loader.py      # Config management
│   └── lib/                  # Bash libraries
├── config/                   # Configuration templates
├── systemd/                  # Service files
├── docs/                     # Documentation
└── install.sh                # Installer
```
