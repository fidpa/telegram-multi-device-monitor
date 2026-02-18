#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# Simple Telegram Message Sender
# Lightweight CLI tool for sending Telegram messages without Python dependencies
#
# Usage:
#   ./simple_sender.sh "Your message here"
#   ./simple_sender.sh -f /path/to/message.txt
#   echo "Message" | ./simple_sender.sh -s
#
# Configuration:
#   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in:
#   - Environment variables (highest priority)
#   - Config file (telegram_config.yml)
#   - Secrets file ($CONFIG_DIR/.secrets)
#
# Version: 1.0.0
#
set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================

# Script directory (symlink-safe)
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
readonly SCRIPT_DIR

# Script name for logging
SCRIPT_NAME="$(basename "$0" .sh)"
readonly SCRIPT_NAME

# Configuration directory (can be overridden via environment)
CONFIG_DIR="${TELEGRAM_CONFIG_DIR:-${SCRIPT_DIR}/../config}"
readonly CONFIG_DIR

# Secrets file location
SECRETS_FILE="${CONFIG_DIR}/.secrets"

# Logging configuration
LOG_DIR="${LOG_DIR:-/var/log/telegram-monitor}"
LOG_FILE="${LOG_DIR}/${SCRIPT_NAME}.log"
LOG_TO_STDOUT="${LOG_TO_STDOUT:-true}"

