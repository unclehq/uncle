#!/usr/bin/env bash
# No remote: the finished worktree is committed, merged into the source branch, and removed.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
COUNT=0; FAILED=0
check() { COUNT=$((COUNT+1)); if [[ "$2" != "$3" ]]; then FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; fi; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

setup() {  # $1 = verdict ; leaves cwd in the worktree
    rm -rf "$TMP/src" "$TMP/src-wt"
    mkdir "$TMP/src" && cd "$TMP/src" && git init -q -b main && printf '.uncle/*\n' > .gitignore
    echo old > main.c && git add -A && git commit -q -m base
    git worktree add -q -b uncle/change-it "$TMP/src-wt" && cd "$TMP/src-wt"
    mkdir -p .uncle/workflow && : > .uncle/workflow/worktree-owned && printf 'r\t%s\th\n' "$1" > .uncle/workflow/audit-verdict
    echo new > main.c && echo audit > FINAL_AUDIT.md && mkdir -p .uncle/docs && echo audit > .uncle/docs/FINAL_AUDIT.md
    TREE="$(GIT_INDEX_FILE="$TMP/idx" git add -A . 2>/dev/null; GIT_INDEX_FILE="$TMP/idx" git write-tree)"; rm -f "$TMP/idx"
    git reset -q; rm FINAL_AUDIT.md
}
run() {
    ( . "$ROOT/scripts/lib/change-pr.sh"
      CLOSE_ISSUE=0; VERDICT_FILE=.uncle/workflow/audit-verdict; ORIGIN_FILE=.uncle/workflow/origin
      change_pr_engine() { case "$1" in validate) return "${STUB_VALIDATE:-0}";; commit-tree) echo "$TREE";; esac; }
      change_pr_local_merge_applies && echo applies || echo not-applicable
      change_pr_local_merge
      echo "reason=$CHANGE_PR_EXTRAS_REASON"
      change_pr_remove_merged_worktree
    ) 2>&1
}

setup READY
OUT="$(run)"
check "applies with no remote" 1 "$(grep -c '^applies' <<<"$OUT")"
check "reason merged-local" 1 "$(grep -c '^reason=merged-local' <<<"$OUT")"
check "main has the new code" new "$(git -C "$TMP/src" show HEAD:main.c)"
check "main has the audit copy" audit "$(git -C "$TMP/src" show HEAD:FINAL_AUDIT.md)"
check "worktree removed" no "$([[ -e "$TMP/src-wt" ]] && echo yes || echo no)"
check "merged branch deleted" "" "$(git -C "$TMP/src" branch --list uncle/change-it)"
check "source checkout clean" "" "$(git -C "$TMP/src" status --porcelain)"

setup NOT_READY
OUT="$(run)"
check "not-ready: reason" 1 "$(grep -c '^reason=verdict-not-ready' <<<"$OUT")"
check "not-ready: main untouched" old "$(git -C "$TMP/src" show HEAD:main.c)"
check "not-ready: worktree kept" yes "$([[ -e "$TMP/src-wt" ]] && echo yes || echo no)"

setup READY
( cd "$TMP/src" && git checkout -q -b other && git checkout -q main && echo diverged > main.c && git commit -qam diverge )
OUT="$(run)"
check "conflict: reason" 1 "$(grep -c '^reason=local-merge-failed' <<<"$OUT")"
check "conflict: main left as it was" diverged "$(git -C "$TMP/src" show HEAD:main.c)"
check "conflict: no merge in progress" "" "$(git -C "$TMP/src" status --porcelain)"
check "conflict: worktree kept" yes "$([[ -e "$TMP/src-wt" ]] && echo yes || echo no)"

setup READY
git -C "$TMP/src" remote add origin https://example.invalid/x.git
OUT="$(run)"
check "a remote means the PR path, not a local merge" 1 "$(grep -c '^not-applicable' <<<"$OUT")"

setup READY
OUT="$(STUB_VALIDATE=1 run)"
check "audit no longer binds: nothing merged" 1 "$(grep -c '^reason=validate-failed' <<<"$OUT")"
check "audit no longer binds: main untouched" old "$(git -C "$TMP/src" show HEAD:main.c)"

# --- new-application build: nothing committed, an untracked uncle placeholder .gitignore in the source checkout ---
app_setup() {
    rm -rf "$TMP/app" "$TMP/app-wt"
    mkdir "$TMP/app" && cd "$TMP/app" && git init -q -b main && echo readme > README.md && git add -A && git commit -q -m first
    printf '.uncle\n' > .gitignore     # untracked, as an earlier uncle run left it
    git worktree add -q -b uncle/create-hello "$TMP/app-wt" && cd "$TMP/app-wt"
    mkdir -p .uncle/workflow .uncle/docs && : > .uncle/workflow/worktree-owned && echo state > .uncle/workflow/state
    printf '/hello\n.uncle\n' > .gitignore; echo 'int main(void){return 0;}' > hello.c; printf 'all:\n' > Makefile; echo bin > hello; echo doc > .uncle/docs/P.md
}
app_run() { ( . "$ROOT/scripts/lib/worktree-merge.sh"
    worktree_merge_owned && echo owned
    worktree_merge_finish_all "uncle: create hello" && echo finished || echo "failed: $WORKTREE_MERGE_FAILURE"
    worktree_merge_remove_pending ) 2>&1; }

