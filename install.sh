#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# telegram-multi-device-monitor Installation Script
#
# This script installs the Telegram monitoring system with:
# - Dependency checks
# - Configuration prompts
# - systemd service installation
# - Verification
#
# Usage:
#   ./install.sh              # Interactive installation
#   ./install.sh --uninstall  # Remove installation
#   ./install.sh --check      # Verify dependencies only
#
set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================

readonly SCRIPT_NAME="install.sh"
readonly VERSION="1.0.0"

# Installation paths
readonly INSTALL_DIR="/opt/telegram-monitor"
readonly CONFIG_DIR="/etc/telegram-monitor"
readonly LOG_DIR="/var/log/telegram-monitor"
readonly STATE_DIR="/var/lib/telegram-monitor"
readonly SERVICE_USER="telegram-monitor"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Source directory (where this script is)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR

# ============================================================================
# Logging Functions
# ============================================================================

info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# ============================================================================
# Dependency Checking
# ============================================================================

check_python() {
    if command -v python3 >/dev/null 2>&1; then
        local version
        version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        local major minor
        IFS='.' read -r major minor <<< "$version"

        if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 10 ]]; then
            success "Python $version found"
            return 0
        else
            error "Python 3.10+ required (found $version)"
            return 1
        fi
    else
        error "Python 3 not found"
        return 1
    fi
}

check_pip_packages() {
    info "Checking Python packages..."
    local missing=()

    for pkg in "telegram" "flask" "yaml" "psutil" "aiohttp"; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            missing+=("$pkg")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing packages: ${missing[*]}"
        info "Install with: pip3 install -r requirements.txt"
        return 1
    else
        success "All Python packages installed"
        return 0
    fi
}

check_system_commands() {
    info "Checking system commands..."
    local missing=()

    for cmd in curl jq systemctl; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing commands: ${missing[*]}"
        info "Install with: sudo apt install curl jq systemd"
        return 1
    else
        success "All system commands available"
        return 0
    fi
}

check_dependencies() {
    info "Checking dependencies..."
    local failed=0

    check_python || ((failed++))
    check_pip_packages || ((failed++))
    check_system_commands || ((failed++))

    if [[ $failed -gt 0 ]]; then
        error "$failed dependency check(s) failed"
        return 1
    fi

    success "All dependencies satisfied"
    return 0
}

# ============================================================================
# Installation Functions
# ============================================================================

create_user() {
    info "Creating service user..."
    if id "$SERVICE_USER" &>/dev/null; then
        success "User $SERVICE_USER already exists"
    else
        sudo useradd -r -s /sbin/nologin "$SERVICE_USER"
        success "Created user $SERVICE_USER"
    fi
}

create_directories() {
    info "Creating directories..."

    sudo mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$STATE_DIR"
    sudo chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR" "$STATE_DIR"
    sudo chmod 750 "$CONFIG_DIR" "$LOG_DIR" "$STATE_DIR"

    success "Directories created"
}

copy_files() {
    info "Copying files..."

    # Source files
    sudo cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
    sudo chmod +x "$INSTALL_DIR/src/"*.sh 2>/dev/null || true

    # Config templates
    if [[ ! -f "$CONFIG_DIR/telegram_config.yml" ]]; then
        sudo cp "$SCRIPT_DIR/config/"*.example "$CONFIG_DIR/"
        for f in "$CONFIG_DIR/"*.example; do
            sudo mv "$f" "${f%.example}"
        done
        warn "Config files copied - EDIT $CONFIG_DIR/telegram_config.yml with your settings!"
    else
        info "Config files already exist, skipping"
    fi

    success "Files copied to $INSTALL_DIR"
}

install_python_deps() {
    info "Installing Python dependencies..."

    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        pip3 install --user -r "$SCRIPT_DIR/requirements.txt" || {
            warn "pip install failed, trying with sudo..."
            sudo pip3 install -r "$SCRIPT_DIR/requirements.txt"
        }
        success "Python dependencies installed"
    else
        warn "requirements.txt not found, skipping"
    fi
}

configure_telegram() {
    info "Telegram Configuration"
    echo ""
    echo "You need to configure your Telegram bot credentials."
    echo "Get these from @BotFather on Telegram."
    echo ""

    # Check if already configured
    if [[ -f "$CONFIG_DIR/telegram_config.yml" ]]; then
        if grep -q "YOUR_BOT_TOKEN" "$CONFIG_DIR/telegram_config.yml" 2>/dev/null; then
            read -rp "Enter your Telegram Bot Token: " bot_token
            read -rp "Enter your Telegram Chat ID: " chat_id

            if [[ -n "$bot_token" ]] && [[ -n "$chat_id" ]]; then
                sudo sed -i "s/YOUR_BOT_TOKEN_HERE/$bot_token/" "$CONFIG_DIR/telegram_config.yml"
                sudo sed -i "s/YOUR_CHAT_ID_HERE/$chat_id/" "$CONFIG_DIR/telegram_config.yml"
                success "Telegram credentials configured"
            else
                warn "Skipping configuration - edit $CONFIG_DIR/telegram_config.yml manually"
            fi
        else
            success "Telegram already configured"
        fi
    fi
}

