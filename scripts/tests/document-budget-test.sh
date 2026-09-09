#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
printf 'abc\ndef' > PROJECT_PLAN.md
WORKFLOW_DOC_MAX_BYTES=7 WORKFLOW_DOC_MAX_LINES=2 check_document_budget PROJECT_PLAN.md
if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=6 check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_LINES=1 check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
[[ $(cat PROJECT_PLAN.md) == $'abc\ndef' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
for value in 0 invalid -1 1:2; do
    if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES="$value" check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
done
printf 'é' > ADVERSARIAL_REVIEW.md
if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=1 check_document_budget ADVERSARIAL_REVIEW.md 2>/dev/null; then exit 1; fi
WORKFLOW_DOC_MAX_BYTES=2 check_document_budget ADVERSARIAL_REVIEW.md
printf 'mandatory acceptance evidence' > VERIFICATION_REPORT.md
if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=1 check_document_budget VERIFICATION_REPORT.md 2>/dev/null; then exit 1; fi
[[ $(cat VERIFICATION_REPORT.md) == "mandatory acceptance evidence" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
LOG_DIR="$tmp"
printf 'stage instructions' > prompt.md
WORKFLOW_DOC_MAX_BYTES=12345 gated_prompt prompt.md updated-plan > resolved
grep -q '12345 UTF-8 bytes' "$(cat resolved)"
# Every artifact gets three times its source brief. An interpretation squeezed to
# the brief's own length is what sent the requirements agent into repeated
# self-trimming instead of finishing, so 2x is the rule for all of them.
# Interpretation budgets follow source size, with a floor and ceiling, and
# agree between the generated prompt and the post-agent guard.
printf 'brief' > REQUIREMENTS.md
[[ $(requirements_document_max_bytes) == 4000 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
python3 - <<'PY'
from pathlib import Path
Path('REQUIREMENTS.md').write_bytes(b'x' * 5478)
Path('REQUIREMENTS_INTERPRETATION.md').write_bytes(b'x' * 16435)
PY
[[ $(requirements_document_max_bytes) == 16434 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
gated_prompt prompt.md requirements > resolved
grep -q '16434 UTF-8 bytes' "$(cat resolved)"
if grep -q 'Target 12,000' "$(cat resolved)"; then exit 1; fi
if WORKFLOW_DOC_BUDGET_ENFORCE=1 check_document_budget REQUIREMENTS_INTERPRETATION.md 2>/dev/null; then exit 1; fi
# By default the same overflow is a remark, not a stop: the number is a
# target the prompt gives the agent, and a document already written is
# worth more than its length is worth enforcing.
check_document_budget REQUIREMENTS_INTERPRETATION.md 2>/dev/null \
    || { echo "FAIL $0:$LINENO advisory budget must not stop the run" >&2; exit 1; }
[[ -s REQUIREMENTS_INTERPRETATION.md ]] \
    || { echo "FAIL $0:$LINENO the oversized document must be preserved" >&2; exit 1; }
WORKFLOW_DOC_MAX_BYTES=16435 check_document_budget REQUIREMENTS_INTERPRETATION.md
WORKFLOW_DOC_MAX_BYTES=6000 gated_prompt prompt.md requirements > resolved
grep -q '6000 UTF-8 bytes' "$(cat resolved)"
python3 - <<'PY'
from pathlib import Path
Path('REQUIREMENTS.md').write_bytes(b'x' * 25000)
PY
[[ $(requirements_document_max_bytes) == 40000 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Every document stage (including step handoffs and background checklists)
# advertises exactly the limits enforced for each named artifact.
for stage in $DOC_STAGES implementation-step-2; do
    gated_prompt prompt.md "$stage" > resolved
    [[ -n $(stage_documents "$stage") ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    while IFS= read -r file; do
        read -r bytes lines <<< "$(document_budget "$file")"
        grep -qF -- "$file: at most $bytes UTF-8 bytes and $lines lines." "$(cat resolved)"
        printf 'abc\ndef' > "$file"
        WORKFLOW_DOC_MAX_BYTES=7 WORKFLOW_DOC_MAX_LINES=2 check_document_budget "$file"
        if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=6 check_document_budget "$file" 2>/dev/null; then exit 1; fi
        if WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_LINES=1 check_document_budget "$file" 2>/dev/null; then exit 1; fi
        [[ $(cat "$file") == $'abc\ndef' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    done < <(stage_documents "$stage")
done
[[ $(document_budget PROJECT_PLAN.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(document_budget IMPLEMENTATION_NOTES.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(document_budget FINAL_AUDIT.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(document_budget VERIFICATION_REPORT.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf 'small change' > CHANGE_REQUEST.md
[[ $(document_budget CHANGE_SPEC.md) == '4000 120' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Shared artifacts use workflow context when both authoritative inputs exist.
[[ $(DOCUMENT_BUDGET_SOURCE=CHANGE_REQUEST.md document_budget FINAL_AUDIT.md) == '4000 120' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(DOCUMENT_BUDGET_SOURCE=REQUIREMENTS.md document_budget FINAL_AUDIT.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(DOCUMENT_BUDGET_SOURCE=REQUIREMENTS.md document_budget CHANGE_PLAN.md) == '4000 120' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(DOCUMENT_BUDGET_SOURCE=CHANGE_REQUEST.md document_budget PROJECT_PLAN.md) == '40000 1000' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Every artifact has bounded, monotonic defaults; generated output has no effect.
for stage in $DOC_STAGES implementation-step-2; do
    while IFS= read -r file; do
        read -r floor cap mult lf lc <<< "$(document_budget_defaults "$file")"
        source=$(document_budget_source "$file")
        rm -f "$source"
        [[ $(document_budget "$file") == "$floor $lf" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
        : > "$source"
        [[ $(document_budget "$file") == "$floor $lf" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
        python3 - "$source" <<'PYDATA'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b'x' * 5001)
PYDATA
        read -r bytes lines <<< "$(document_budget "$file")"
        expected=$((5001 * mult))
        (( expected < floor )) && expected=$floor
        (( expected > cap )) && expected=$cap
        expected_lines=$(((expected * lf + floor - 1) / floor))
        (( expected_lines > lc )) && expected_lines=$lc
        [[ "$bytes $lines" == "$expected $expected_lines" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
        python3 - "$source" <<'PYDATA'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b'x' * 100000)
PYDATA
        [[ $(document_budget "$file") == "$cap $lc" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    done < <(stage_documents "$stage")
done
before=$(document_budget FINAL_AUDIT.md)
printf 'generated plan changed substantially' > UPDATED_PROJECT_PLAN.md
[[ $(document_budget FINAL_AUDIT.md) == "$before" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Restore artifacts used by override and guard checks below.
printf 'abc\ndef' > PROJECT_PLAN.md
printf 'abc\ndef' > FINAL_AUDIT.md
WORKFLOW_DOC_MAX_BYTES=1 WORKFLOW_DOC_MAX_BYTES_FINAL_AUDIT=7 \
    WORKFLOW_DOC_MAX_LINES=1 WORKFLOW_DOC_MAX_LINES_FINAL_AUDIT=2 \
    check_document_budget FINAL_AUDIT.md
WORKFLOW_DOC_MAX_BYTES=1 WORKFLOW_DOC_MAX_BYTES_FINAL_AUDIT=7 \
    gated_prompt prompt.md final-audit reviewer > resolved
grep -qF 'FINAL_AUDIT.md: at most 7 UTF-8 bytes' "$(cat resolved)"
grep -q 'Reviewer output' "$(cat resolved)"
if WORKFLOW_DOC_MAX_BYTES_FINAL_AUDIT=invalid gated_prompt prompt.md final-audit 2>/dev/null; then exit 1; fi
# Draft targets use the effective override, including leading-zero integers.
WORKFLOW_DOC_MAX_BYTES=01000 gated_prompt prompt.md updated-plan > resolved
grep -qF 'Draft toward 850 bytes' "$(cat resolved)"
grep -qF 'supersede any fixed byte target' "$(cat resolved)"
# No installed/local output rules must not disable prompt budgets.
ROOT_SAVED="$ROOT"
ROOT=""
UNCLE_OUTPUT_RULES= gated_prompt prompt.md final-audit > resolved
grep -q 'Compact output budgets' "$(cat resolved)"
ROOT="$ROOT_SAVED"
# Code and raw logs are outside the document cap.
printf 'uncapped evidence' > raw.log
WORKFLOW_DOC_MAX_BYTES=1 check_document_budget raw.log
# Exercise the driver's post-agent guard: oversized output cannot reach approval.
awk '/^require_artifact\(\)/ {copy=1} copy {print} copy && /^}/ {exit}' \
    "$ROOT/scripts/stagegate.sh" > guard.sh
[[ -s guard.sh ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
bash -n guard.sh
. ./guard.sh
# Enforcing, the stage does not advance past an oversized document.
if (WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=1 require_artifact PROJECT_PLAN.md; touch advanced) 2>/dev/null; then
    exit 1
fi
[[ ! -e advanced && -s PROJECT_PLAN.md ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# By default it does advance, and the document survives. This is the whole
# behaviour change: a plan that ran for ten minutes and came out 3KB long is
# worth more than the limit it missed, and killing the stage there threw the
# work away and then re-ran it to produce the same overrun again.
(WORKFLOW_DOC_MAX_BYTES=1 require_artifact PROJECT_PLAN.md; touch advanced) 2>/dev/null \
    || { echo "FAIL $0:$LINENO an advisory overrun must not stop the stage" >&2; exit 1; }
[[ -e advanced && -s PROJECT_PLAN.md ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
rm -f advanced
(WORKFLOW_DOC_MAX_BYTES=7 require_artifact PROJECT_PLAN.md; touch advanced)
[[ -e advanced ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Standalone reviewer entry points also advertise and enforce the same cap.
mkdir -p standalone/scripts/lib standalone/.uncle/workflow/approvals
cp "$ROOT/scripts/lib/gates.sh" "$ROOT/scripts/lib/compact-review.py" standalone/scripts/lib/
cp "$ROOT/scripts/codex-review-plan.sh" "$ROOT/scripts/codex-create-checklist.sh" standalone/scripts/
cat > standalone/reviewer <<'STUB'
#!/usr/bin/env bash
out=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == --output-last-message ]]; then shift; out="$1"; fi
    prompt="$1"
    shift
done
printf '%s' "$prompt" > reviewer-prompt.txt
printf 'review body' > "$out"
STUB
chmod +x standalone/reviewer
(
    cd standalone
    printf 'source' > REQUIREMENTS.md
    printf 'plan' > PROJECT_PLAN.md
    printf 'plan' > UPDATED_PROJECT_PLAN.md
    printf 'tests' > AUTOMATED_TEST_REPORT.md
    for plan in PROJECT_PLAN UPDATED_PROJECT_PLAN; do
        hash_file "$plan.md" > ".uncle/workflow/approvals/$plan.sha256"
    done
    for script in codex-review-plan.sh codex-create-checklist.sh; do
        if WORKFLOW_REVIEW_COMPACT=0 WORKFLOW_REVIEWER_CMD="$PWD/reviewer" \
            WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_DOC_MAX_BYTES=1 \
            bash "scripts/$script" > rejected 2>&1; then exit 1; fi
        grep -q 'Document budget exceeded:' rejected
        grep -q 'at most 1 UTF-8 bytes' reviewer-prompt.txt
        WORKFLOW_REVIEWER_CMD="$PWD/reviewer" WORKFLOW_DOC_MAX_BYTES=100 \
            bash "scripts/$script" > /dev/null
    done
)
echo 'document-budget-test: passed'
