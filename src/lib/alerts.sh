#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# Alert Management Library for Bash Scripts
#
# Provides rate-limited alert sending with deduplication:
# - Alert deduplication within configurable window
# - Rate limiting to prevent alert storms
# - State persistence across script runs
# - Telegram integration via simple_sender.sh
#
# Usage:
#   source lib/alerts.sh
#   alerts_init  # Initialize state
#   send_alert "WARNING" "Disk space low" "disk_warning"
#
# Configuration (set before sourcing):
#   ALERT_STATE_FILE - Path to state file
#   ALERT_DEDUP_HOURS - Deduplication window (default: 3)
#   ALERT_RATE_LIMIT - Max alerts per hour (default: 10)
#

# Prevent double-sourcing
[[ -n "${_ALERTS_SOURCED:-}" ]] && return 0
readonly _ALERTS_SOURCED=1

# ============================================================================
# Configuration
# ============================================================================

# State file for tracking sent alerts (persistent across reboots)
_ALERT_DEFAULT_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/telegram-monitor"
ALERT_STATE_FILE="${ALERT_STATE_FILE:-${_ALERT_DEFAULT_STATE_DIR}/alert_state.json}"

# Deduplication window in hours
ALERT_DEDUP_HOURS="${ALERT_DEDUP_HOURS:-3}"

# Rate limit: max alerts per hour
ALERT_RATE_LIMIT="${ALERT_RATE_LIMIT:-10}"

# Path to telegram sender script
TELEGRAM_SENDER="${TELEGRAM_SENDER:-$(dirname "${BASH_SOURCE[0]}")/../simple_sender.sh}"

# ============================================================================
# State Management
# ============================================================================

alerts_init() {
    # Create state directory with restrictive permissions
    local state_dir
    state_dir="$(dirname "$ALERT_STATE_FILE")"
    if [[ ! -d "$state_dir" ]]; then
        mkdir -p "$state_dir"
        chmod 700 "$state_dir"
    fi

    # Initialize state file if not exists
    if [[ ! -f "$ALERT_STATE_FILE" ]]; then
        echo '{"alerts":{},"count":0,"hour_start":0}' > "$ALERT_STATE_FILE"
        chmod 600 "$ALERT_STATE_FILE"
    fi
}

_load_state() {
    if [[ -f "$ALERT_STATE_FILE" ]]; then
        cat "$ALERT_STATE_FILE"
    else
        echo '{"alerts":{},"count":0,"hour_start":0}'
    fi
}

_save_state() {
    local state="$1"
    local tmp="${ALERT_STATE_FILE}.tmp.$$"
    echo "$state" > "$tmp" && mv "$tmp" "$ALERT_STATE_FILE"
}

# Sanitize alert_id to prevent sed/grep injection
# Allow only: alphanumeric, underscore, hyphen
_sanitize_alert_id() {
    local raw_id="$1"
    local sanitized="${raw_id//[^a-zA-Z0-9_-]/}"

    # Warn if characters were removed (helps debugging)
    if [[ "$sanitized" != "$raw_id" ]]; then
        echo "[ALERTS] Warning: alert_id sanitized: '$raw_id' -> '$sanitized'" >&2
    fi

    echo "$sanitized"
}

_get_alert_timestamp() {
    local alert_id
    alert_id=$(_sanitize_alert_id "$1")
    local state
    state=$(_load_state)

    if command -v jq >/dev/null 2>&1; then
        jq -r ".alerts[\"$alert_id\"] // 0" <<< "$state"
    else
        # Fallback without jq
        grep -o "\"$alert_id\":[0-9]*" <<< "$state" | cut -d: -f2 || echo 0
    fi
}

