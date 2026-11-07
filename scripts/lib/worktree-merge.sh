#!/usr/bin/env bash
# Finish a run that happened in one of uncle's own worktrees by merging it back: commit, merge into the branch the source checkout is on,
# remove the worktree and the merged branch. Shared by the change driver (change-pr.sh, which commits the audited tree) and the
# new-application driver (stagegate.sh, which has no PR path at all and committed nothing).
#
# Callers set their own exit status from what these report; nothing here exits.

WORKTREE_MERGE_LIB_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"

# worktree_merge_owned — true in a linked worktree uncle created for this run. WORKFLOW_LOCAL_MERGE=0 opts out.
worktree_merge_owned() {
    [[ "${WORKFLOW_LOCAL_MERGE:-1}" == 1 ]] || return 1
    local gd cd d="${STATE_DIR:-.uncle/workflow}"
    gd="$(git rev-parse --absolute-git-dir 2>/dev/null)" || return 1
    cd="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
    [[ -n "$gd" && -n "$cd" ]] || return 1
    gd="$(cd "$gd" 2>/dev/null && pwd -P)" || return 1
    cd="$(cd "$cd" 2>/dev/null && pwd -P)" || return 1
    [[ "$gd" != "$cd" ]] || return 1
    [[ "$d" == /* ]] || d="$(pwd -P)/$d"
    [[ -e "$d/worktree-owned" ]]
}

# worktree_merge_commit_all <title> — commit everything the run left in the worktree (ignored files and the run's own state stay out).
# Used where there is no audited tree to commit. Returns 1, saying why, when the tree is not clean afterwards.
worktree_merge_commit_all() {
    local title="$1"
    git add -A || { echo "git add refused in $(pwd -P)" >&2; return 1; }
    git reset -q -- .uncle/workflow >/dev/null 2>&1 || true
    if ! git diff --cached --quiet; then
        git -c commit.gpgsign=false commit -q --no-gpg-sign -m "$title" || { echo "committing failed in $(pwd -P)" >&2; return 1; }
    fi
    [[ -z "$(git status --porcelain --untracked-files=all -- . ':(exclude).uncle/workflow' 2>&1)" ]] \
        || { echo "the worktree is not clean after the commit" >&2; return 1; }
}

# worktree_merge_into_source <branch> <main> — merge <branch> into the branch checked out in <main>. A merge git refuses is aborted, so
# <main> is left as it was. Prints why on failure.
worktree_merge_into_source() {
    local branch="$1" main="$2" srcbranch
    srcbranch="$(git -C "$main" branch --show-current 2>/dev/null)"
    [[ -n "$srcbranch" ]] || { echo "the source checkout $main is not on a named branch" >&2; return 1; }
    # A first build leaves the source checkout with an untracked placeholder .gitignore (uncle's own ignore entries, nothing of the
    # project's). git will not merge over an untracked file, and the run's .gitignore is the one the project should have.
    if [[ -f "$main/.gitignore" ]] \
       && [[ -z "$(git -C "$main" ls-files -- .gitignore)" ]] \
       && git -C "$main" cat-file -e "$branch:.gitignore" 2>/dev/null \
       && ! git -C "$main" cat-file -e "HEAD:.gitignore" 2>/dev/null \
       && python3 -B - "$WORKTREE_MERGE_LIB_DIR" "$main/.gitignore" <<'PY' 2>/dev/null; then
import sys
sys.path.insert(0, sys.argv[1])
from uncle_gitignore import strip_managed
sys.exit(0 if not strip_managed(open(sys.argv[2], encoding='utf-8').read()).strip() else 1)
PY
        rm -f "$main/.gitignore"
    fi
    if ! git -C "$main" -c commit.gpgsign=false merge --no-edit "$branch" >&2; then
        git -C "$main" merge --abort >/dev/null 2>&1 || true   # errors only when no merge was left in progress
        echo "merging $branch into $srcbranch in $main failed (nothing changed there)" >&2
        return 1
    fi
    echo "Merged $branch into $srcbranch in $main."
}

# worktree_merge_remove <worktree> <main> <branch> — remove the merged worktree and its branch (git refuses -d for unmerged work).
# Leaves the directory, and says how to remove it, when git refuses (e.g. files it does not ignore).
worktree_merge_remove() {
    local wt="$1" main="$2" branch="$3"
    cd "$main" 2>/dev/null || { echo "Worktree $wt kept: $main is unreachable."; return 0; }
    if git -C "$main" worktree remove "$wt" 2>/dev/null && [[ ! -e "$wt" ]]; then
        echo "Removed worktree $wt."
        git -C "$main" branch -d "$branch" >/dev/null 2>&1 && echo "Deleted merged branch $branch." || true
    else
        echo "Worktree $wt kept: git would not remove it. Everything is merged; remove it with: git -C $main worktree remove --force $wt"
    fi
    return 0
}

# worktree_merge_finish_all <title> — the new-application path: commit, merge, and record what to remove once the summary has printed.
# Sets WORKTREE_MERGE_PENDING ("worktree|main|branch") on success, WORKTREE_MERGE_FAILURE otherwise. Returns 0 on success.
worktree_merge_finish_all() {
    local title="$1" branch main why
    WORKTREE_MERGE_PENDING=""; WORKTREE_MERGE_FAILURE=""
    branch="$(git branch --show-current 2>/dev/null)"
    [[ -n "$branch" ]] || { WORKTREE_MERGE_FAILURE="the worktree has no branch (detached HEAD)"; return 1; }
    main="$(git worktree list --porcelain | head -n 1)"; main="${main#worktree }"
    if ! why="$(worktree_merge_commit_all "$title" 2>&1)"; then WORKTREE_MERGE_FAILURE="$why; branch $branch is kept"; return 1; fi
    echo "Committed the run's files on $branch."
    if ! why="$(worktree_merge_into_source "$branch" "$main" 2>&1)"; then
        WORKTREE_MERGE_FAILURE="$why; branch $branch and this worktree are kept"; return 1
    fi
    printf '%s\n' "$why"
    WORKTREE_MERGE_PENDING="$(pwd -P)|$main|$branch"
}

worktree_merge_remove_pending() {
    [[ -n "${WORKTREE_MERGE_PENDING:-}" ]] || return 0
    local wt main branch
    IFS='|' read -r wt main branch <<< "$WORKTREE_MERGE_PENDING"
    WORKTREE_MERGE_PENDING=""
    worktree_merge_remove "$wt" "$main" "$branch"
}
