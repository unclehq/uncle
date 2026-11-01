#!/usr/bin/env bash
# Only a critical failure makes repair necessary: acceptance_transition on a test review whose thoroughness rows failed.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

mk() {   # <green rows...> -> a project state with a test review failing ASSERTIONS and COVERAGE
    s="$work/s$((++n))"; mkdir -p "$s/documents" "$s/logs"
    python3 - "$s/documents/TEST_REVIEW.json" <<'PY'
import json, sys
st = {'ASSERTIONS': 'FAIL', 'COVERAGE': 'NOT RUN', 'NEGATIVE': 'FAIL'}
rows = [{'id': i, 'required': True, 'status': st.get(i, 'PASS'), 'evidence': 'e'} for i in 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'.split()]
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': rows}, open(sys.argv[1], 'w'))
PY
    : > "$s/green.tsv"
    for r in "$@"; do printf '%s\n' "$r" >> "$s/green.tsv"; done
    : > "$s/logs/green-check.log"
}
n=0
go() {   # <state dir> [env...]  -> prints the next state, REPAIR, or what the gate said
    env -i PATH="$PATH" "${@:2}" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='$1'; LOG_DIR='$1/logs'; GREEN_CLASS='$1/green.tsv'
        record_nonblocking_failure() { printf '%s\t%s\n' \"\$1\" \"\$2\" >> '$1/ledger.tsv'; }
        ensure_acceptance_canonical() { return 0; }
        supervision_validation_failed() { :; }
        set_state() { echo \"state=\$1\"; }
        . '$ROOT/scripts/lib/acceptance-gate.sh'
        acceptance_transition .uncle/docs/TEST_REVIEW.md NEXT 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'" 2>&1
}

mk 'PASS	npm ci' 'PASS	npx vitest run' 'MUTATION	node tests/mutations/run.mjs'
out="$(go "$s")"
grep -q 'state=NEXT' <<< "$out"                 || bad "no critical failure: the run should continue, got: $out"
grep -q 'Severity MAJOR: test-review row ASSERTIONS' <<< "$out" || bad "the severity was not announced"
grep -c 'TEST_REVIEW.json' "$s/ledger.tsv" | grep -qx 3 || bad "each downgraded row should be ledgered for the audit (got $(cat "$s/ledger.tsv" 2>/dev/null | wc -l))"
grep -q 'MAJOR' "$s/ledger.tsv" && grep -q 'MINOR' "$s/ledger.tsv" || bad "the ledger lacks the severities"
[[ -s "$s/failure-severity.tsv" ]]               || bad "failure-severity.tsv was not written"

mk 'PASS	npm ci' 'REGRESSION	npx vitest run'
out="$(go "$s")"
grep -q 'state=REPAIR' <<< "$out"               || bad "a failing driver command is critical: repair, got: $out"
[[ ! -s "$s/ledger.tsv" ]]                      || bad "a critical failure was downgraded"

mk 'PASS	npm ci' 'PASS	npx vite build'
echo 'Build failed: Could not resolve ./App.jsx' > "$s/logs/green-check.log"
out="$(go "$s")"
grep -q 'state=REPAIR' <<< "$out"               || bad "an unbuildable application is critical: repair, got: $out"

mk 'PASS	npm ci'
out="$(go "$s" WORKFLOW_REPAIR_SEVERITY=all)"
grep -q 'state=REPAIR' <<< "$out"               || bad "WORKFLOW_REPAIR_SEVERITY=all restores repair for every failing row, got: $out"

# only the test review is gated, and both drivers reach it through acceptance_transition
grep -q 'TEST_REVIEW.md ]] || severity_gate_test_review' "$ROOT/scripts/lib/acceptance-gate.sh" || bad "the gate is not applied to the test review"
[[ $fail == 0 ]] && echo "severity-gate-driver-test.sh: ok"
exit $fail
