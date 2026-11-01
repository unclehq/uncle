#!/usr/bin/env bash
# A FAIL row from an independent review must reach the implementer as a repair request, and a review that keeps failing must
# not loop the run forever: unattended it is ledgered and carried to the next stage, attended it stops for a person.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
STATE_DIR="$work/state"; mkdir -p "$STATE_DIR"
cat > "$work/TEST_REVIEW.json" <<'JSON'
{"rows":[{"id":"COVERAGE","required":true,"status":"PASS","evidence":"fine"},
         {"id":"NEGATIVE","required":true,"status":"FAIL","evidence":"no mutate-fail-restore evidence for ledger-tolerance-test.sh"}]}
JSON
eval "$(awk '/^acceptance_queue_repair\(\) \{/,/^}/' "$ROOT/scripts/lib/acceptance-gate.sh")"
set_state() { echo "$1" > "$STATE_DIR/next-state"; }
record_unattended_gate() { echo "$1" >> "$STATE_DIR/ledger"; }
triage_stop_reason() { :; }

acceptance_queue_repair "$work/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md CHECKLIST || bad "first repair was refused"
grep -q 'NEGATIVE \[FAIL\]: no mutate-fail-restore' "$STATE_DIR/acceptance-repair-request.md" || bad "the failing row is not in the request"
grep -q 'COVERAGE' "$STATE_DIR/acceptance-repair-request.md" && bad "a passing row leaked into the request"
acceptance_queue_repair "$work/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md CHECKLIST || bad "second repair was refused"

UNATTENDED=1
if acceptance_queue_repair "$work/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md CHECKLIST; then bad "an exhausted unattended repair did not move the run on"; fi
[[ "$(cat "$STATE_DIR/next-state")" == CHECKLIST ]] || bad "exhausted repair did not advance to CHECKLIST"
grep -q acceptance-repair-exhausted "$STATE_DIR/ledger" || bad "exhaustion was not ledgered"

UNATTENDED=0; printf '2\n' > "$STATE_DIR/acceptance-repair-count-TEST_REVIEW"
( acceptance_queue_repair "$work/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md CHECKLIST ) >/dev/null 2>&1 && bad "an exhausted attended repair did not stop"

grep -Eq '^\s+REPAIR\|' "$ROOT/scripts/lib/acceptance-gate.sh" && bad "a REPAIR review is treated as a supervision validation failure"
grep -q 'acceptance-repair-request.md' "$ROOT/scripts/change-workflow.sh" || bad "IMPLEMENT does not consume the repair request"
[[ $fail == 0 ]] && echo "acceptance-repair-request-test.sh: ok"
exit $fail
