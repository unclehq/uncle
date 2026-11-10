#!/usr/bin/env bash
# tests_collate: a lockfile the driver's own dependency install wrote during test authoring is not a stray; real strays still fail.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
d="$(mktemp -d)"; trap 'rm -rf "$d"' EXIT
cd "$d" && git init -q -b main && git config user.email t@t && git config user.name t && git config commit.gpgsign false
echo x > README.md && git add -A && git commit -qm base
STATE_DIR=.uncle/workflow; LOG_DIR=$STATE_DIR/logs; PLAN_DOC=plan.md; WORKFLOW_TESTS_LANES="unit"; export WORKFLOW_TESTS_CONCURRENT=0
source "$ROOT/scripts/lib/tests-stage.sh"
mkdir -p "$STATE_DIR/tests"; : > "$STATE_DIR/tests.paths"; echo tests/ > "$STATE_DIR/tests.paths"
tests_status_snapshot > "$STATE_DIR/tests/status.before"
mkdir -p tests; echo t > tests/a.test.js; printf 'tests/a.test.js\n' > "$STATE_DIR/tests/lane-unit.files"; : > "$STATE_DIR/tests/lane-harness.files"
echo '{}' > package-lock.json                                  # written by the driver's install, claimed by no lane
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1 (got $3, want $2)"; fail=1; fi; }
tests_collate >/dev/null 2>&1; check "driver-written package-lock.json is not a stray" 0 $?
echo s > stray.js
out="$(tests_collate 2>&1)"; rc=$?
check "a real stray file still fails the check" 1 $rc
grep -q "stray.js changed during test authoring" <<< "$out"; check "the stray is named" 0 $?
exit "$fail"
