#!/usr/bin/env bash
# Refuse to run a workflow whose target project is uncle's own primary
# checkout -- the tree these scripts are executing from. A driver run
# directly, with no UNCLE_PROJECT_ROOT set, defaults PROJECT_ROOT to ROOT
# (see the comment above ROOT/PROJECT_ROOT in stagegate.sh and
# change-workflow.sh); an unattended run then commits to the exact source
# tree a live editor or another session may be using at the same time.
#
# A linked git worktree (`git worktree add`) is a different, separate
# directory on disk and is unaffected by this: self-hosted dogfooding
# belongs there, not in the checkout uncle itself runs from. That
# distinction is what `-d "$root/.git"` tests -- a linked worktree's `.git`
# is a file (`gitdir: ...`), never a directory, so only the primary checkout
# trips this guard.
guard_against_self_target() {
    local root="$1" project_root="$2" allow="$3"
    [[ "$project_root" == "$root" ]] || return 0
    [[ -d "$root/.git" ]] || return 0
    [[ "$allow" != 1 ]] || return 0
    echo "Refusing to run against $root: it is the primary checkout uncle itself" >&2
    echo "is running from, not a project to change. A workflow here can collide" >&2
    echo "with a live editor or another session using the same files." >&2
    echo >&2
    echo "Use a linked git worktree instead (git worktree add ../uncle-<name>)," >&2
    echo "pass UNCLE_PROJECT_ROOT=<path> to target a different directory, or set" >&2
    echo "UNCLE_ALLOW_SELF_TARGET=1 (or --allow-self-target) to proceed anyway." >&2
    exit 1
}
