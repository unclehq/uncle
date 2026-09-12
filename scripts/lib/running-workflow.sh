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
    local processes helper
    case "${OSTYPE:-}" in
        msys*|cygwin*|win32*)
            helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/running-workflow.ps1"
            if command -v cygpath >/dev/null 2>&1; then helper="$(cygpath -w "$helper")"; fi
            powershell.exe -NoProfile -NonInteractive -File "$helper" | tr '\r\n' '  '
            return "${PIPESTATUS[0]}"
            ;;
    esac
    processes="$(ps -Ao pid=,args= 2>/dev/null)" || return 2
    printf '%s\n' "$processes" | awk '
        {
            pid = $1
            first = $2
            second = (NF >= 3 ? $3 : "")
            driver = "(stagegate|change-workflow|from-issue)\\.sh$"
            # The launcher counts too. It owns the run a driver is executing,
            # and replacing the keg under it breaks the driver it spawns next
            # -- which is how an upgrade mid-run loses hours of work.
            launcher = "(^|/)uncle$"
            tui = "(^|/)uncle_tui\\.py$"
            if (first ~ driver || first ~ launcher) { printf "%s ", pid; next }
            if (first ~ /(^|\/)(ba|z|da)?sh$/ && (second ~ driver || second ~ launcher)) {
                printf "%s ", pid; next
            }
            # Only when a Python interpreter is running it: "vim uncle_tui.py"
            # is someone reading the file, not a live session.
            if (first ~ /(^|\/)[Pp]ython[0-9.]*$/ && second ~ tui) printf "%s ", pid
        }
    '
}

running_workflow_report() {
    local pids
    if ! pids="$(running_workflow_pids)"; then
        echo "Cannot determine whether a workflow is running; refusing to replace the installation." >&2
        echo "Restore process inspection or explicitly use --force-live." >&2
        return 0
    fi
    [[ -n "${pids// /}" ]] || return 1
    echo "A uncle workflow is running (pid ${pids% })." >&2
    echo "Installing now replaces the scripts it is executing, mid-run." >&2
    echo "Wait for it to reach a gate and stop, or rerun with --force-live." >&2
    return 0
}
