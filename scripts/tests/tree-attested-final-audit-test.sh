#!/usr/bin/env bash
# assert_tree_matches_attested accepts a tracked .uncle/docs/FINAL_AUDIT.md that the attested tree does not contain
# (the audit is judged by the bound tree, never part of it), and still refuses other differences.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/lib/change-pr.sh"
d="$(mktemp -d)"; trap 'rm -rf "$d"' EXIT
cd "$d" && git init -q -b main && git config user.email t@t && git config user.name t && git config commit.gpgsign false
mkdir -p .uncle/docs && echo old > .uncle/docs/FINAL_AUDIT.md && echo a > code.txt
git add -A && git commit -qm base
echo new > .uncle/docs/FINAL_AUDIT.md                        # this run's audit, written after the tree is bound
export GIT_INDEX_FILE="$d/.git/tmp-index"; git read-tree HEAD; git rm -q --cached .uncle/docs/FINAL_AUDIT.md
tree="$(git write-tree)"; unset GIT_INDEX_FILE              # the attested tree: no .uncle/docs/FINAL_AUDIT.md
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1 (got $3, want $2)"; fail=1; fi; }
assert_tree_matches_attested "$tree" pre >/dev/null 2>&1; check "tracked FINAL_AUDIT.md absent from the attested tree is accepted" 0 $?
echo changed > code.txt; git add code.txt
assert_tree_matches_attested "$tree" pre >/dev/null 2>&1; check "another changed path is still refused" 1 $?
exit "$fail"
