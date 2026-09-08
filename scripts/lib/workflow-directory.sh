#!/usr/bin/env bash
# Preserve existing runs when upgrading from the old state-directory name.
workflow_directory_migrate() {
    local parent="${1:-.}/.uncle" holder
    if [[ -d "$parent/workspace" && ! -e "$parent/workflow" ]]; then
        holder="$(cat "$parent/workspace/lock/pid" 2>/dev/null || true)"
        if [[ -n "$holder" ]] && kill -0 "$holder" 2>/dev/null; then
            echo "Wait for the running workflow (pid $holder) to finish before migrating $parent/workspace." >&2
            return 1
        fi
        mv "$parent/workspace" "$parent/workflow"
    elif [[ -e "$parent/workspace" && -e "$parent/workflow" ]]; then
        echo "Both $parent/workspace and $parent/workflow exist. Move the old directory aside before continuing; neither directory was changed." >&2
        return 1
    fi
}
