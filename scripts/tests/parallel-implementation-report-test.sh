#!/usr/bin/env bash
set -euo pipefail

# run_parallel_implementation_report's two marker checks used `-s`
# (nonempty) against files that are always created with bare `touch`
# (always 0 bytes). -s was therefore always false: the function returned 1
# on every call, on every real run, and the canonical
# IMPLEMENTATION_NOTES.md/AUTOMATED_TEST_REPORT.md reconciliation it exists
# for never actually happened. The failure surfaced far downstream and
# unrelated-looking: a later `require_artifact AUTOMATED_TEST_REPORT.md`
# failing because the file was never written.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT

# Extract the function body verbatim from the real driver, so this test
# fails the moment anyone reintroduces -s (or anything else) here, instead
# of testing a hand-copied stand-in that could quietly drift from it.
FUNCTION="$(awk '/^run_parallel_implementation_report\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
[[ -n "$FUNCTION" ]] || { echo "FAIL: could not extract run_parallel_implementation_report from stagegate.sh" >&2; exit 1; }

RUN_CLAUDE_CALLS=0
run_claude() { RUN_CLAUDE_CALLS=$((RUN_CLAUDE_CALLS + 1)); echo notes > IMPLEMENTATION_NOTES.md; echo report > AUTOMATED_TEST_REPORT.md; }
require_artifact() { [[ -s "$1" ]] || { echo "missing artifact: $1" >&2; return 1; }; }
eval "$FUNCTION"

WORK="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR" "$WORK"' EXIT
cd "$WORK"

FAILED=0
fail() { echo "FAIL: $1" >&2; FAILED=1; }

# No completion marker at all: the fan-out itself never finished. Must not
# call run_claude, and must report a failure so the caller does not silently
# treat unmerged work as reconciled.
if run_parallel_implementation_report; then
    fail "no completion marker: expected nonzero return"
fi
[[ "$RUN_CLAUDE_CALLS" == 0 ]] || fail "no completion marker: run_claude must not be called"

# The real marker: a bare touch, 0 bytes -- exactly what the driver writes.
: > "$STATE_DIR/parallel-implementation-complete"
if ! run_parallel_implementation_report; then
    fail "0-byte completion marker: expected success (this is the bug: -s treated this as absent)"
fi
[[ "$RUN_CLAUDE_CALLS" == 1 ]] || fail "0-byte completion marker: run_claude must be called exactly once, got $RUN_CLAUDE_CALLS"
[[ -e "$STATE_DIR/parallel-implementation-report-complete" ]] || fail "report-complete marker was not written"
[[ -s IMPLEMENTATION_NOTES.md ]] || fail "IMPLEMENTATION_NOTES.md was not produced"
[[ -s AUTOMATED_TEST_REPORT.md ]] || fail "AUTOMATED_TEST_REPORT.md was not produced"

# Calling it again (a resume) must recognize the 0-byte report marker as
# "already done" and skip re-invoking the reviewer entirely.
OUT="$(run_parallel_implementation_report)"
[[ "$RUN_CLAUDE_CALLS" == 1 ]] || fail "already-reconciled resume: run_claude must not be called again, got $RUN_CLAUDE_CALLS calls total"
grep -q 'already reconciled' <<< "$OUT" || fail "already-reconciled resume: expected the skip message"

if [[ "$FAILED" -ne 0 ]]; then
    exit 1
fi
echo "parallel-implementation-report-test.sh: marker existence (not size) gates the reconciliation pass"
