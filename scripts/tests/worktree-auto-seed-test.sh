#!/usr/bin/env bash
set -uo pipefail
# worktree_auto moves a run into its own git worktree, and the brief has to go with it. `uncle --change-request` (and the chat) write
# the brief to .uncle/docs/CHANGE_REQUEST.md as soon as that folder exists, which it does for any project uncle has built before; a
# person writes it at the root. Only the root was carried over, so a change request on a project uncle had already built started in a
# worktree with no request and the driver stopped at once with "Required file missing or empty: .uncle/docs/CHANGE_REQUEST.md"
# (found building a calculator, then changing its background). The real function runs, in a scratch repository.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

G() { git -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false -c tag.gpgsign=false "$@"; }
new_project() {   # name -> $PROJ, a repository with one commit whose .uncle is ignored
    PROJ="$TMP/$1"
    mkdir -p "$PROJ/src" && cd "$PROJ" || exit 1
    G init -q -b main . && printf '.uncle\nnode_modules\n' > .gitignore && printf 'export const a = 1;\n' > src/a.js
    G add -A && G commit -q --no-gpg-sign -m base
    cd "$REPO" || exit 1
}
auto() {   # prints what worktree_auto printed (the new directory, or nothing)
    ( cd "$PROJ" && env -u UNCLE_PROJECT_ROOT -u UNCLE_PROJECT_ROOT_LOCKED ROOT="$REPO" "$@" \
        bash -c '. "$ROOT/scripts/lib/worktrees.sh"; worktree_auto "$PWD"' 2> "$TMP/err" )
}

# 1. The case that failed: the request is under .uncle/docs/ (as `uncle --change-request` writes it), not at the root.
new_project docs-only
mkdir -p "$PROJ/.uncle/docs" && printf '# Change request\n\nChange the background to mustard and chocolate.\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
WT="$(auto)"
check "a worktree was made" test -d "$WT"
check "it is one of the project's git worktrees" bash -c 'git -C "$1" worktree list --porcelain | grep -qF "$(basename "$2")"' _ "$PROJ" "$WT"
check "the request is in the worktree under .uncle/docs/" test -s "$WT/.uncle/docs/CHANGE_REQUEST.md"
check "and it is the same text" test "$(cat "$WT/.uncle/docs/CHANGE_REQUEST.md")" == "$(printf '# Change request\n\nChange the background to mustard and chocolate.\n')"
check "the worktree is marked as owned" test -e "$WT/.uncle/workflow/worktree-owned"
check "the request was moved: the source project no longer holds it" test ! -e "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
check "the project's files are in the worktree" test -s "$WT/src/a.js"
check "nothing was copied to the worktree root" test ! -e "$WT/CHANGE_REQUEST.md"

# 2. A brief at the root, as a person writes it: carried to the root, as before.
new_project root-only
printf '# Change request\n\nAdd a widget.\n' > "$PROJ/CHANGE_REQUEST.md"
WT="$(auto)"
check "root brief: a worktree was made" test -d "$WT"
check "root brief: moved to the worktree root" test "$(cat "$WT/CHANGE_REQUEST.md")" == "$(printf '# Change request\n\nAdd a widget.\n')"
check "root brief: gone from the source project" test ! -e "$PROJ/CHANGE_REQUEST.md"
check "root brief: nothing invented under .uncle/docs/" test ! -e "$WT/.uncle/docs/CHANGE_REQUEST.md"

# 3. Requirements are carried from either place too.
new_project requirements-docs
mkdir -p "$PROJ/.uncle/docs" && printf 'Build a calendar.\n' > "$PROJ/.uncle/docs/REQUIREMENTS.md"
WT="$(auto)"
check "requirements under .uncle/docs/: a worktree was made" test -d "$WT"
check "requirements under .uncle/docs/: carried to the same path" test "$(cat "$WT/.uncle/docs/REQUIREMENTS.md")" == "Build a calendar."
check "requirements under .uncle/docs/: gone from the source project" test ! -e "$PROJ/.uncle/docs/REQUIREMENTS.md"

new_project requirements-root
printf 'Build a calendar.\n' > "$PROJ/REQUIREMENTS.md"
WT="$(auto)"
check "requirements at the root: carried to the root" test "$(cat "$WT/REQUIREMENTS.md")" == "Build a calendar."

# 4. Both places at once, and both files: each goes to its own path.
new_project everything
mkdir -p "$PROJ/.uncle/docs"
printf 'root request\n' > "$PROJ/CHANGE_REQUEST.md"
printf 'docs request\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
printf 'docs requirements\n' > "$PROJ/.uncle/docs/REQUIREMENTS.md"
WT="$(auto)"
check "both: root copy at the root" test "$(cat "$WT/CHANGE_REQUEST.md")" == "root request"
check "both: docs copy under .uncle/docs/" test "$(cat "$WT/.uncle/docs/CHANGE_REQUEST.md")" == "docs request"
check "both: requirements under .uncle/docs/" test "$(cat "$WT/.uncle/docs/REQUIREMENTS.md")" == "docs requirements"

# 4b. An earlier run's merge committed the request: the new one overwrote a tracked file in the source project. Moving it must put the
# source back to HEAD, or the run's own merge later refuses ("local changes ... would be overwritten").
new_project tracked-request
mkdir -p "$PROJ/.uncle/docs" && printf 'old request\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
( cd "$PROJ" && G add -f .uncle/docs/CHANGE_REQUEST.md && G commit -q --no-gpg-sign -m "earlier request" )
printf 'new request\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
WT="$(auto)"
check "tracked request: the worktree has the new text" test "$(cat "$WT/.uncle/docs/CHANGE_REQUEST.md")" == "new request"
check "tracked request: the source file is back to HEAD" test "$(cat "$PROJ/.uncle/docs/CHANGE_REQUEST.md")" == "old request"
check "tracked request: the source checkout is clean" test -z "$(git -C "$PROJ" status --porcelain)"

# 5. An empty file is not a brief, and is not copied.
new_project empty
mkdir -p "$PROJ/.uncle/docs" && : > "$PROJ/.uncle/docs/CHANGE_REQUEST.md" && printf 'real brief\n' > "$PROJ/CHANGE_REQUEST.md"
WT="$(auto)"
check "empty docs file: not copied" test ! -e "$WT/.uncle/docs/CHANGE_REQUEST.md"
check "empty docs file: the root brief still is" test -s "$WT/CHANGE_REQUEST.md"

# 6. No worktree wanted: nothing is made or printed.
new_project switched-off
mkdir -p "$PROJ/.uncle/docs" && printf 'a brief\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
WT="$(auto WORKFLOW_WORKTREE=0)"
check "WORKFLOW_WORKTREE=0: nothing printed" test -z "$WT"
check "WORKFLOW_WORKTREE=0: no worktree" test "$(git -C "$PROJ" worktree list | wc -l | tr -d ' ')" == 1

# 7. A run already inside its own worktree stays where it is.
new_project already-owned
mkdir -p "$PROJ/.uncle/docs" "$PROJ/.uncle/workflow" && printf 'a brief\n' > "$PROJ/.uncle/docs/CHANGE_REQUEST.md" && : > "$PROJ/.uncle/workflow/worktree-owned"
WT="$(auto)"
check "already owned: nothing printed" test -z "$WT"

if [[ "$fails" -ne 0 ]]; then echo "worktree-auto-seed-test.sh: $fails failed"; exit 1; fi
echo "worktree-auto-seed-test.sh: all checks passed"
