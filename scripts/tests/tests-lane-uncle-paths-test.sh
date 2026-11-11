#!/usr/bin/env bash
# A tests lane that lists its own `.uncle/workflow/tests/lane-*.files` among its files must not make the stage fail: those are
# driver state, not tests, and `.uncle/` is never a valid protected path (a groovy-calculator build stopped at IMPLEMENT on it).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else FAILED=1; echo "FAIL $1: expected [$2] got [$3]"; fi; }

cd "$TMP" && git init -q . && mkdir -p tests .uncle/workflow/tests
STATE_DIR="$TMP/.uncle/workflow"; PLAN_DOC="$TMP/plan.md"; : > "$PLAN_DOC"
export STATE_DIR PLAN_DOC WORKFLOW_TESTS_LANES=mutation
printf 'x\n' > tests/list.mjs
printf 'tests/list.mjs\n' > "$STATE_DIR/tests.paths"
# shellcheck disable=SC1091
. "$ROOT/scripts/lib/tests-stage.sh"
tests_concurrent() { return 1; }
tests_status_snapshot() { :; }
: > "$STATE_DIR/tests/status.before"
: > "$STATE_DIR/tests/lane-harness.files"   # the harness lane always runs first; this one wrote nothing
printf 'tests/list.mjs\n.uncle/workflow/tests/lane-mutation.files\n.uncle/workflow/tests/lane-mutation.md\n' > "$STATE_DIR/tests/lane-mutation.files"
touch "$STATE_DIR/tests/lane-mutation.files" "$STATE_DIR/tests/lane-mutation.md"

out="$(tests_collate 2>&1)"; status=$?
check "collate passes when a lane lists its own bookkeeping" 0 "$status"
check "the .uncle entries are noted and ignored" 2 "$(printf '%s' "$out" | grep -c 'driver state and not a test file')"
check "no .uncle path reaches the freeze list" 0 "$(grep -c '^\.uncle/' "$STATE_DIR/tests/outside.paths" 2>/dev/null)"
check "the real test file is still tracked" 1 "$(awk -F'\t' '$2 == "tests/list.mjs"' "$STATE_DIR/tests/listed.tsv" | wc -l | tr -d ' ')"
exit "$FAILED"
