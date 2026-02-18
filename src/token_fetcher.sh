#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# Telegram Token Fetcher
# Retrieves bot token from secret manager and caches for systemd service
#
# This script is designed to run as ExecStartPre in a systemd service.
# It fetches the token from a secret manager (Vaultwarden/Bitwarden CLI)
# and writes it to a RuntimeDirectory for the main bot to consume.
#
# Usage:
#   As ExecStartPre in systemd:
#   ExecStartPre=/path/to/token_fetcher.sh
#
# Output:
#   Writes environment file to $RUNTIME_DIRECTORY/env
#   Format: TELEGRAM_BOT_TOKEN=<token>
#
# Exit Codes:
#   0 - Success (token from secret manager or fallback)
#   1 - Failure (no token available)
#
# Version: 1.0.0
#
set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================

readonly SCRIPT_NAME="token_fetcher"

# Secret manager configuration (customize for your setup)
# Vaultwarden/Bitwarden CLI item name containing the bot token
SECRET_ITEM_NAME="${SECRET_ITEM_NAME:-Telegram Bot Token}"

# Secret manager URL (if using Bitwarden CLI with self-hosted server)
SECRET_MANAGER_URL="${SECRET_MANAGER_URL:-}"

# Timeout for secret manager operations
SECRET_TIMEOUT="${SECRET_TIMEOUT:-10}"

# Fallback configuration
CONFIG_DIR="${TELEGRAM_CONFIG_DIR:-/etc/telegram-monitor}"
FALLBACK_SECRETS="${CONFIG_DIR}/.secrets"

# RuntimeDirectory (set by systemd, or use default)
RUNTIME_DIR="${RUNTIME_DIRECTORY:-/run/telegram-monitor}"
readonly ENV_FILE="${RUNTIME_DIR}/env"

# Bootstrap credentials file (for unlocking secret manager)
BOOTSTRAP_SECRETS="${BOOTSTRAP_SECRETS:-${HOME}/.telegram-monitor-bootstrap}"

# ============================================================================
# Logging
# ============================================================================

log_info() {
    echo "[${SCRIPT_NAME}] INFO: $*" >&2
}

log_warn() {
    echo "[${SCRIPT_NAME}] WARN: $*" >&2
}

log_error() {
    echo "[${SCRIPT_NAME}] ERROR: $*" >&2
}

# ============================================================================
# Secret Manager Functions
# ============================================================================

check_secret_manager_available() {
    # Check if Bitwarden CLI is installed and server is reachable
    if ! command -v bw >/dev/null 2>&1; then
        log_warn "Bitwarden CLI (bw) not installed"
        return 1
    fi

    # If custom server URL is set, check if it's reachable
    if [[ -n "$SECRET_MANAGER_URL" ]]; then
        local http_code
        http_code=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" \
            "${SECRET_MANAGER_URL}/alive" 2>/dev/null || echo "000")

        if [[ "$http_code" != "200" ]]; then
            log_warn "Secret manager not reachable at ${SECRET_MANAGER_URL}"
            return 1
        fi
    fi

    return 0
}