app_setup
OUT="$(app_run)"
check "app: owned worktree detected" 1 "$(grep -c '^owned' <<<"$OUT")"
check "app: finished" 1 "$(grep -c '^finished' <<<"$OUT")"
check "app: main has the code" "$(printf 'int main(void){return 0;}')" "$(cat "$TMP/app/hello.c")"
check "app: main tracks the Makefile" Makefile "$(git -C "$TMP/app" ls-files Makefile)"
check "app: the project's .gitignore replaced the placeholder" "/hello" "$(git -C "$TMP/app" show HEAD:.gitignore | head -1)"
check "app: ignored binary not committed" "" "$(git -C "$TMP/app" ls-files hello)"
check "app: run state not committed" "" "$(git -C "$TMP/app" ls-files .uncle)"
check "app: worktree removed" no "$([[ -e "$TMP/app-wt" ]] && echo yes || echo no)"
check "app: branch deleted" "" "$(git -C "$TMP/app" branch --list uncle/create-hello)"

app_setup
echo "my own rule" > "$TMP/app/.gitignore"      # a real untracked .gitignore of the user's: must not be removed
OUT="$(app_run)"
check "app: a user's own untracked .gitignore blocks the merge" 1 "$(grep -c '^failed' <<<"$OUT")"
check "app: ...and is left alone" "my own rule" "$(cat "$TMP/app/.gitignore")"
check "app: ...and the worktree is kept" yes "$([[ -e "$TMP/app-wt" ]] && echo yes || echo no)"

# --- a published PR: the worktree goes, the branch (the PR head) stays ---
pr_setup() {
    rm -rf "$TMP/pr" "$TMP/pr-wt"
    mkdir "$TMP/pr" && cd "$TMP/pr" && git init -q -b main && echo a > main.c && printf '.uncle/*\n!.uncle/docs/\n' > .gitignore && git add -A && git commit -q -m base
    git remote add origin https://example.invalid/x.git
    git worktree add -q -b uncle/change-it "$TMP/pr-wt" && cd "$TMP/pr-wt"
    mkdir -p .uncle/workflow .uncle/docs && : > .uncle/workflow/worktree-owned
    echo b > main.c && git commit -qam change
    echo audit > .uncle/docs/FINAL_AUDIT.md        # written after the commit: untracked, not ignored
    echo audit > FINAL_AUDIT.md && git add FINAL_AUDIT.md && git commit -qm audit && rm FINAL_AUDIT.md   # the root copy the handoff commits, absent on disk
}
pr_run() { ( . "$ROOT/scripts/lib/change-pr.sh"
    CLOSE_ISSUE=1; UNATTENDED=1; ORIGIN_FILE=.uncle/workflow/origin; VERDICT_FILE=.uncle/workflow/audit-verdict
    change_pr_publish() { CHANGE_PR_EXTRAS_REASON="${STUB_REASON:-published}"; }
    change_pr_engine() { return 1; }
    change_pr_complete </dev/null >/dev/null 2>&1; echo "rc=$?"
    echo "pending=${WORKTREE_MERGE_PENDING:+yes}"
    change_pr_remove_merged_worktree ) 2>&1; }

pr_setup
OUT="$(pr_run)"
check "pr: complete returns 0" 1 "$(grep -c '^rc=0' <<<"$OUT")"
check "pr: removal queued" 1 "$(grep -c '^pending=yes' <<<"$OUT")"
check "pr: worktree removed although only run files are dirty" no "$([[ -e "$TMP/pr-wt" ]] && echo yes || echo no)"
check "pr: the PR branch is kept" uncle/change-it "$(git -C "$TMP/pr" branch --list uncle/change-it | tr -d ' *+')"

pr_setup
echo "unsaved work" > "$TMP/pr-wt/notes.txt"
OUT="$(pr_run)"
check "pr: an operator's own file keeps the worktree" yes "$([[ -e "$TMP/pr-wt" ]] && echo yes || echo no)"
check "pr: ...and says how to remove it" 1 "$(grep -c 'worktree remove --force' <<<"$OUT")"

pr_setup
OUT="$(STUB_REASON=handoff-failed pr_run)"
check "pr: nothing published, nothing queued" 1 "$(grep -c '^pending=$' <<<"$OUT")"
check "pr: nothing published, worktree kept" yes "$([[ -e "$TMP/pr-wt" ]] && echo yes || echo no)"

if [[ "$FAILED" -ne 0 ]]; then echo "local-merge-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "local-merge-test.sh: $COUNT checks passed"