install_systemd_service() {
    info "Installing systemd service..."

    local service_file="/etc/systemd/system/telegram-interactive-bot.service"

    if [[ -f "$service_file" ]]; then
        read -rp "Service already exists. Overwrite? [y/N]: " overwrite
        if [[ "$overwrite" != "y" ]] && [[ "$overwrite" != "Y" ]]; then
            info "Skipping service installation"
            return 0
        fi
    fi

    # Copy and customize service file
    sudo cp "$SCRIPT_DIR/systemd/telegram-interactive-bot.service.example" "$service_file"
    sudo sed -i "s|/opt/telegram-monitor|$INSTALL_DIR|g" "$service_file"

    # Reload and enable
    sudo systemctl daemon-reload
    sudo systemctl enable telegram-interactive-bot.service

    success "Service installed and enabled"
    info "Start with: sudo systemctl start telegram-interactive-bot"
}

verify_installation() {
    info "Verifying installation..."
    local failed=0

    # Check directories
    for dir in "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"; do
        if [[ -d "$dir" ]]; then
            success "Directory $dir exists"
        else
            error "Directory $dir missing"
            ((failed++))
        fi
    done

    # Check main script
    if [[ -f "$INSTALL_DIR/src/interactive_bot.py" ]]; then
        success "Main script exists"
    else
        error "Main script missing"
        ((failed++))
    fi

    # Check config
    if [[ -f "$CONFIG_DIR/telegram_config.yml" ]]; then
        success "Config file exists"
    else
        error "Config file missing"
        ((failed++))
    fi

    # Test import
    if python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR/src'); import config_loader" 2>/dev/null; then
        success "Python imports work"
    else
        error "Python imports failed"
        ((failed++))
    fi

    if [[ $failed -eq 0 ]]; then
        success "Installation verified successfully!"
        return 0
    else
        error "$failed verification check(s) failed"
        return 1
    fi
}

# ============================================================================
# Uninstallation
# ============================================================================

uninstall() {
    warn "This will remove telegram-multi-device-monitor"
    read -rp "Are you sure? [y/N]: " confirm

    if [[ "$confirm" != "y" ]] && [[ "$confirm" != "Y" ]]; then
        info "Uninstall cancelled"
        return 0
    fi

    info "Stopping service..."
    sudo systemctl stop telegram-interactive-bot.service 2>/dev/null || true
    sudo systemctl disable telegram-interactive-bot.service 2>/dev/null || true

    info "Removing files..."
    sudo rm -rf "$INSTALL_DIR"
    sudo rm -f /etc/systemd/system/telegram-*.service
    sudo systemctl daemon-reload

    info "Keeping config in $CONFIG_DIR and logs in $LOG_DIR"
    info "Remove manually if needed: sudo rm -rf $CONFIG_DIR $LOG_DIR"

    success "Uninstallation complete"
}

# ============================================================================
# Main
# ============================================================================

usage() {
    cat << EOF
telegram-multi-device-monitor Installer v$VERSION

Usage: $0 [OPTION]

Options:
    (no option)     Interactive installation
    --check         Check dependencies only
    --uninstall     Remove installation
    --help          Show this help

EOF
}

main() {
    echo "================================================"
    echo "telegram-multi-device-monitor Installer v$VERSION"
    echo "================================================"
    echo ""

    case "${1:-}" in
        --check)
            check_dependencies
            exit $?
            ;;
        --uninstall)
            uninstall
            exit $?
            ;;
        --help|-h)
            usage
            exit 0
            ;;
    esac

    # Full installation
    info "Starting installation..."

    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        warn "Not running as root. Will use sudo for privileged operations."
    fi

    check_dependencies || {
        error "Please install missing dependencies first"
        exit 1
    }

    create_user
    create_directories
    copy_files
    install_python_deps
    configure_telegram
    install_systemd_service
    verify_installation

    echo ""
    echo "================================================"
    success "Installation complete!"
    echo "================================================"
    echo ""
    echo "Next steps:"
    echo "  1. Edit config:  sudo nano $CONFIG_DIR/telegram_config.yml"
    echo "  2. Start service: sudo systemctl start telegram-interactive-bot"
    echo "  3. Check status:  sudo systemctl status telegram-interactive-bot"
    echo "  4. View logs:     sudo journalctl -u telegram-interactive-bot -f"
    echo ""
}

main "$@"
