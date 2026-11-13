#!/usr/bin/env bash
# Shared COMPLETE-branch hook for stagegate.sh and change-workflow.sh (D-2, D-10).
# Sourced, never executed. Host mode is decided only by host_preview.py mode-check
# (hosted mode, UNCLE_HOSTED=1); otherwise it does nothing at all.
# WORKFLOW_PREVIEW_OPEN_BROWSER=0 is set only inside the subshell around the call
# and never exported to the driver environment. Failures are ignored (INV-1).
uncle_host_preview_hook() {
    local lib="${ROOT:?}/scripts/lib"
    python3 -B "$lib/host_preview.py" mode-check >/dev/null 2>&1 || return 0
    # The live preview (the early page) may hold the preview port; stop it so the finished app takes the same one.
    python3 -B "$lib/preview_server.py" stop "${STATE_DIR:-$PWD/.uncle/workflow}" >/dev/null 2>&1 || true
    (
        export WORKFLOW_PREVIEW_OPEN_BROWSER=0
        python3 -B "$lib/host_preview.py" serve "$PWD"
    ) || true
    return 0
}

# uncle_host_preview_early — the first thing a hosted run does: serve a "starting" page on the host's address and write
# .uncle/preview.json, so the host can show the preview from the first second instead of waiting for a stage to build one.
# Hosted mode only; otherwise it does nothing. The later preview build and the Vite hand-over reuse this server (its pid file is
# what they look for), and on_exit stops it. HOST_PREVIEW_EARLY=1 tells the exit handler this run started one. Never fails.
uncle_host_preview_early() {
    local lib="${ROOT:?}/scripts/lib" state="${STATE_DIR:?}" root="${PROJECT_ROOT:-$PWD}" i
    python3 -B "$lib/host_preview.py" mode-check >/dev/null 2>&1 || return 0
    if [[ -s "$state/preview-server.pid" ]] && kill -0 "$(cat "$state/preview-server.pid" 2>/dev/null)" 2>/dev/null; then
        return 0
    fi
    mkdir -p "$state" 2>/dev/null || return 0
    python3 -B "$lib/preview_server.py" early "$root" "$state" > "$state/preview-early.log" 2>&1 < /dev/null &
    HOST_PREVIEW_EARLY=1
    # Do not return before the record exists: the host reads it right away.
    for ((i = 0; i < 40; i++)); do
        [[ -s "$root/.uncle/preview.json" ]] && break
        sleep 0.1
    done
    return 0
}
