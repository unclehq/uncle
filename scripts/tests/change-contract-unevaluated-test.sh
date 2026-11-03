#!/usr/bin/env bash
set -uo pipefail
# A change request whose implementation notes carry no acceptance delivery rows (the worker wrote no handoff, so the only fragment is the
# driver's own record of a scope deviation) looped forever: change_implementation_incomplete_choice says "the acceptance contract cannot be
# evaluated ... planning is not run again, the run continues" and returns 2, but the guard at the top of the driver's loop
# (implementation_complete) rejects the same notes on the next pass and sends WAIT_IMPLEMENT_APPROVAL back to IMPLEMENT, which continues, which
# the guard sends back ... about twice a second with no model call, 57 ledger entries in 38 seconds (found changing a calculator's background).
# The decision to continue is now recorded against the notes it was made for, and the guard honours it. The real functions run.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

ROOT="$REPO"; STATE_DIR="$TMP/state"; UNATTENDED=0
mkdir -p "$STATE_DIR/documents" "$STATE_DIR/waivers"
hash_file() { shasum -a 256 "$1" | cut -d' ' -f1; }
verify_approval() { :; }
supervision_validation_failed() { echo "$1" >> "$STATE_DIR/supervision-calls"; }
waive_file() { printf '%s/waivers/%s' "$STATE_DIR" "$1"; }
record_unattended_gate() { printf '%s\t%s\n' "$1" "$2" >> "$STATE_DIR/ledger"; }
gate_prompt() { :; }
ANSWER=""
gate_read() { printf -v "$1" '%s' "$ANSWER"; }
eval "$(awk '$0 == "implementation_complete() {" {p=1} p{print} p&&/^}$/{exit}' "$REPO/scripts/change-workflow.sh")"
. "$REPO/scripts/lib/implementation-gates.sh"

write_spec() {
    python3 - "$STATE_DIR/documents/CHANGE_SPEC.json" <<'PY'
import json, sys
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'change-spec', 'narrative': 'x', 'acceptance_criteria': [
    {'id': 'AC-1', 'criterion': 'the background is mustard and chocolate', 'verification': 'T-11'},
    {'id': 'AC-2', 'criterion': 'the rest is unchanged', 'verification': 'npm test'}]}, open(sys.argv[1], 'w'))
PY
}
write_notes() {   # [deliveries-json]  -- the one fragment the driver itself recorded, plus any deliveries given
    python3 - "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" "${1:-[]}" <<'PY'
import json, sys
fragment = {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'changed_files': [], 'unresolved_concerns': [],
            'deviations': [{'file': '.gitignore', 'reason': 'recorded by the driver'}], 'deliveries': json.loads(sys.argv[2]),
            '_label': 'Driver-recorded scope deviations'}
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'fragments': [fragment]}, open(sys.argv[1], 'w'))
PY
}
supervision_calls() { [[ -f "$STATE_DIR/supervision-calls" ]] && wc -l < "$STATE_DIR/supervision-calls" | tr -d ' ' || echo 0; }
# The driver reaches the choice only after implementation_complete has written implementation-completion.txt, so a fresh situation is made
# the same way: run the check once (it records why the notes were rejected), then clear everything it and the choice leave behind.
reset() {
    rm -f "$STATE_DIR/supervision-calls" "$STATE_DIR/ledger" "$STATE_DIR/implementation-contract-unevaluated" "$STATE_DIR/implementation-completion.txt"
    implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1 || true
    rm -f "$STATE_DIR/supervision-calls" "$STATE_DIR/ledger" "$STATE_DIR/implementation-contract-unevaluated"
}

# 1. The situation: notes with no acceptance rows. The guard rejects them, and with no decision on record it asks supervision.
write_spec; write_notes '[]'; reset
implementation_complete WAIT_IMPLEMENT_APPROVAL > "$TMP/out" 2>&1; rc=$?
check "no decision recorded: the notes are rejected" test "$rc" == 1
check "the reason is that no rows could be read" grep -q "no acceptance delivery rows" "$STATE_DIR/implementation-completion.txt"
check "supervision was asked once" test "$(supervision_calls)" == 1

# 2. Unattended, the choice continues and records it; the guard now lets the run through, without asking supervision again.
reset; UNATTENDED=1
change_implementation_incomplete_choice > "$TMP/out" 2>&1; rc=$?
check "unattended: the choice continues (2)" test "$rc" == 2
check "unattended: it says planning is not run again" grep -q "Planning is not run again" "$TMP/out"
check "unattended: the ledger records the continuation" grep -q "continued: the acceptance contract could not be evaluated" "$STATE_DIR/ledger"
check "unattended: the decision is recorded against these notes" test "$(cat "$STATE_DIR/implementation-contract-unevaluated")" == "$(hash_file "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json")"
implementation_complete WAIT_IMPLEMENT_APPROVAL > "$TMP/out" 2>&1; rc=$?
check "the guard honours it: the run may go on" test "$rc" == 0
check "and says so" grep -q "acceptance contract unevaluated, as recorded" "$TMP/out"
check "supervision was not asked about the same notes again" test "$(supervision_calls)" == 0
for state in WAIT_IMPLEMENT_APPROVAL MANUAL_CHECKLIST EXECUTE_CHECKLIST FINAL_AUDIT VALIDATE_AUDIT; do
    check "the guard lets $state through" implementation_complete "$state" > /dev/null 2>&1
