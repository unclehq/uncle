#!/usr/bin/env bash
# Called after the workflow lock is acquired, from the project directory.
uncle_ensure_project_git() {
    local inside directory
    command -v git >/dev/null 2>&1 || { echo 'Git is required to start a build.' >&2; return 1; }
    if inside="$(git rev-parse --is-inside-work-tree 2>/dev/null)"; then
        [[ "$inside" == true ]] && return 0
        echo 'Cannot build inside a bare Git repository.' >&2
        return 1
    fi
    # A broken or inaccessible repository is not an absent repository. Never
    # create a nested checkout to hide a Git error, including unsafe ownership.
    directory="$PWD"
    while :; do
        if [[ -e "$directory/.git" || -L "$directory/.git" ]]; then
            echo 'Cannot access the existing Git repository; repair it before building.' >&2
            return 1
        fi
        [[ "$directory" != / ]] || break
        directory="$(dirname "$directory")"
    done
    if [[ -n "${GIT_DIR:-}${GIT_WORK_TREE:-}" ]]; then
        echo 'Git environment points to an unavailable repository; check GIT_DIR/GIT_WORK_TREE.' >&2
        return 1
    fi
    git init --quiet || return 1
    echo "Initialized Git repository in $PWD"
}
