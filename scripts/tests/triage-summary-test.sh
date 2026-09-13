#!/usr/bin/env bash
set -euo pipefail

# AC-15: both drivers print every triage-actions.tsv row at COMPLETE, under a
# "Triage actions" heading, and print nothing when there is no ledger.
# Rows of every outcome are in the fixture (AR-015): an action that wrote
# nothing, or failed to, is still an action the operator selected.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# No stage may reach a real runner from a test: every stage command is a stub that fails.
export UNCLE_CONFIG=/dev/null WORKFLOW_AGENT_CMD=/usr/bin/false WORKFLOW_REVIEWER_CMD=/usr/bin/false WORKFLOW_CODEX_CMD=/usr/bin/false
unset UNCLE_STATUS_STAGE UNCLE_DRIVER_SUPERVISED UNCLE_PROJECT_ROOT 2>/dev/null || true

FAILED=0
COUNT=0
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
check_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    grep -qF -- "$needle" "$file" || fail "$name — expected to find: $needle"
}
check_not_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if grep -qF -- "$needle" "$file"; then fail "$name — did not expect: $needle"; fi
}
check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    [[ "$actual" == "$expected" ]] || fail "$name — expected '$expected', got '$actual'"
}

TSV_FIXTURE="$(printf 'ts\tturn\tproposal\toutcome\tpath\tbefore\tafter\n2026-01-01T00:00:00Z\t1\tProposal 1: fix\tAPPLIED\tsrc/x\taaaa\tbbbb\n2026-01-01T00:00:01Z\t1\tProposal 1: fix\tREFUSED\t.uncle/workflow/approvals/CHANGE_PLAN.sha256\tcccc\tdddd\n2026-01-01T00:00:02Z\t2\tProposal 2: retry\tNO_EDIT\t-\t-\t-\n2026-01-01T00:00:03Z\t3\tProposal 1: fix\tFAILED\tsrc/y\teeee\tffff\n')"

complete_run() {  # complete_run <driver> <dir> [with-tsv]
    local driver="$1" dir="$2" with="${3:-}"
    rm -rf "$dir"
    mkdir -p "$dir/.uncle/workflow"
    printf 'COMPLETE\n' > "$dir/.uncle/workflow/state"
    printf '# audit\n' > "$dir/FINAL_AUDIT.md"
    if [[ -n "$with" ]]; then
        printf '%s\n' "$TSV_FIXTURE" > "$dir/.uncle/workflow/triage-actions.tsv"
    fi
    (cd "$dir" && UNCLE_PROJECT_ROOT="$dir" bash "$ROOT/scripts/$driver" < /dev/null > "$dir/out.txt" 2>&1) || true
}

for driver in change-workflow.sh stagegate.sh; do
    complete_run "$driver" "$TMP/with" yes
    out="$TMP/with/out.txt"
    check_contains "$driver: complete banner" "complete" "$out"
    check_contains "$driver: heading" "Triage actions (.uncle/workflow/triage-actions.tsv):" "$out"
    check_contains "$driver: header row" "ts	turn	proposal	outcome	path	before	after" "$out"
    check_contains "$driver: APPLIED row" "1	Proposal 1: fix	APPLIED	src/x	aaaa	bbbb" "$out"
    check_contains "$driver: REFUSED row" "REFUSED	.uncle/workflow/approvals/CHANGE_PLAN.sha256	cccc	dddd" "$out"
    check_contains "$driver: NO_EDIT row" "2	Proposal 2: retry	NO_EDIT	-	-	-" "$out"
    check_contains "$driver: FAILED row" "3	Proposal 1: fix	FAILED	src/y	eeee	ffff" "$out"
    check_eq "$driver: every row printed" 5 "$(sed -n '/^Triage actions/,$p' "$out" | grep -c $'^  .*\t' || true)"

    complete_run "$driver" "$TMP/without"
    out="$TMP/without/out.txt"
    check_contains "$driver: complete banner without ledger" "complete" "$out"
    check_not_contains "$driver: no heading without ledger" "Triage actions" "$out"
done

if [[ "$FAILED" -ne 0 ]]; then
    echo "triage-summary-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "triage-summary-test.sh: $COUNT checks passed"
