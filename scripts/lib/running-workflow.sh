#!/usr/bin/env bash
# Is a workflow running right now?
#
# Upgrading uncle while a driver is running replaces the scripts that driver is
# executing. Homebrew makes it worse than a race: `brew reinstall` deletes the
# versioned keg, so a driver launched from it starts failing on files that no
# longer exist, mid-run, after hours of work. The launcher now goes through the
# opt symlink so the path keeps resolving, but swapping the code under a live
# run is still not something to do by accident.
running_workflow_pids() {
    # The drivers, by the path they are invoked as. Not the TUI: sitting at a
    # menu is not a run, and refusing to upgrade then would be refusing for no
    # reason.
    pgrep -f '(stagegate|change-workflow)\.sh' 2>/dev/null | tr '\n' ' '
}

running_workflow_report() {
    local pids
    pids="$(running_workflow_pids)"
    [[ -n "${pids// /}" ]] || return 1
    echo "A uncle workflow is running (pid ${pids% })." >&2
    echo "Installing now replaces the scripts it is executing, mid-run." >&2
    echo "Wait for it to reach a gate and stop, or rerun with --force-live." >&2
    return 0
}
