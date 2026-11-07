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
    echo new > main.c && echo audit > FINAL_AUDIT.md
    TREE="$(GIT_INDEX_FILE="$TMP/idx" git add -A -f . 2>/dev/null; GIT_INDEX_FILE="$TMP/idx" git write-tree)"; rm -f "$TMP/idx"
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

if [[ "$FAILED" -ne 0 ]]; then echo "local-merge-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "local-merge-test.sh: $COUNT checks passed"
