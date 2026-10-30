#!/usr/bin/env bash
# implementation_complete(): a delivery criterion claimed by two different
# isolated parallel steps is a conflict between their own outputs, not a
# defect retrying either step alone can fix. An unattended run must stop for
# a person to reconcile it instead of burning the retry budget retrying the
# one step supervision happens to name -- observed live on issue 116: five
# retries of the same step left the same duplicate every time.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected [$2] got [$3]"; fi; }

block="$(sed -n '/^implementation_complete() {/,/^}/p' "$ROOT/scripts/change-workflow.sh")"
[[ -n "$block" ]] || { echo 'FATAL: could not extract implementation_complete'; exit 2; }
printf '%s\n' "$block" > "$temp/fn.sh"

STATE_DIR="$temp/project/.uncle/workflow"
mkdir -p "$STATE_DIR/documents" "$temp/project/.uncle/docs" "$temp/project/.uncle/workflow/waivers"
cd "$temp/project"
printf '{"schema":"uncle.artifact/v1","kind":"change-spec","acceptance_criteria":[{"id":"AC-3","criterion":"no Cline residue","verification":"bash scripts/tests/cline-removal-gate-test.sh"}]}' \
    > "$STATE_DIR/documents/CHANGE_SPEC.json"
printf '{"schema":"uncle.artifact/v1","kind":"implementation-notes","fragments":[{"schema":"uncle.artifact/v1","kind":"implementation-notes","deliveries":[{"id":"AC-3","status":"IMPLEMENTED","changed_code":"step2","observed_verification":"e"}]},{"schema":"uncle.artifact/v1","kind":"implementation-notes","deliveries":[{"id":"AC-3","status":"IMPLEMENTED","changed_code":"step5","observed_verification":"e"}]}]}' \
    > "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json"

verify_approval() { :; }
waive_file() { printf ''; }
supervision_validation_failed() { echo "SUPERVISION_CALLED $*" >> "$temp/calls"; }
# shellcheck disable=SC1090
source "$temp/fn.sh"

# --- unattended: a duplicate-delivery rejection stops, not retries ---------
: > "$temp/calls"
UNATTENDED=1
status=0
output="$(implementation_complete 2>&1)" || status=$?
check "unattended stops (does not return 1 for a retry)" "1" "$status"
check "the stop message names the duplicate" "yes" "$(printf '%s' "$output" | grep -q 'Duplicate delivery criterion AC-3' && echo yes || echo no)"
check "the stop message explains it is a cross-step conflict" "yes" \
    "$(printf '%s' "$output" | grep -q 'conflict between two steps' && echo yes || echo no)"
check "supervision is never invoked for this failure class" "" "$(cat "$temp/calls" 2>/dev/null)"

# --- attended: still goes through supervision as before --------------------
: > "$temp/calls"
UNATTENDED=0
status=0
implementation_complete >/dev/null 2>&1 || status=$?
check "attended runs still fall through to supervision" "1" "$status"
check "...and supervision is called" "yes" "$(grep -q 'SUPERVISION_CALLED implementation_completion' "$temp/calls" && echo yes || echo no)"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "implementation-completion-duplicate-stop-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "implementation-completion-duplicate-stop-test.sh: $PASS checks passed"