done

# 3. The loop itself: the driver's guard, then the IMPLEMENT handler, round and round. It must end on the first pass.
reset; UNATTENDED=1
passes=0
while (( passes < 6 )); do
    passes=$((passes + 1))
    implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1 && break      # the guard at the top of the loop: through
    change_implementation_incomplete_choice > /dev/null 2>&1                        # IMPLEMENT: continue, and (now) record it
done
check "the run is through the guard within two passes, not looping" test "$passes" -le 2
reset; UNATTENDED=1
implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1 && echo through > "$TMP/through" || rm -f "$TMP/through"
check "with nothing recorded the guard still rejects (the old behaviour for a fresh implementation)" test ! -e "$TMP/through"

# 4. Attended: continue is recorded too, stop is not.
reset; UNATTENDED=0; ANSWER=stop
change_implementation_incomplete_choice > /dev/null 2>&1; rc=$?
check "attended stop: returns 1" test "$rc" == 1
check "attended stop: nothing recorded" test ! -e "$STATE_DIR/implementation-contract-unevaluated"
implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1; rc=$?
check "attended stop: the guard still rejects" test "$rc" == 1
reset; ANSWER=continue
change_implementation_incomplete_choice > /dev/null 2>&1; rc=$?
check "attended continue: returns 2" test "$rc" == 2
check "attended continue: recorded" test -s "$STATE_DIR/implementation-contract-unevaluated"
implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1; rc=$?
check "attended continue: the guard lets it through" test "$rc" == 0
reset; ANSWER=""
change_implementation_incomplete_choice > /dev/null 2>&1; rc=$?
check "attended no answer: stays pending" test "$rc" == 1
check "attended no answer: nothing recorded" test ! -e "$STATE_DIR/implementation-contract-unevaluated"
UNATTENDED=0

# 5. The decision is for those notes only: change them and they are judged afresh.
reset; UNATTENDED=1
change_implementation_incomplete_choice > /dev/null 2>&1
write_notes '[]'; python3 - "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d['fragments'][0]['deviations'].append({'file': 'src/x.js', 'reason': 'a different handoff'}); json.dump(d, open(p, 'w'))
PY
implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1; rc=$?
check "changed notes: the old decision no longer applies" test "$rc" == 1

# 6. It excuses a contract that cannot be read, never a row the notes reject.
reset; UNATTENDED=1
write_notes '[{"id":"AC-1","status":"INCOMPLETE","changed_code":"","observed_verification":"not done"}]'
reset
printf '%s' "$(hash_file "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json")" > "$STATE_DIR/implementation-contract-unevaluated"
implementation_complete WAIT_IMPLEMENT_APPROVAL > "$TMP/out" 2>&1; rc=$?
check "a rejected row is not excused by a stale record" test "$rc" == 1
check "the rejected row is what is reported" grep -q "^AC-1: requires IMPLEMENTED" "$STATE_DIR/implementation-completion.txt"
write_notes '[{"id":"AC-1","status":"IMPLEMENTED","changed_code":"src/theme.css","observed_verification":"T-11 passes"},{"id":"AC-2","status":"IMPLEMENTED","changed_code":"none","observed_verification":"npm test"}]'
reset
implementation_complete WAIT_IMPLEMENT_APPROVAL > /dev/null 2>&1; rc=$?
check "complete notes pass on their own, with no record" test "$rc" == 0
check "and no supervision was needed" test "$(supervision_calls)" == 0
UNATTENDED=0

# 7. The record is in the right places in the code.
check "the guard checks the record before it asks supervision" bash -c 'f="$1/scripts/change-workflow.sh"; a=$(grep -n "implementation-contract-unevaluated" "$f" | head -1 | cut -d: -f1); b=$(grep -n "supervision_validation_failed implementation_completion" "$f" | head -1 | cut -d: -f1); [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]]' _ "$REPO"
check "the choice records it on both ways to continue" bash -c '[[ "$(grep -c "change_record_contract_unevaluated" "$1/scripts/lib/implementation-gates.sh")" == 3 ]]' _ "$REPO"

if [[ "$fails" -ne 0 ]]; then echo "change-contract-unevaluated-test.sh: $fails failed"; exit 1; fi
echo "change-contract-unevaluated-test.sh: all checks passed"