# Telegram API credentials (will be loaded)
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
    local message="[${SCRIPT_NAME}] INFO: $*"
    [[ "$LOG_TO_STDOUT" == "true" ]] && echo "$message" >&2
    if [[ -w "$(dirname "$LOG_FILE")" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

log_warn() {
    local message="[${SCRIPT_NAME}] WARN: $*"
    [[ "$LOG_TO_STDOUT" == "true" ]] && echo "$message" >&2
    if [[ -w "$(dirname "$LOG_FILE")" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

log_error() {
    local message="[${SCRIPT_NAME}] ERROR: $*"
    echo "$message" >&2
    if [[ -w "$(dirname "$LOG_FILE")" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

# ============================================================================
# Configuration Loading
# ============================================================================

load_from_yaml() {
    # Load config from YAML file using simple parsing
    # Requires yq or falls back to grep-based parsing
    local config_file="${CONFIG_DIR}/telegram_config.yml"

    if [[ ! -f "$config_file" ]]; then
        return 1
    fi

    # Try yq first (more reliable)
    if command -v yq >/dev/null 2>&1; then
        if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
            TELEGRAM_BOT_TOKEN=$(yq -r '.telegram.token // ""' "$config_file" 2>/dev/null)
        fi
        if [[ -z "$TELEGRAM_CHAT_ID" ]]; then
            TELEGRAM_CHAT_ID=$(yq -r '.telegram.chat_id // ""' "$config_file" 2>/dev/null)
        fi
        return 0
    fi

    # Fallback: simple grep-based parsing
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
        TELEGRAM_BOT_TOKEN=$(grep -E '^\s*token:' "$config_file" 2>/dev/null | head -1 | sed 's/.*token:\s*["'"'"']\?\([^"'"'"']*\)["'"'"']\?.*/\1/' | tr -d ' ')
    fi
    if [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        TELEGRAM_CHAT_ID=$(grep -E '^\s*chat_id:' "$config_file" 2>/dev/null | head -1 | sed 's/.*chat_id:\s*["'"'"']\?\([^"'"'"']*\)["'"'"']\?.*/\1/' | tr -d ' ')
    fi

    return 0
}

load_from_secrets() {
    # Load credentials from .secrets file (simple KEY=VALUE format)
    local secrets_file="$1"

    if [[ ! -f "$secrets_file" ]]; then
        return 1
    fi

    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue

        case "$key" in
            TELEGRAM_BOT_TOKEN)
                [[ -z "$TELEGRAM_BOT_TOKEN" ]] && TELEGRAM_BOT_TOKEN="$value"
                ;;
            TELEGRAM_CHAT_ID)
                [[ -z "$TELEGRAM_CHAT_ID" ]] && TELEGRAM_CHAT_ID="$value"
                ;;
        esac
    done < <(grep -E '^[^#]*=' "$secrets_file" 2>/dev/null || true)

    return 0
}

load_config() {
    # Load configuration from multiple sources (priority order)
    # 1. Environment variables (already set)
    # 2. YAML config file
    # 3. Secrets file

    log_info "Loading Telegram configuration..."

    # Try YAML config
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        load_from_yaml && log_info "Loaded config from YAML"
    fi

    # Try secrets file
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        load_from_secrets "$SECRETS_FILE" && log_info "Loaded config from secrets file"
    fi

    # Try home directory secrets
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        load_from_secrets "${HOME}/.telegram-monitor.secrets" 2>/dev/null || true
    fi

    # Validate configuration
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
        log_error "Missing Telegram configuration (BOT_TOKEN or CHAT_ID)"
        log_error "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables"
        log_error "Or configure in ${CONFIG_DIR}/telegram_config.yml"
        return 1
    fi

    log_info "Configuration loaded successfully"
    return 0
}

# ============================================================================
# Telegram Functions
# ============================================================================

send_telegram_message() {
    local message="$1"
    local parse_mode="${2:-}"  # Default: empty (plain text)

    log_info "Sending Telegram message (${#message} chars)"

    # URL encode message
    local encoded_message
    if command -v jq >/dev/null 2>&1; then
        encoded_message=$(printf '%s' "$message" | jq -sRr @uri 2>/dev/null)
    else
        # Fallback: basic URL encoding
        encoded_message=$(printf '%s' "$message" | sed 's/ /%20/g; s/\n/%0A/g')
    fi

    # Build API URL
    local api_url="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"

    # Build curl command
    local curl_args=(
        -s -X POST "$api_url"
        -d "chat_id=${TELEGRAM_CHAT_ID}"
        -d "text=${encoded_message}"
        -d "disable_web_page_preview=true"
        --max-time 10
        --retry 3
        --retry-delay 2
    )

    # Add parse_mode if specified
    if [[ -n "$parse_mode" ]]; then
        curl_args+=(-d "parse_mode=${parse_mode}")
    fi

    # Send request
    local response
    response=$(curl "${curl_args[@]}" 2>/dev/null) || {
        log_error "curl request failed"
        return 1
    }

    # Check response
    if echo "$response" | grep -q '"ok":true'; then
        log_info "Telegram message sent successfully"
        return 0
    else
        log_error "Telegram API error: ${response:0:100}"
        return 1
    fi
}

# ============================================================================
# Main
# ============================================================================

usage() {
    cat << EOF
Simple Telegram Message Sender

Usage: $0 [OPTIONS] MESSAGE

OPTIONS:
    -f, --file FILE     Read message from file
    -s, --stdin         Read message from stdin
    -m, --markdown      Enable Markdown parsing
    -h, --help          Show this help

EXAMPLES:
    $0 "Test message"
    $0 -f /path/to/message.txt
    echo "Message" | $0 -s
    $0 -m "*Bold* and _italic_"

CONFIGURATION:
    Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID via:
    - Environment variables
    - ${CONFIG_DIR}/telegram_config.yml
    - ${CONFIG_DIR}/.secrets
EOF
}

main() {
    local message=""
    local from_stdin=false
    local from_file=""
    local parse_mode=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -s|--stdin)
                from_stdin=true
                shift
                ;;
            -f|--file)
                from_file="$2"
                shift 2
                ;;
            -m|--markdown)
                parse_mode="Markdown"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                usage >&2
                exit 1
                ;;
            *)
                message="$1"
                shift
                ;;
        esac
    done

    # Load configuration
    if ! load_config; then
        exit 1
    fi

    # Determine message source
    if [[ "$from_stdin" == "true" ]]; then
        message=$(cat)
    elif [[ -n "$from_file" ]]; then
        if [[ -f "$from_file" ]]; then
            message=$(cat "$from_file")
        else
            log_error "File not found: $from_file"
            exit 1
        fi
    fi

    # Validate message
    if [[ -z "$message" ]]; then
        log_error "No message provided"
        usage >&2
        exit 1
    fi

    # Send message
    if send_telegram_message "$message" "$parse_mode"; then
        exit 0
    else
        exit 1
    fi
}

# Only run main if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