fetch_from_secret_manager() {
    # Fetch token from Bitwarden/Vaultwarden CLI
    local token bw_session bw_status

    # Check for bootstrap credentials
    if [[ ! -f "$BOOTSTRAP_SECRETS" ]]; then
        log_warn "Bootstrap secrets not found: $BOOTSTRAP_SECRETS"
        return 1
    fi

    # Load bootstrap credentials
    local bw_password bw_email
    bw_password=$(grep "^BW_PASSWORD=" "$BOOTSTRAP_SECRETS" 2>/dev/null | cut -d= -f2 | tr -d ' \n\r')
    bw_email=$(grep "^BW_EMAIL=" "$BOOTSTRAP_SECRETS" 2>/dev/null | cut -d= -f2 | tr -d ' \n\r')

    if [[ -z "$bw_password" ]] || [[ -z "$bw_email" ]]; then
        log_warn "BW_PASSWORD or BW_EMAIL not found in bootstrap secrets"
        return 1
    fi

    export BW_PASSWORD="$bw_password"

    # Configure server URL if specified
    if [[ -n "$SECRET_MANAGER_URL" ]]; then
        bw config server "$SECRET_MANAGER_URL" >/dev/null 2>&1 || true
    fi

    # Check login status
    bw_status=$(bw status 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

    if [[ "$bw_status" == "unauthenticated" ]]; then
        log_info "Logging into secret manager..."
        if ! timeout "$SECRET_TIMEOUT" bw login "$bw_email" --passwordenv BW_PASSWORD --raw >/dev/null 2>&1; then
            log_warn "Failed to login to secret manager"
            unset BW_PASSWORD
            return 1
        fi
    fi

    # Unlock vault
    bw_session=$(timeout "$SECRET_TIMEOUT" bw unlock --passwordenv BW_PASSWORD --raw 2>/dev/null)

    if [[ -z "$bw_session" ]]; then
        log_warn "Failed to unlock vault"
        unset BW_PASSWORD
        return 1
    fi

    export BW_SESSION="$bw_session"

    # Sync (optional, for fresh data)
    timeout "$SECRET_TIMEOUT" bw sync --session "$bw_session" >/dev/null 2>&1 || true

    # Fetch token (stored as Secure Note)
    token=$(timeout "$SECRET_TIMEOUT" bw get notes "$SECRET_ITEM_NAME" --session "$bw_session" 2>/dev/null)

    # Cleanup
    unset BW_PASSWORD BW_SESSION

    if [[ -z "$token" ]]; then
        log_warn "Token not found in secret manager item: $SECRET_ITEM_NAME"
        return 1
    fi

    # Validate token format (bot_id:secret)
    if [[ ! "$token" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
        log_warn "Token format invalid (expected: <bot_id>:<secret>)"
        return 1
    fi

    echo "$token"
    return 0
}

fetch_from_fallback() {
    # Load token from fallback secrets file
    if [[ ! -f "$FALLBACK_SECRETS" ]]; then
        log_error "Fallback secrets not found: $FALLBACK_SECRETS"
        return 1
    fi

    local token line

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and empty lines
        [[ -z "$line" ]] && continue
        [[ "$line" == \#* ]] && continue

        if [[ "$line" == TELEGRAM_BOT_TOKEN=* ]]; then
            token="${line#TELEGRAM_BOT_TOKEN=}"
            # Strip quotes and whitespace
            token="${token//\"/}"
            token="${token//\'/}"
            token="${token%% }"
            token="${token## }"
            break
        fi
    done < "$FALLBACK_SECRETS"

    if [[ -z "$token" ]]; then
        log_error "TELEGRAM_BOT_TOKEN not found in $FALLBACK_SECRETS"
        return 1
    fi

    echo "$token"
    return 0
}

write_env_file() {
    local token="$1"

    # Create RuntimeDirectory if not exists
    if [[ ! -d "$RUNTIME_DIR" ]]; then
        mkdir -p "$RUNTIME_DIR"
        chmod 750 "$RUNTIME_DIR"
    fi

    # Write environment file with restrictive permissions
    printf 'TELEGRAM_BOT_TOKEN=%s\n' "$token" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    log_info "Environment file written: $ENV_FILE"
    return 0
}

# ============================================================================
# Main
# ============================================================================

main() {
    local token=""
    local source=""

    log_info "Starting token fetch..."

    # Try secret manager first
    if check_secret_manager_available; then
        log_info "Secret manager available, attempting token fetch..."

        if token=$(fetch_from_secret_manager); then
            source="secret_manager"
            log_info "Token fetched from secret manager"
        else
            log_warn "Secret manager fetch failed, trying fallback..."
        fi
    else
        log_warn "Secret manager not available, using fallback..."
    fi

    # Fallback to secrets file
    if [[ -z "$token" ]]; then
        if token=$(fetch_from_fallback); then
            source="fallback"
            log_info "Token fetched from fallback"
        else
            log_error "All token sources failed!"
            return 1
        fi
    fi

    # Write environment file
    if ! write_env_file "$token"; then
        log_error "Failed to write environment file"
        return 1
    fi

    log_info "Token source: $source"
    log_info "Token ready for service"

    return 0
}

main "$@"
