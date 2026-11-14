#!/usr/bin/env bash
# Run policy: the single place that decides how a run relates to git.
#
#   app    builds start on a clean main in place (no worktree), or are refused.
#   change runs in place get a new branch unless already on their own run branch.
#   issue  runs are untouched.
#
# Sourced by launchers and drivers. Functions return 1 on refusal after printing
# the reason to stderr; callers propagate with `|| exit 1`. Nothing here deletes
# or force-modifies a branch or worktree. UNCLE_RUN_POLICY=off skips the app
# preflight and the change guard (legacy suites).

run_policy_kind() {
    case "${1:-}" in
        stagegate.sh|create_app|run_app) echo app ;;
        change-workflow.sh|change_request|create_change|run_change) echo change ;;
        from-issue.sh|github_issue) echo issue ;;
        *) echo unknown ;;
    esac
}

run_policy_worktree_wanted() {
    [[ "${1:-}" != "app" ]]
}

_RUN_POLICY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

run_policy_off() {
    [[ "${UNCLE_RUN_POLICY:-}" == "off" ]] || return 1
    echo "Run policy disabled by UNCLE_RUN_POLICY=off." >&2
    return 0
}

_run_policy_state_dir() {
    echo "${STATE_DIR:-.uncle/workflow}"
}

# True when the project is a git work tree with a born HEAD.
_run_policy_born() {
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        && git rev-parse --verify --quiet HEAD >/dev/null 2>&1
}

# Current local branch name; empty on detached HEAD.
_run_policy_current() {
    git symbolic-ref --short -q HEAD 2>/dev/null
}

# main; master only when no local main exists. Empty when neither exists.
_run_policy_default() {
    if git show-ref --verify --quiet refs/heads/main; then
        echo main
    elif git show-ref --verify --quiet refs/heads/master; then
        echo master
    fi
}

_run_policy_is_default() {
    local b="$1" d
    d="$(_run_policy_default)"
    [[ -n "$d" && "$b" == "$d" ]]
}

# A worktree-owned marker is valid only in a linked worktree on an existing
# local non-default branch.
_run_policy_valid_marker() {
    local cur
    [[ -e "$(_run_policy_state_dir)/worktree-owned" ]] || return 1
    [[ "$(git rev-parse --git-dir 2>/dev/null)" != "$(git rev-parse --git-common-dir 2>/dev/null)" ]] || return 1
    cur="$(_run_policy_current)"
    [[ -n "$cur" ]] || return 1
    git show-ref --verify --quiet "refs/heads/$cur" || return 1
    _run_policy_is_default "$cur" && return 1
    return 0
}

# True when a non-default current branch equals a recorded, existing run-branch.
_run_policy_on_run_branch() {
    local cur rb f
    cur="$(_run_policy_current)"
    [[ -n "$cur" ]] || return 1
    _run_policy_is_default "$cur" && return 1
    f="$(_run_policy_state_dir)/run-branch"
    [[ -f "$f" ]] || return 1
    rb="$(head -n 1 "$f" 2>/dev/null | tr -d '\r')"
    [[ -n "$rb" && "$rb" == "$cur" ]] || return 1
    git show-ref --verify --quiet "refs/heads/$rb"
}