_set_alert_timestamp() {
    local alert_id
    alert_id=$(_sanitize_alert_id "$1")
    local timestamp="$2"
    local state
    state=$(_load_state)

    if command -v jq >/dev/null 2>&1; then
        state=$(jq ".alerts[\"$alert_id\"] = $timestamp" <<< "$state")
    else
        # Simple replacement without jq (limited)
        if grep -q "\"$alert_id\":" <<< "$state"; then
            state=$(sed "s/\"$alert_id\":[0-9]*/\"$alert_id\":$timestamp/" <<< "$state")
        else
            state=$(sed "s/\"alerts\":{/\"alerts\":{\"$alert_id\":$timestamp,/" <<< "$state")
        fi
    fi

    _save_state "$state"
}

# ============================================================================
# Rate Limiting
# ============================================================================

_check_rate_limit() {
    local current_time
    current_time=$(date +%s)
    local state
    state=$(_load_state)

    local hour_start count

    if command -v jq >/dev/null 2>&1; then
        hour_start=$(jq -r '.hour_start // 0' <<< "$state")
        count=$(jq -r '.count // 0' <<< "$state")
    else
        hour_start=0
        count=0
    fi

    # Reset if hour has passed
    if (( current_time - hour_start > 3600 )); then
        hour_start=$current_time
        count=0
    fi

    # Check limit
    if (( count >= ALERT_RATE_LIMIT )); then
        return 1  # Rate limited
    fi

    # Update count
    ((count++))

    if command -v jq >/dev/null 2>&1; then
        state=$(jq ".hour_start = $hour_start | .count = $count" <<< "$state")
        _save_state "$state"
    fi

    return 0  # OK to send
}

# ============================================================================
# Deduplication
# ============================================================================

_should_send_alert() {
    local alert_id="$1"
    local current_time
    current_time=$(date +%s)

    local last_sent
    last_sent=$(_get_alert_timestamp "$alert_id")

    local dedup_seconds=$((ALERT_DEDUP_HOURS * 3600))

    if (( current_time - last_sent < dedup_seconds )); then
        return 1  # Duplicate, suppress
    fi

    return 0  # OK to send
}

# ============================================================================
# Public Functions
# ============================================================================

send_alert() {
    local level="$1"
    local message="$2"
    local alert_id="${3:-$(echo "$message" | md5sum | cut -d' ' -f1)}"

    # Check deduplication
    if ! _should_send_alert "$alert_id"; then
        echo "[ALERTS] Suppressed duplicate: $alert_id" >&2
        return 0
    fi

    # Check rate limit
    if ! _check_rate_limit; then
        echo "[ALERTS] Rate limited, not sending" >&2
        return 0
    fi

    # Format message with level
    local emoji
    case "$level" in
        INFO)     emoji="ℹ️" ;;
        WARNING)  emoji="⚠️" ;;
        CRITICAL) emoji="🚨" ;;
        SUCCESS)  emoji="✅" ;;
        RECOVERY) emoji="🔄" ;;
        *)        emoji="📢" ;;
    esac

    local formatted_message="${emoji} ${level}: ${message}"

    # Send via telegram
    if [[ -x "$TELEGRAM_SENDER" ]]; then
        if "$TELEGRAM_SENDER" "$formatted_message"; then
            # Record successful send
            _set_alert_timestamp "$alert_id" "$(date +%s)"
            echo "[ALERTS] Sent: $alert_id" >&2
            return 0
        else
            echo "[ALERTS] Failed to send: $alert_id" >&2
            return 1
        fi
    else
        echo "[ALERTS] Telegram sender not found: $TELEGRAM_SENDER" >&2
        return 1
    fi
}

# Convenience functions
send_info() {
    send_alert "INFO" "$1" "${2:-}"
}

send_warning() {
    send_alert "WARNING" "$1" "${2:-}"
}

send_critical() {
    send_alert "CRITICAL" "$1" "${2:-}"
}

send_recovery() {
    send_alert "RECOVERY" "$1" "${2:-}"
}

# Clear alert state (for recovery alerts)
clear_alert() {
    local alert_id="$1"
    _set_alert_timestamp "$alert_id" "0"
}

# Export functions
export -f alerts_init send_alert send_info send_warning send_critical send_recovery clear_alert
