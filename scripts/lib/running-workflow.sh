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
    # The drivers, by the script they were invoked as: argv[0], or argv[1] when
    # a shell runs it. Matching the path anywhere in the command line would
    # count a grep or an editor that merely mentions stagegate.sh, and refuse
    # an install because someone had the file open.
    #
    # Always succeeds. pgrep exits 1 when nothing matches, and a caller that
    # assigns this under `set -o pipefail` would take that as an error -- as one
    # did, failing only on a machine where no workflow happened to be running.
    ps -Ao pid=,args= 2>/dev/null | awk '
        {
            pid = $1
            first = $2
            second = (NF >= 3 ? $3 : "")
            driver = "(stagegate|change-workflow)\\.sh$"
            if (first ~ driver) { printf "%s ", pid; next }
            if (first ~ /(^|\/)(ba|z|da)?sh$/ && second ~ driver) printf "%s ", pid
        }
    ' || true
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
