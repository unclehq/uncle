#!/usr/bin/env bash
# Git worktrees for `from-issue.sh --worktree` (Issue 64).
#
# Sourced by from-issue.sh for worktree_default_dir / worktree_create /
# worktree_remove; `bash scripts/lib/worktrees.sh remove <dir>` is the CLI for
# removing a finished run by hand. Every refusal returns 1 before any write.
# No path here deletes a branch or forces a removal: a worktree run's branch is
# the PR head, and git itself refuses to remove a dirty tree.
#
# bash 3.2 compatible.

WORKTREES_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$WORKTREES_LIB_DIR/state.sh"

# Physical path of an existing directory; empty when it does not exist.
worktree_real() {
    (cd "$1" 2>/dev/null && pwd -P)
}

# worktree_default_dir <project-root> <issue> — sibling of the project.
worktree_default_dir() {
    local root="$1" issue="$2"
    printf '%s/%s-issue-%s' "$(dirname "$root")" "$(basename "$root")" "$issue"
}

# worktree_registered <git-dir> <dir> — true when git lists <dir> as a worktree.
worktree_registered() {
    local repo="$1" target="$2" line path
    target="$(worktree_real "$target")"
    [[ -n "$target" ]] || return 1
    while IFS= read -r line; do
        case "$line" in
            "worktree "*)
                path="$(worktree_real "${line#worktree }")"
                if [[ "$path" == "$target" ]]; then
                    return 0
                fi
                ;;
        esac
    done < <(git -C "$repo" worktree list --porcelain 2>/dev/null)
    return 1
}

