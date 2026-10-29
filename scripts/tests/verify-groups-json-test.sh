#!/usr/bin/env bash
# Declared parallel verification groups are read from a canonical JSON plan's narrative (they were
# ignored for every JSON plan), and a bad declaration falls back to sequential instead of halting.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
. "$ROOT/scripts/lib/green-check.sh"

printf 'set -u\nnpm ci\nnpm run build\nnpx vitest run\nnpx playwright test\nbash mutations.sh\necho done\n' > "$TMP/commands"   # 7 lines

plan_json() {   # name groups-block-or-empty
    python3 - "$TMP/$1.json" "$2" <<'PY'
import json, sys
narrative = '# Plan\n\n## 1. Architecture\ntext\n\n'
if sys.argv[2]:
    narrative += '## Parallel verification groups\n\n```text\n%s\n```\n\n' % sys.argv[2]
narrative += '## Verification commands\n\nsee block\n'
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': narrative, 'verification_commands': 'x'}, open(sys.argv[1], 'w'))
PY
}

plan_json valid $'3 4\n5 6'
out="$(verify_parallel_groups "$TMP/valid.json" "$TMP/commands" 2>/dev/null)"; rc=$?
check "valid groups: accepted"                 test "$rc" == 0
check "valid groups: both rows are returned"   test "$out" == $'3 4\n5 6'

plan_json labelled $'Serial: 1\nConcurrent: 2, 3\nConcurrent: 4, 5\nSerial: 6\nSerial: 7'
out="$(verify_parallel_groups "$TMP/labelled.json" "$TMP/commands" 2>/dev/null)"; rc=$?
check "labelled groups: accepted"              test "$rc" == 0
check "labelled groups: normalized"            test "$out" == $'2 3\n4 5'

plan_json none ''
out="$(verify_parallel_groups "$TMP/none.json" "$TMP/commands" 2>/dev/null)"; rc=$?
check "no groups: accepted, nothing returned"  bash -c 'test "$1" == 0 && test -z "$2"' _ "$rc" "$out"

for bad in $'3\n5 6' $'4 3' $'3 5' $'1 2 99' $'3 4\n4 5' 'prose here'; do
    plan_json bad "$bad"
    out="$(verify_parallel_groups "$TMP/bad.json" "$TMP/commands" 2>"$TMP/err")"; rc=$?
    check "bad groups ($(printf '%s' "$bad" | tr '\n' '/')): the run goes on sequentially" bash -c 'test "$1" == 0 && test -z "$2"' _ "$rc" "$out"
    check "bad groups ($(printf '%s' "$bad" | tr '\n' '/')): says so"                       grep -q 'running the verification commands in order' "$TMP/err"
done

printf 'not json' > "$TMP/garbled.json"
out="$(verify_parallel_groups "$TMP/garbled.json" "$TMP/commands" 2>/dev/null)"; rc=$?
check "an unreadable plan runs sequentially"   bash -c 'test "$1" == 0 && test -z "$2"' _ "$rc" "$out"

# Markdown plans keep their strict behaviour: a bad declaration is an error to amend.
printf '## Parallel verification groups\n\n```text\n4 3\n```\n' > "$TMP/plan.md"
verify_parallel_groups "$TMP/plan.md" "$TMP/commands" > /dev/null 2>&1
check "a Markdown plan with bad groups is still rejected" test "$?" != 0
printf '## Parallel verification groups\n\n```text\n3 4\n```\n' > "$TMP/plan.md"
check "a Markdown plan with good groups is accepted"      test "$(verify_parallel_groups "$TMP/plan.md" "$TMP/commands")" == "3 4"
printf '## Parallel verification groups\n\n```text\nSerial: 1\nConcurrent: 2, 3\n```\n' > "$TMP/plan.md"
check "a Markdown plan with labelled groups is accepted"  test "$(verify_parallel_groups "$TMP/plan.md" "$TMP/commands")" == "2 3"

# The prompts ask the planner and the implementer for a fast verification.
for f in project-plan.md project-plan-investigate.md updated-plan.md updated-plan-investigate.md; do
    check "$f asks for fast verification"  grep -q 'Make verification fast' "$ROOT/prompts/$f"
    check "$f asks for concurrent injections" grep -q 'starts every mutation at once' "$ROOT/prompts/$f"
done
for f in implement.md implement-investigate.md; do
    check "$f asks for a fast injection runner" grep -q 'Write the defect-injection runner to be fast' "$ROOT/prompts/$f"
done
for f in project-plan.md project-plan-investigate.md; do
    check "$f drops the final Reconcile step"   grep -q 'Do not end with a `Reconcile` step' "$ROOT/prompts/$f"
    check "$f keeps verification-time steps independent" grep -q 'does not depend on them while it is written' "$ROOT/prompts/$f"
done

for f in project-plan.md project-plan-investigate.md; do
    check "$f limits Depends on to three steps"      grep -q '`Depends on:` lists at most three steps' "$ROOT/prompts/$f"
    check "$f names the serial tail and its cost"    grep -q 'adds its whole duration to the build' "$ROOT/prompts/$f"
done
for f in updated-plan.md updated-plan-investigate.md; do
    check "$f keeps revised steps parallel"          grep -q 'Keep the steps parallel' "$ROOT/prompts/$f"
    check "$f forbids a re-checking final step"      grep -q 'Do not add a final step that re-checks everything' "$ROOT/prompts/$f"
done

[[ "$fails" == 0 ]] && echo "verify-groups-json-test.sh: all checks passed" || exit 1
