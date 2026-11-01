#!/usr/bin/env bash
# Warm the package and browser caches for the final build while planning and review run.
# See install_warm.py: it fills npm's and Playwright's machine-wide caches from a temporary
# directory, never touches the project, and never fails a stage.
#
# On by default.  WORKFLOW_INSTALL_WARM=0 turns it off.

INSTALL_WARM_PID=""

# install_warm_start <plan.md> — detached; returns immediately.  A running warm-up is left to finish:
# the cache is shared, so a second plan only adds the packages the first did not name.
install_warm_start() {
    [[ "${WORKFLOW_INSTALL_WARM:-1}" == 1 ]] || return 0
    [[ -s "$1" ]] || return 0
    if [[ -n "$INSTALL_WARM_PID" ]] && kill -0 "$INSTALL_WARM_PID" 2>/dev/null; then
        return 0
    fi
    mkdir -p "$STATE_DIR" "$LOG_DIR" 2>/dev/null || return 0
    python3 -B "${INSTALL_WARM_PY:-$ROOT/scripts/lib/install_warm.py}" "$1" "$STATE_DIR" \
        > "$LOG_DIR/install-warm.log" 2>&1 < /dev/null &
    INSTALL_WARM_PID=$!
}

# install_warm_cancel — from the EXIT trap.  A download must not outlive its run.
install_warm_cancel() {
    if [[ -n "$INSTALL_WARM_PID" ]] && kill -0 "$INSTALL_WARM_PID" 2>/dev/null; then
        # The helper owns its child groups and releases the install lock after cleanup.
        kill "$INSTALL_WARM_PID" 2>/dev/null || true
        wait "$INSTALL_WARM_PID" 2>/dev/null || true
    fi
    INSTALL_WARM_PID=""
    return 0
}
