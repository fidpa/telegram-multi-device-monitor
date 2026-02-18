#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# Centralized Logging Library for Bash Scripts
#
# Provides structured logging with multiple output targets:
# - File logging with rotation support
# - Journal/syslog integration
# - Stdout for interactive use
# - Structured key=value logging
#
# Usage:
#   source lib/logging.sh
#   log_info "Starting process"
#   log_error "Something failed"
#   log_info_structured "Operation complete" "DURATION=5s" "ITEMS=42"
#
# Configuration (set before sourcing):
#   SCRIPT_NAME - Script identifier (default: basename of $0)
#   LOG_FILE - Path to log file (default: /tmp/${SCRIPT_NAME}.log)
#   LOG_TO_JOURNAL - Enable journal logging (default: false)
#   LOG_TO_STDOUT - Enable stdout logging (default: true)
#   LOG_LEVEL - Minimum log level: DEBUG, INFO, WARN, ERROR (default: INFO)
#

# Prevent double-sourcing
[[ -n "${_LOGGING_SOURCED:-}" ]] && return 0
readonly _LOGGING_SOURCED=1

# ============================================================================
# Configuration
# ============================================================================

# Script name (set before sourcing or defaults to basename)
SCRIPT_NAME="${SCRIPT_NAME:-$(basename "${0:-script}" .sh)}"

# Log file path
LOG_FILE="${LOG_FILE:-/tmp/${SCRIPT_NAME}.log}"

# Output targets
LOG_TO_JOURNAL="${LOG_TO_JOURNAL:-false}"
LOG_TO_STDOUT="${LOG_TO_STDOUT:-true}"
LOG_TO_FILE="${LOG_TO_FILE:-true}"

# Log level (DEBUG=0, INFO=1, WARN=2, ERROR=3)
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# ============================================================================
# Internal Functions
# ============================================================================

_log_level_to_int() {
    case "${1:-INFO}" in
        DEBUG) echo 0 ;;
        INFO)  echo 1 ;;
        WARN)  echo 2 ;;
        ERROR) echo 3 ;;
        *)     echo 1 ;;
    esac
}

_should_log() {
    local msg_level="$1"
    local min_level
    min_level=$(_log_level_to_int "$LOG_LEVEL")
    local this_level
    this_level=$(_log_level_to_int "$msg_level")

    [[ "$this_level" -ge "$min_level" ]]
}

_format_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

_log() {
    local level="$1"
    shift
    local message="$*"

    # Check if we should log this level
    _should_log "$level" || return 0

    local timestamp
    timestamp=$(_format_timestamp)
    local formatted="[$timestamp] [$SCRIPT_NAME] [$level] $message"

    # File output
    if [[ "$LOG_TO_FILE" == "true" ]] && [[ -n "$LOG_FILE" ]]; then
        # Create log directory if needed
        local log_dir
        log_dir=$(dirname "$LOG_FILE")
        if [[ -w "$log_dir" ]] || mkdir -p "$log_dir" 2>/dev/null; then
            echo "$formatted" >> "$LOG_FILE" 2>/dev/null || true
        fi
    fi

    # Stdout output
    if [[ "$LOG_TO_STDOUT" == "true" ]]; then
        case "$level" in
            ERROR) echo "$formatted" >&2 ;;
            *)     echo "$formatted" ;;
        esac
    fi

    # Journal output
    if [[ "$LOG_TO_JOURNAL" == "true" ]]; then
        local priority
        case "$level" in
            DEBUG) priority="debug" ;;
            INFO)  priority="info" ;;
            WARN)  priority="warning" ;;
            ERROR) priority="err" ;;
            *)     priority="info" ;;
        esac

        logger -t "$SCRIPT_NAME" -p "user.$priority" "$message" 2>/dev/null || true
    fi
}

# ============================================================================
# Public Logging Functions
# ============================================================================

log_debug() {
    _log DEBUG "$@"
}

log_info() {
    _log INFO "$@"
}

log_warn() {
    _log WARN "$@"
}

log_error() {
    _log ERROR "$@"
}

# ============================================================================
# Structured Logging
# ============================================================================

log_info_structured() {
    local message="$1"
    shift
    local kvpairs=""

    for kv in "$@"; do
        kvpairs+=" $kv"
    done

    _log INFO "$message |$kvpairs"
}

log_error_structured() {
    local message="$1"
    shift
    local kvpairs=""

    for kv in "$@"; do
        kvpairs+=" $kv"
    done

    _log ERROR "$message |$kvpairs"
}

# ============================================================================
# Utility Functions
# ============================================================================

# Log function execution start/end
log_function_start() {
    log_debug "ENTER ${FUNCNAME[1]:-main}()"
}

log_function_end() {
    local exit_code="${1:-0}"
    log_debug "EXIT ${FUNCNAME[1]:-main}() rc=$exit_code"
}

# Create log rotation (call periodically)
rotate_log() {
    local max_size="${1:-10485760}"  # 10MB default
    local keep="${2:-3}"

    [[ ! -f "$LOG_FILE" ]] && return 0

    local size
    size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)

    if [[ "$size" -gt "$max_size" ]]; then
        for ((i=keep-1; i>=1; i--)); do
            [[ -f "${LOG_FILE}.$i" ]] && mv "${LOG_FILE}.$i" "${LOG_FILE}.$((i+1))"
        done
        mv "$LOG_FILE" "${LOG_FILE}.1"
        log_info "Log rotated (was ${size} bytes)"
    fi
}

# Export all functions
export -f log_debug log_info log_warn log_error
export -f log_info_structured log_error_structured
export -f log_function_start log_function_end rotate_log
