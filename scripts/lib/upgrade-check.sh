#!/usr/bin/env bash
# Startup update support. This file is sourced by uncle after argument parsing.

. "$ROOT/scripts/lib/running-workflow.sh"

upgrade_version_parts() {
    local version="${1#v}" base
    base="${version%%+*}"
    [[ "$base" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || return 1
    printf '%s %s %s %s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${version#"$base"}"
}

upgrade_available() {
    local local_version="$1" latest_tag="$2" local_parts latest_parts index
    local -a local_values latest_values
    local_parts="$(upgrade_version_parts "$local_version")" || return 2
    latest_parts="$(upgrade_version_parts "$latest_tag")" || return 2
    read -r -a local_values <<< "$local_parts"
    read -r -a latest_values <<< "$latest_parts"
    for index in 0 1 2; do
        ((10#${latest_values[index]} > 10#${local_values[index]})) && return 0
        ((10#${latest_values[index]} < 10#${local_values[index]})) && return 1
    done
    [[ -n "${local_values[3]}" && -z "${latest_values[3]}" ]] && return 0
    return 1
}

upgrade_valid_tag() { upgrade_version_parts "$1" >/dev/null; }

upgrade_run_with_timeout() {
    local output pid elapsed status
    output="$(mktemp "${TMPDIR:-/tmp}/uncle-upgrade-command.XXXXXX")" || return 1
    if command -v perl >/dev/null 2>&1; then
        perl -e '$seconds = shift; $child = fork; exit 1 unless defined $child; if (!$child) { exec @ARGV; exit 127; } $SIG{ALRM} = sub { kill "TERM", $child; waitpid $child, 0; exit 124; }; alarm $seconds; waitpid $child, 0; exit $? >> 8;' 5 "$@" > "$output" 2>/dev/null
        status=$?
        cat "$output"
        rm -f "$output"
        return "$status"
    fi
    "$@" > "$output" &
    pid=$!
    for elapsed in {1..50}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        rm -f "$output"
        return 124
    fi
    if wait "$pid"; then status=0; else status=$?; fi
    cat "$output"
    rm -f "$output"
    return "$status"
}

upgrade_fetch_latest_tag() {
    local tag=""
    if command -v gh >/dev/null 2>&1; then
        tag="$(upgrade_run_with_timeout gh release view --repo unclehq/uncle --json tagName --jq .tagName 2>/dev/null)" || tag=""
        if upgrade_valid_tag "$tag"; then printf '%s\n' "$tag"; return 0; fi
    fi
    if command -v curl >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
        tag="$(curl -sSf --max-time 5 'https://api.github.com/repos/unclehq/uncle/releases/latest' 2>/dev/null | jq -r .tag_name 2>/dev/null)" || tag=""
        upgrade_valid_tag "$tag" && { printf '%s\n' "$tag"; return 0; }
    fi
    return 1
}

upgrade_should_check() {
    [[ "${UNCLE_SKIP_UPGRADE:-}" != 1 ]] || return 1
    [[ " ${UNCLE_ARGS[*]:-} " != *' --unattended '* ]] || return 1
    [[ -t 0 ]] || return 1
    local pids pid
    pids="$(running_workflow_pids 2>/dev/null)" || return 1
    for pid in $pids; do [[ "$pid" != "$$" ]] && return 1; done
    return 0
}

upgrade_acquire_lock() {
    UPGRADE_LOCK_DIR="${UNCLE_UPGRADE_LOCK_DIR:-${TMPDIR:-/tmp}/uncle-upgrade.lock}"
    mkdir "$UPGRADE_LOCK_DIR" 2>/dev/null
}

upgrade_release_lock() {
    local lock_dir="${UPGRADE_LOCK_DIR:-${UNCLE_UPGRADE_LOCK_DIR:-${TMPDIR:-/tmp}/uncle-upgrade.lock}}"
    rmdir "$lock_dir" 2>/dev/null || true
    UPGRADE_LOCK_DIR=""
}

upgrade_verify_checksum() {
    local directory="$1" tag="$2" checksum
    checksum="$(find "$directory" -maxdepth 1 -type f -name '*.sha256' -print -quit)"
    if [[ -z "$checksum" ]]; then
        printf 'Warning: no checksum file for %s; skipping verification\n' "$tag" >&2
        return 0
    fi
    (cd "$directory" && sha256sum -c "$(basename "$checksum")") >/dev/null 2>&1
}

upgrade_download_and_install() {
    local local_version="$1" tag="$2" temp archive extracted
    temp="$(mktemp -d "${TMPDIR:-/tmp}/uncle-upgrade.XXXXXX")" || { printf 'Unable to prepare upgrade.\n' >&2; return 1; }
    if ! gh release download "$tag" --repo unclehq/uncle --archive tar.gz --dir "$temp"; then
        printf 'Upgrade download failed; continuing with %s.\n' "$local_version" >&2; rm -rf "$temp"; return 1
    fi
    archive="$(find "$temp" -maxdepth 1 -type f -name '*.tar.gz' -print -quit)"
    if [[ -z "$archive" ]] || ! upgrade_verify_checksum "$temp" "$tag"; then
        printf 'Upgrade verification failed; continuing with %s.\n' "$local_version" >&2; rm -rf "$temp"; return 1
    fi
    if ! tar -xzf "$archive" -C "$temp"; then
        printf 'Upgrade extraction failed; continuing with %s.\n' "$local_version" >&2; rm -rf "$temp"; return 1
    fi
    extracted="$(find "$temp" -mindepth 1 -maxdepth 1 -type d -print -quit)"
    if [[ -z "$extracted" ]] || ! UNCLE_ALLOW_LIVE_INSTALL=1 bash "$ROOT/install.sh" --source-dir "$extracted"; then
        printf 'Upgrade installation failed; continuing with %s.\n' "$local_version" >&2; rm -rf "$temp"; return 1
    fi
    rm -rf "$temp"
    upgrade_release_lock
    exec "${UNCLE_LAUNCHER_PATH:-$ROOT/uncle}" "${UNCLE_ORIGINAL_ARGS[@]}"
}

upgrade_check_and_run() {
    local tag local_version answer
    upgrade_acquire_lock || return 0
    upgrade_should_check || { upgrade_release_lock; return 0; }
    tag="$(upgrade_fetch_latest_tag)" || { upgrade_release_lock; return 0; }
    local_version="$(<"$ROOT/VERSION")"
    upgrade_available "$local_version" "$tag" || { upgrade_release_lock; return 0; }
    printf 'A new version %s is available (you have %s). Install? [y/N] ' "${tag#v}" "$local_version"
    IFS= read -r answer || { upgrade_release_lock; return 0; }
    case "$answer" in [yY]|[yY][eE][sS]) upgrade_download_and_install "$local_version" "$tag" ;; esac
    upgrade_release_lock
}
