#!/usr/bin/env bash
# AC-17: a write under .uncle/workflow/envelopes/ between the driver's snapshot
# and restore is detected, reverted byte for byte, logged, and exits 1.
# AC-16: a discarded speculative stage in stagegate.sh removes its envelope.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STATE="$TMP/.uncle/workflow"
mkdir -p "$STATE"
FAILED=0
COUNT=0

check() {
    COUNT=$((COUNT + 1))
    if [[ "$1" != "$2" ]]; then
        echo "FAIL $3: expected '$2', got '$1'"
        FAILED=$((FAILED + 1))
    fi
}

env_py() {
    python3 "$ROOT/scripts/lib/envelope.py" "$@"
}

env_py write --state "$STATE" --stage review --result pass > /dev/null || exit 1
env_py write --state "$STATE" --stage plan --result pass > /dev/null || exit 1
before_review="$(cat "$STATE/envelopes/review.json")"
before_plan="$(cat "$STATE/envelopes/plan.json")"

# Untouched: restore is silent and exits 0.
env_py snapshot --state "$STATE" || exit 1
env_py restore --state "$STATE" > "$TMP/out" 2>&1
check "$?" 0 "untouched restore exits 0"
check "$(wc -c < "$TMP/out" | tr -d ' ')" 0 "untouched restore is silent"
check "$(test -f "$STATE/envelope-tamper.log"; echo $?)" 1 "no log without a write"

# The agent rewrites one envelope, adds another, and deletes a third.
env_py snapshot --state "$STATE" || exit 1
printf '{"forged":true}' > "$STATE/envelopes/review.json"
printf '{"stage":"verification","result":"pass"}' > "$STATE/envelopes/verification.json"
rm -f "$STATE/envelopes/plan.json"
env_py restore --state "$STATE" > "$TMP/out" 2>&1
check "$?" 1 "tampered restore exits 1"
check "$(cat "$STATE/envelopes/review.json")" "$before_review" "review bytes restored"
check "$(cat "$STATE/envelopes/plan.json")" "$before_plan" "deleted envelope restored"
check "$(test -e "$STATE/envelopes/verification.json"; echo $?)" 1 "forged envelope removed"
check "$(grep -c 'Envelope write reverted: envelopes/review.json' "$TMP/out")" 1 "reports the rewritten file"
check "$(grep -c 'Envelope write reverted: envelopes/verification.json' "$TMP/out")" 1 "reports the added file"
check "$(grep -c 'Envelope write reverted: envelopes/plan.json' "$TMP/out")" 1 "reports the deleted file"
check "$(wc -l < "$STATE/envelope-tamper.log" | tr -d ' ')" 3 "three log rows"
check "$(awk -F'\t' 'NF != 4 { bad++ } END { print bad + 0 }' "$STATE/envelope-tamper.log")" 0 "log rows are time, path, before, after"
check "$(awk -F'\t' '$2 == "envelopes/review.json" { print ($3 != $4) }' "$STATE/envelope-tamper.log")" 1 "before and after hashes differ"

# The whole directory removed: exit 1 and the directory comes back.
env_py snapshot --state "$STATE" || exit 1
rm -rf "$STATE/envelopes"
env_py restore --state "$STATE" > "$TMP/out" 2>&1
check "$?" 1 "deleted directory exits 1"
check "$(test -d "$STATE/envelopes"; echo $?)" 0 "directory restored"
check "$(cat "$STATE/envelopes/review.json")" "$before_review" "contents restored with the directory"
check "$(grep -c 'envelopes/' "$STATE/envelope-tamper.log")" 6 "log appended, never truncated"

# The driver wraps each implementation agent run in the guard.
python3 - "$ROOT/scripts/change-workflow.sh" <<'PY' || FAILED=$((FAILED + 1))
import re, sys
text = open(sys.argv[1], encoding='utf-8').read()
branch = text[text.index('        IMPLEMENT)'):text.index('        WAIT_IMPLEMENT_APPROVAL)')]
runs = [m.start() for m in re.finditer(r'run_(?:claude|stepwise_implementation) ', branch)]
begins = [m.start() for m in re.finditer(r'envelope_guard_begin', branch)]
ends = [m.start() for m in re.finditer(r'envelope_guard_end', branch)]
if not (len(runs) == len(begins) == len(ends) == 3 and all(b < r < e for b, r, e in zip(begins, runs, ends))):
    print('FAIL: not every implementation agent run is wrapped by the envelope guard', runs, begins, ends)
    raise SystemExit(1)
if 'envelope_invalidate IMPLEMENT' not in branch:
    print('FAIL: IMPLEMENT entry does not invalidate downstream envelopes')
    raise SystemExit(1)
PY
COUNT=$((COUNT + 1))

# AC-16: stagegate's discarded speculation leaves no envelope behind.
python3 - "$ROOT/scripts/stagegate.sh" <<'PY' || FAILED=$((FAILED + 1))
import sys
text = open(sys.argv[1], encoding='utf-8').read()
body = text[text.index('adopt_speculation() {'):]
body = body[:body.index('\n}\n')]
discard = body.index('Discarding speculative $stage')
rm = body.index('rm -f "$STATE_DIR/envelopes/${stage}.json"')
if not discard < rm < body.index('return 1', discard) + 20:
    print('FAIL: the discarded speculative stage keeps its envelope')
    raise SystemExit(1)
PY
COUNT=$((COUNT + 1))

# The rm line, executed: a stage envelope disappears when its speculation is discarded.
mkdir -p "$TMP/spec/.uncle/workflow/envelopes"
printf '{}' > "$TMP/spec/.uncle/workflow/envelopes/review.json"
(
    STATE_DIR="$TMP/spec/.uncle/workflow"
    stage=review
    eval "$(sed -n '/Discarding speculative/,/return 1/p' "$ROOT/scripts/stagegate.sh" | grep 'rm -f "\$STATE_DIR/envelopes')"
)
check "$(test -e "$TMP/spec/.uncle/workflow/envelopes/review.json"; echo $?)" 1 "speculative envelope removed"

if [[ "$FAILED" -ne 0 ]]; then
    echo "envelope-protection-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "envelope-protection-test.sh: $COUNT checks passed"
