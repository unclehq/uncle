#!/usr/bin/env bash
# After a PR the source checkout must not keep an untracked placeholder .gitignore of uncle's own (it dirties the checkout and blocks
# pulling the merged .gitignore); a .gitignore holding anything of the project's, or a tracked one, is never touched.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
COUNT=0; FAILED=0
check() { COUNT=$((COUNT+1)); if [[ "$2" != "$3" ]]; then FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; fi; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

setup() {  # $1 = placeholder content for the source checkout's untracked .gitignore ("" = none)
    rm -rf "$TMP/src" "$TMP/src-wt"
    mkdir "$TMP/src" && cd "$TMP/src" && git init -q -b main && echo r > README.md && git add -A && git commit -q -m first
    [[ -z "$1" ]] || printf '%s' "$1" > .gitignore
    git worktree add -q -b uncle/change-x "$TMP/src-wt" && cd "$TMP/src-wt"
    printf '.uncle/*\n!.uncle/docs/\n' > .gitignore && echo c > c.txt && git add -A && git commit -q -m run
}
drop() { ( . "$ROOT/scripts/lib/worktree-merge.sh"; worktree_merge_drop_placeholder_gitignore uncle/change-x "$TMP/src" ); }
exists() { [[ -e "$TMP/src/.gitignore" ]] && echo yes || echo no; }

setup '.uncle
'
drop; check "a bare .uncle placeholder is removed" no "$(exists)"
check "source checkout is clean afterwards" "" "$(git -C "$TMP/src" status --porcelain)"

setup '.uncle/*
!.uncle/docs/
'
drop; check "the canonical block alone is a placeholder" no "$(exists)"

setup $'.uncle\nnode_modules/\n'
drop; check "a project rule keeps the file" yes "$(exists)"

setup ''
drop; check "no .gitignore: nothing to do" no "$(exists)"

setup '.uncle
'
git -C "$TMP/src" add -f .gitignore && git -C "$TMP/src" commit -q -m track
drop; check "a tracked .gitignore is kept" yes "$(exists)"

echo "$((COUNT-FAILED))/$COUNT passed"; [[ "$FAILED" == 0 ]]