# worktree_create <dir> <branch> — in the current project root. Refuses, with
# nothing written, when the branch exists, the directory is non-empty or
# registered, or the directory lies inside the project. Copies .uncle/config
# when the project has one.
worktree_create() {
    local dir="$1" branch="$2" root parent abs

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Not a git repository: $PWD" >&2
        return 1
    fi
    if ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
        echo "Invalid branch name: $branch" >&2
        return 1
    fi
    if git show-ref --verify --quiet "refs/heads/$branch"; then
        echo "Branch already exists: $branch" >&2
        return 1
    fi
    root="$(pwd -P)"
    parent="$(worktree_real "$(dirname "$dir")")"
    if [[ -z "$parent" ]]; then
        echo "Parent directory does not exist: $(dirname "$dir")" >&2
        return 1
    fi
    abs="$parent/$(basename "$dir")"
    case "$abs" in
        "$root"|"$root"/*)
            echo "Worktree directory must not be inside the project: $dir" >&2
            return 1
            ;;
    esac
    if [[ -e "$dir" ]]; then
        if [[ ! -d "$dir" ]] || [[ -n "$(ls -A "$dir" 2>/dev/null)" ]]; then
            echo "Directory is not empty: $dir" >&2
            return 1
        fi
        if worktree_registered "$root" "$dir"; then
            echo "Directory is already a registered worktree: $dir" >&2
            return 1
        fi
    fi

    if ! git worktree add "$dir" -b "$branch" HEAD; then
        return 1
    fi

    if [[ -e .uncle/config ]]; then
        if ! { mkdir -p "$dir/.uncle" && cp -p .uncle/config "$dir/.uncle/config"; }; then
            # Roll back the directory only. The branch is a ref the person may
            # already expect to exist; it is never deleted here (I-4).
            rm -rf "$dir/.uncle"
            git worktree remove "$dir" >/dev/null 2>&1 || true
            echo "Could not copy .uncle/config into $dir; worktree removed." >&2
            echo "branch $branch kept; delete with: git branch -d $branch" >&2
            return 1
        fi
    fi

    # A worktree checks out a commit, so its .gitignore is whatever was
    # committed -- on a project that adopted the block later, that is the
    # version without it. Normalizing only the project root left every
    # worktree unconfigured, which is how one ended up tracking a previous
    # run's .uncle/workflow-history and carrying 2379 files into a PR.
    # Best effort: a project whose ignore file cannot be written still runs.
    python3 "$ROOT/scripts/lib/uncle_gitignore.py" "$abs" 2>/dev/null || true

    worktree_copy_venvs "$root" "$abs"
    return 0
}

# worktree_copy_venvs <src_root> <dst_root> — carry any already-populated
# Python virtualenv (".venv" at the project root or one level down, e.g.
# "server/.venv") into the new worktree, instead of leaving it to whatever
# tool first touches the tree there.
#
# `git worktree add` shares history, not installed dependencies: a fresh
# worktree's own ".venv" does not exist until something creates one, and
# nothing here guarantees that first thing installs the project's full
# dependency set. Observed on canopy issue #4: the implementing agent's own
# baseline picked `uv run pytest`, which is not what the project documents
# (`.venv/bin/python`, per its README and Makefile) and auto-created a second,
# base-dependencies-only venv that never got the `[dev]` extras -- so the
# agent's every subsequent test run failed with a plain `ModuleNotFoundError`,
# read as an environment defect rather than what it was: a worktree that
# never had a real environment to begin with. Copying the source project's
# own, already-verified environment sidesteps that regardless of which tool
# an agent reaches for, and is far cheaper than reinstalling a dependency set
# that can include multi-hundred-megabyte packages (torch, playwright's
# browser).
#
# A copy is not portable on its own: activation scripts, editable-install
# finders, and interpreter shebangs all embed the source's absolute path.
# Every text file under the copy has that path rewritten to the new
# worktree's, so the environment resolves as if built there directly.
worktree_copy_venvs() {
    local src="$1" dst="$2" venv rel
    while IFS= read -r -d '' venv; do
        rel="${venv#"$src"/}"
        [[ "$rel" != "$venv" ]] || continue
        echo "Copying $rel into $dst (carrying its installed dependencies)..."
        if ! cp -R "$venv" "$dst/$rel" 2>/dev/null; then
            echo "Warning: could not copy $rel into the new worktree; set it up there manually." >&2
            continue
        fi
        python3 -c "
import pathlib, sys
root = pathlib.Path(sys.argv[1])
old, new = sys.argv[2].encode(), sys.argv[3].encode()
for path in root.rglob('*'):
    if not path.is_file() or path.is_symlink():
        continue
    try:
        data = path.read_bytes()
    except OSError:
        continue
    if old not in data:
        continue
    try:
        path.write_bytes(data.replace(old, new))
    except OSError:
        pass
" "$dst/$rel" "$src" "$dst" \
            || echo "Warning: could not relocate absolute paths inside $rel; it may still point at $src." >&2
    done < <(find "$src" -maxdepth 2 -type d -name ".venv" -print0 2>/dev/null)
}

# worktree_run_locked <dir> — true while a driver holds the run in <dir>: the
# legacy lock directory exists, the driver.lock flock is held, or the process
# group it records is alive. False for a run that merely stopped mid-way.
worktree_run_locked() {
    local dir="$1"
    [[ -e "$dir/.uncle/workflow/lock" ]] && return 0
    [[ -f "$dir/.uncle/workflow/driver.lock" ]] || return 1
    python3 - "$dir/.uncle/workflow/driver.lock" <<'LOCKPROBE'
import json, os, sys
try:
    import fcntl
except ImportError:
    fcntl = None
path = sys.argv[1]
try:
    with open(path, 'a+') as lock:
        if fcntl is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                sys.exit(0)
        lock.seek(0)
        try:
            owner = json.loads(lock.read() or '{}')
        except ValueError:
            owner = {}
except OSError:
    sys.exit(1)
pgid = owner.get('pgid') if isinstance(owner, dict) else None
if pgid:
    try:
        os.killpg(int(pgid), 0)
        sys.exit(0)
    except (OSError, ValueError):
        pass
sys.exit(1)
LOCKPROBE
}

# worktree_remove <dir> — remove a finished run's worktree. Refuses while the
# driver lock exists or the state is not COMPLETE; git refuses a dirty tree.
# The branch is left in place.
worktree_remove() {
    local dir="$1" state main

    if [[ ! -d "$dir" ]] || ! worktree_registered "$dir" "$dir"; then
        echo "Not a registered git worktree: $dir" >&2
        return 1
    fi
    if [[ -e "$dir/.uncle/workflow/lock" ]]; then
        echo "Refusing to remove $dir: a run holds .uncle/workflow/lock" >&2
        return 1
    fi
    state="$(state_read "$dir/.uncle/workflow/state")"
    if [[ "$state" != "COMPLETE" ]]; then
        echo "Refusing to remove $dir: state is '${state:-absent}', not COMPLETE" >&2
        return 1
    fi
    # Run the removal from the main checkout (first line of the porcelain list)
    # so the process is not standing in the directory it deletes.
    main="$(git -C "$dir" worktree list --porcelain | head -n 1)"
    main="${main#worktree }"
    if ! git -C "$main" worktree remove "$dir"; then
        echo "git worktree remove refused $dir; worktree kept" >&2
        return 1
    fi
    echo "Removed worktree $dir (branch kept)"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        remove)
            if [[ -z "${2:-}" ]]; then
                echo "Usage: worktrees.sh remove <dir>" >&2
                exit 1
            fi
            worktree_remove "$2"
            exit $?
            ;;
        *)
            echo "Usage: worktrees.sh remove <dir>" >&2
            exit 1
            ;;
    esac
fi

# worktree_auto — put this run in its own worktree, and print where.
#
# One checkout holds one branch and one driver lock, so two pieces of work in
# one directory cannot run at the same time. Work arrives from chat, from an
# issue, from a CHANGE_REQUEST.md someone wrote by hand, and a second piece can
# arrive while the first is still running -- none of which the driver gets to
# predict. So the isolation is not a flag the operator remembers to pass; every
# run gets its own directory.
#
# Prints the worktree path on success. Prints nothing and returns 0 when a
# worktree is not wanted or not possible: no git, no brief to name one from,
# already inside a run's worktree, or WORKFLOW_WORKTREE=0. The run then
# proceeds where it is, exactly as before.
worktree_auto() {
    local root="${1:-$PWD}" branch base dir n=2

    [[ "${WORKFLOW_WORKTREE:-1}" == "1" ]] || return 0
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    # A worktree this function already made, or one the operator made: either
    # way the run is isolated and moving again would be wrong.
    [[ -f "$root/.uncle/workflow/worktree-owned" ]] && return 0
    [[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]] && return 0

    branch="$(cd "$root" && ROOT="$ROOT" bash -c \
        '. "$ROOT/scripts/lib/change-pr.sh"; change_pr_engine run-branch-name' 2>/dev/null | tail -n 1)"
    [[ -n "$branch" && "$branch" != */ ]] || return 0

    # A name already in use means a previous run for the same brief. Number it
    # rather than colliding: the operator asked for more work, not for the old
    # work to be disturbed.
    base="$branch"
    while git show-ref --verify --quiet "refs/heads/$branch" \
          || [[ -e "$(dirname "$root")/$(basename "$root")-$(basename "$branch")" ]]; do
        branch="$base-$n"
        n=$((n + 1))
        [[ "$n" -gt 64 ]] && return 0
    done
    dir="$(dirname "$root")/$(basename "$root")-$(basename "$branch")"

    worktree_create "$dir" "$branch" >&2 || return 0
    mkdir -p "$dir/.uncle/workflow" && : > "$dir/.uncle/workflow/worktree-owned"

    # `git worktree add` checks out HEAD, and the brief is usually not in HEAD:
    # chat writes it, or a person does, and nobody commits it before starting.
    # Without this the run would begin in a directory with nothing to build.
    local name
    for name in CHANGE_REQUEST.md REQUIREMENTS.md; do
        [[ -s "$root/$name" ]] || continue
        cp -p "$root/$name" "$dir/$name" || {
            echo "Could not copy $name into $dir; running in place." >&2
            rm -rf "$dir/.uncle"
            git worktree remove --force "$dir" >/dev/null 2>&1 || true
            return 0
        }
    done
    printf '%s\n' "$dir"
}
