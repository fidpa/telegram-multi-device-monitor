#!/bin/bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 telegram-multi-device-monitor contributors
#
# Secure File Operations Library for Bash Scripts
#
# Provides safe file operations with:
# - Atomic writes (write to temp, then rename)
# - Permission management
# - Safe path handling
# - Temporary file management
#
# Usage:
#   source lib/file_utils.sh
#   safe_write "/etc/config" "content here"
#   temp_file=$(create_temp_file "prefix")
#

# Prevent double-sourcing
[[ -n "${_FILE_UTILS_SOURCED:-}" ]] && return 0
readonly _FILE_UTILS_SOURCED=1

# ============================================================================
# Safe File Operations
# ============================================================================

safe_write() {
    # Atomically write content to file using temp file + rename
    # Usage: safe_write "/path/to/file" "content" [mode]
    local target_file="$1"
    local content="$2"
    local mode="${3:-644}"

    local target_dir
    target_dir=$(dirname "$target_file")

    # Ensure directory exists
    if [[ ! -d "$target_dir" ]]; then
        mkdir -p "$target_dir" || return 1
    fi

    # Create temp file in same directory (for atomic rename)
    local temp_file
    temp_file=$(mktemp "${target_dir}/.tmp.XXXXXX") || return 1

    # Write content
    echo "$content" > "$temp_file" || {
        rm -f "$temp_file"
        return 1
    }

    # Set permissions before rename
    chmod "$mode" "$temp_file" || {
        rm -f "$temp_file"
        return 1
    }

    # Atomic rename
    mv "$temp_file" "$target_file" || {
        rm -f "$temp_file"
        return 1
    }

    return 0
}

safe_append() {
    # Safely append content to file
    # Usage: safe_append "/path/to/file" "content"
    local target_file="$1"
    local content="$2"

    # Use file locking if flock available
    if command -v flock >/dev/null 2>&1; then
        (
            flock -w 5 200 || return 1
            echo "$content" >> "$target_file"
        ) 200>"${target_file}.lock"
        rm -f "${target_file}.lock"
    else
        echo "$content" >> "$target_file"
    fi
}

# ============================================================================
# Temporary Files
# ============================================================================

create_temp_file() {
    # Create temporary file with optional prefix
    # Usage: temp_file=$(create_temp_file "myprefix")
    local prefix="${1:-tmp}"
    mktemp "/tmp/${prefix}.XXXXXX"
}

create_temp_dir() {
    # Create temporary directory with optional prefix
    # Usage: temp_dir=$(create_temp_dir "myprefix")
    local prefix="${1:-tmp}"
    mktemp -d "/tmp/${prefix}.XXXXXX"
}

cleanup_temp() {
    # Remove temporary file/directory if it matches pattern
    # Usage: cleanup_temp "/tmp/myprefix.XXXXXX"
    local path="$1"

    # Safety check: only remove if in /tmp
    if [[ "$path" == /tmp/* ]]; then
        rm -rf "$path"
    fi
}

# ============================================================================
# Path Handling
# ============================================================================

resolve_path() {
    # Resolve path to absolute, following symlinks
    # Usage: abs_path=$(resolve_path "./relative/path")
    local path="$1"

    if [[ -e "$path" ]]; then
        readlink -f "$path"
    else
        # For non-existent paths, resolve parent
        local dir
        dir=$(dirname "$path")
        local base
        base=$(basename "$path")

        if [[ -d "$dir" ]]; then
            echo "$(readlink -f "$dir")/$base"
        else
            echo "$path"
        fi
    fi
}

ensure_dir() {
    # Ensure directory exists with optional permissions
    # Usage: ensure_dir "/path/to/dir" [mode] [owner]
    local dir="$1"
    local mode="${2:-755}"
    local owner="${3:-}"

    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir" || return 1
    fi

    chmod "$mode" "$dir" || return 1

    if [[ -n "$owner" ]]; then
        chown "$owner" "$dir" || return 1
    fi

    return 0
}

# ============================================================================
# File Checks
# ============================================================================

file_exists_readable() {
    # Check if file exists and is readable
    [[ -f "$1" ]] && [[ -r "$1" ]]
}

file_exists_writable() {
    # Check if file exists and is writable (or directory is writable)
    if [[ -f "$1" ]]; then
        [[ -w "$1" ]]
    else
        [[ -w "$(dirname "$1")" ]]
    fi
}

file_age_seconds() {
    # Get file age in seconds
    # Usage: age=$(file_age_seconds "/path/to/file")
    local file="$1"

    if [[ ! -f "$file" ]]; then
        echo "-1"
        return 1
    fi

    local mtime
    mtime=$(stat -c %Y "$file" 2>/dev/null) || return 1
    local now
    now=$(date +%s)

    echo $((now - mtime))
}

file_is_stale() {
    # Check if file is older than threshold
    # Usage: if file_is_stale "/path/to/file" 3600; then ...
    local file="$1"
    local max_age="${2:-3600}"

    local age
    age=$(file_age_seconds "$file")

    [[ "$age" -gt "$max_age" ]]
}

# ============================================================================
# Config File Helpers
# ============================================================================

read_config_value() {
    # Read value from KEY=VALUE config file
    # Usage: value=$(read_config_value "/etc/config" "MY_KEY")
    local config_file="$1"
    local key="$2"

    if [[ ! -f "$config_file" ]]; then
        return 1
    fi

    grep "^${key}=" "$config_file" | cut -d= -f2- | tr -d '"'"'"
}

write_config_value() {
    # Write/update value in KEY=VALUE config file
    # Usage: write_config_value "/etc/config" "MY_KEY" "my_value"
    local config_file="$1"
    local key="$2"
    local value="$3"

    # Validate key format (only safe characters: letter/underscore start, alphanumeric/underscore)
    if [[ ! "$key" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
        echo "[FILE_UTILS] Invalid config key: $key" >&2
        return 1
    fi

    # Create file if not exists
    if [[ ! -f "$config_file" ]]; then
        printf '%s=%s\n' "$key" "$value" > "$config_file"
        return 0
    fi

    # Update or append
    if grep -q "^${key}=" "$config_file"; then
        # Escape value for sed replacement (escape &, |, /, and \)
        # Note: | is our sed delimiter, so it MUST be escaped
        local escaped_value
        escaped_value=$(printf '%s' "$value" | sed 's/[&|/\]/\\&/g')
        sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$config_file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$config_file"
    fi
}

# Export functions
export -f safe_write safe_append
export -f create_temp_file create_temp_dir cleanup_temp
export -f resolve_path ensure_dir
export -f file_exists_readable file_exists_writable file_age_seconds file_is_stale
export -f read_config_value write_config_value
