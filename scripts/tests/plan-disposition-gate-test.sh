#!/usr/bin/env bash
# AC-3: WAIT_UPDATED_PLAN_APPROVAL refuses while a blocking AR-* finding has no
# disposition row in CHANGE_PLAN.md, naming the finding; passes once every
# blocking finding is dispositioned. Exercises the gate helper the driver
# calls (scripts/lib/envelope.py plan-gate) and the driver's own branch text.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0
COUNT=0

check() {
    COUNT=$((COUNT + 1))
    if [[ "$1" != "$2" ]]; then
        echo "FAIL $3: expected '$2', got '$1'"
        FAILED=$((FAILED + 1))
    fi
}

gate() {
    python3 "$ROOT/scripts/lib/envelope.py" plan-gate "$TMP/ADVERSARIAL_REVIEW.md" "$TMP/CHANGE_PLAN.md" > "$TMP/out" 2>&1
    printf '%s' "$?"
}

cat > "$TMP/ADVERSARIAL_REVIEW.md" <<'REVIEW'
# Adversarial review

## AR-001: Subject digest is the commit tree

- Severity: High
- References: D-4
- Failure: self-reference
- Fix: exclude the attestation
- Verify: verify-test.py

## AR-002: Wording

- Severity: Low
- References: §3
- Failure: none
- Fix: reword
- Verify: read

## Overall assessment
Two findings.
REVIEW

# No disposition table at all: the blocking finding is named, the advisory one is not.
printf '# CHANGE_PLAN.md\n\nNo table.\n' > "$TMP/CHANGE_PLAN.md"
rc="$(gate)"
check "$rc" 1 "no table exits 1"
check "$(grep -c 'AR-001' "$TMP/out")" 1 "names AR-001"
check "$(grep -c 'AR-002' "$TMP/out")" 0 "does not name the advisory finding"
check "$(grep -c 'Plan gate refused' "$TMP/out")" 1 "refusal text"

# A table that dispositions only the advisory finding still refuses.
cat > "$TMP/CHANGE_PLAN.md" <<'PLAN'
# CHANGE_PLAN.md

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-002 | Rejected | wording is fine | none |
PLAN
check "$(gate)" 1 "advisory-only table exits 1"
check "$(grep -c 'AR-001' "$TMP/out")" 1 "still names AR-001"

# Every blocking finding dispositioned: the gate opens.
cat > "$TMP/CHANGE_PLAN.md" <<'PLAN'
# CHANGE_PLAN.md

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | the subject must be the artifact | D-4 |
| AR-002 | Rejected | wording is fine | none |
PLAN
check "$(gate)" 0 "dispositioned table exits 0"
check "$(wc -c < "$TMP/out" | tr -d ' ')" 0 "silent on success"

# A review with no findings never blocks; a missing review never blocks.
printf '# Review\n\n## Overall assessment\nNo findings.\n' > "$TMP/ADVERSARIAL_REVIEW.md"
printf '# plan\n' > "$TMP/CHANGE_PLAN.md"
check "$(gate)" 0 "no findings exits 0"
rm -f "$TMP/ADVERSARIAL_REVIEW.md"
check "$(gate)" 0 "missing review exits 0"

# The driver calls the gate before the approval prompt, in the state's branch.
python3 - "$ROOT/scripts/change-workflow.sh" <<'PY' || FAILED=$((FAILED + 1))
import sys
text = open(sys.argv[1], encoding='utf-8').read()
branch = text[text.index('\n        WAIT_UPDATED_PLAN_APPROVAL)\n'):]
branch = branch[:branch.index('        IMPLEMENT)')]
gate = branch.index('plan-gate ADVERSARIAL_REVIEW.md CHANGE_PLAN.md || exit 1')
prompt = branch.index('human_gate APPROVE')
if not gate < prompt:
    print('FAIL: the plan gate does not precede the approval prompt')
    raise SystemExit(1)
PY
COUNT=$((COUNT + 1))

if [[ "$FAILED" -ne 0 ]]; then
    echo "plan-disposition-gate-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "plan-disposition-gate-test.sh: $COUNT checks passed"
