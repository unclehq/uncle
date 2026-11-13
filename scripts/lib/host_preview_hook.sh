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