# Prints dirty paths (control characters stripped), one per line, in
# `git status` order. Exclusions apply to untracked entries only.
_run_policy_dirty_paths() {
    local entry xy path skip=0
    while IFS= read -r -d '' entry; do
        if [[ "$skip" == 1 ]]; then skip=0; continue; fi
        xy="${entry:0:2}"
        path="${entry:3}"
        case "$xy" in
            R?|C?|?R|?C) skip=1 ;;
        esac
        if [[ "$xy" == "??" ]]; then
            case "$path" in
                .uncle|.uncle/*|REQUIREMENTS.md|CHANGE_REQUEST.md) continue ;;
            esac
        fi
        printf '%s\n' "$path" | tr -d '[:cntrl:]'
        # tr removed the newline too; restore it
        echo
    done < <(git status --porcelain -z --untracked-files=all 2>/dev/null) | sed '/^$/d'
}

# The BH-7 notice: only for explicit WORKFLOW_WORKTREE=1 on a fresh app start.
run_policy_app_notice() {
    [[ "${WORKFLOW_WORKTREE:-}" == "1" ]] || return 0
    [[ -f "${STATE_FILE:-$(_run_policy_state_dir)/state}" ]] && return 0
    _run_policy_valid_marker && return 0
    [[ -e "$(_run_policy_state_dir)/worktree-owned" ]] && return 0
    echo "Note: app builds run in place on main; a worktree was not used." >&2
    return 0
}

run_policy_app_preflight() {
    local cur sha paths n

    run_policy_off && return 0
    # Resume: a parseable state file means the run already started.
    [[ -s "${STATE_FILE:-$(_run_policy_state_dir)/state}" ]] && return 0
    # Legacy owned app worktree (D-10): not preflighted.
    _run_policy_valid_marker && return 0
    _run_policy_born || return 0

    cur="$(_run_policy_current)"
    if [[ -z "$cur" ]]; then
        sha="$(git rev-parse --short HEAD 2>/dev/null)"
        echo "Refusing app build: HEAD is detached at $sha, not on main. Switch to main (git switch main) and retry." >&2
        return 1
    fi
    if ! _run_policy_is_default "$cur"; then
        echo "Refusing app build: current branch is '$cur', not main. Switch to main (git switch main) and retry." >&2
        return 1
    fi

    paths="$(_run_policy_dirty_paths)"
    if [[ -n "$paths" ]]; then
        n="$(printf '%s\n' "$paths" | wc -l | tr -d ' ')"
        {
            echo "Refusing app build: the working tree on '$cur' has uncommitted changes. Commit or stash them and retry:"
            printf '%s\n' "$paths" | head -n 10 | sed 's/^/  /'
            if [[ "$n" -gt 10 ]]; then
                echo "and $((n - 10)) more"
            fi
        } >&2
        return 1
    fi
    return 0
}

# Commit-free base snapshot (hand-off only). Builds a tree in an isolated
# temporary index from the work tree (tracked + untracked, never `.uncle/`),
# prints the tree id on stdout and, when $1 is given, writes a
# "<blob-sha><TAB><path>" inventory there. Creates no commit or ref and never
# touches the real index, work tree or HEAD. Returns 1 on any failure.
run_policy_seed_base() {
    local inv="${1:-}" tmp idx tree gd rc=0 p

    [[ "${UNCLE_PUBLISH_MODE:-}" == "handoff" ]] || return 0
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    gd="$(git rev-parse --git-dir 2>/dev/null)" || return 1
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/run-policy-seed.XXXXXX")" || return 1
    idx="$tmp/index"
    (
        # Subshell: GIT_INDEX_FILE must not leak into the caller.
        export GIT_INDEX_FILE="$idx"
        git ls-files -z --cached --others --exclude-standard -- . ':(exclude).uncle' ':(exclude).uncle/**' \
            | while IFS= read -r -d '' p; do
                case "$p" in .uncle|.uncle/*) continue ;; esac
                [[ -e "$p" || -L "$p" ]] && printf '%s\0' "$p"
            done > "$tmp/paths" \
        && git update-index --add -z --stdin < "$tmp/paths" \
        && tree="$(git write-tree)" \
        && [[ -n "$tree" ]] \
        && ! git ls-tree -r --name-only "$tree" | grep -qE '^\.uncle(/|$)' \
        && { [[ -z "$inv" ]] || git ls-tree -r "$tree" | sed -E 's/^[0-7]+ [a-z]+ ([0-9a-f]+)\t/\1\t/' > "$inv"; } \
        && printf '%s\n' "$tree"
    ) > "$tmp/out" 2>/dev/null || rc=1
    [[ "$rc" == 0 ]] && cat "$tmp/out"
    rm -rf "$tmp"
    [[ "$rc" == 0 ]]
}

# Hand-off base evidence: snapshot tree (isolated index) plus an unsigned
# evidence commit under the private ref refs/uncle/handoff-base. HEAD, branches,
# the real index and the work tree are never touched; nothing is pushed.
# Failure warns and returns 0 (HEAD stays unborn).
run_policy_snapshot_base() {
    local tree commit
    [[ "${UNCLE_PUBLISH_MODE:-}" == "handoff" ]] || return 0
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    git rev-parse --verify --quiet HEAD >/dev/null 2>&1 && return 0
    if tree="$(run_policy_seed_base)" && [[ -n "$tree" ]] \
       && commit="$(git -c commit.gpgsign=false -c tag.gpgsign=false -c user.name=Uncle -c user.email=uncle@localhost \
            commit-tree --no-gpg-sign -m "uncle hand-off base snapshot" "$tree" </dev/null)" && [[ -n "$commit" ]] \
       && git update-ref refs/uncle/handoff-base "$commit"; then
        export UNCLE_HANDOFF_BASE_TREE="$tree" UNCLE_HANDOFF_BASE_COMMIT="$commit"
        echo "Run policy: hand-off base snapshot $commit (tree $tree); HEAD left unborn." >&2
    else
        echo "Run policy: warning: could not capture a hand-off base snapshot; continuing without one." >&2
    fi
    return 0
}

run_policy_change_branch() {
    local cur base name n=2 dir

    run_policy_off && return 0
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
       || ! git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
        run_policy_snapshot_base
        echo "Run policy: no git history to branch from; continuing without a run branch." >&2
        return 0
    fi

    cur="$(_run_policy_current)"
    if [[ -n "$cur" ]]; then
        _run_policy_on_run_branch && return 0
        _run_policy_valid_marker && return 0
        # A linked worktree on its own non-default branch is already isolated,
        # even when nothing marked it (a worktree made from the TUI or by hand
        # has no worktree-owned file). Branching again here moved the checkout
        # to "<branch>-2" after the PR journal had recorded "<branch>", so
        # publication saw "HEAD or branch changed" and made no PR. Adopt the
        # branch as the run branch instead.
        if [[ "$(git rev-parse --git-dir 2>/dev/null)" != "$(git rev-parse --git-common-dir 2>/dev/null)" ]] \
           && ! _run_policy_is_default "$cur" \
           && git show-ref --verify --quiet "refs/heads/$cur"; then
            dir="$(_run_policy_state_dir)"
            mkdir -p "$dir" && printf '%s\n' "$cur" > "$dir/run-branch"
            return 0
        fi
    fi

    base="$( ROOT="${ROOT:-$_RUN_POLICY_ROOT}" bash -c \
        '. "$ROOT/scripts/lib/change-pr.sh"; change_pr_engine run-branch-name' 2>/dev/null | tail -n 1)"
    if [[ -z "$base" ]]; then
        echo "Run policy: could not derive a run branch name (empty name); nothing was changed." >&2
        return 1
    fi
    if [[ "$base" == -* ]] || ! git check-ref-format --branch "$base" >/dev/null 2>&1; then
        echo "Run policy: derived run branch name '$base' is invalid; nothing was changed." >&2
        return 1
    fi

    name="$base"
    while git show-ref --verify --quiet "refs/heads/$name"; do
        name="$base-$n"
        n=$((n + 1))
        if [[ "$n" -gt 64 ]]; then
            echo "Run policy: run branch names exhausted ($base through $base-64 all exist); nothing was changed." >&2
            return 1
        fi
    done
    if ! git check-ref-format --branch "$name" >/dev/null 2>&1; then
        echo "Run policy: run branch name '$name' is invalid; nothing was changed." >&2
        return 1
    fi

    if ! git switch -c "$name" >/dev/null 2>&1; then
        echo "Run policy: git switch -c $name failed; the checkout is unchanged." >&2
        return 1
    fi
    dir="$(_run_policy_state_dir)"
    mkdir -p "$dir" && printf '%s\n' "$name" > "$dir/run-branch"
    echo "Branch: $name"
    return 0
}
