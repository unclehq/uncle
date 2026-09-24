#!/usr/bin/env bash
set -euo pipefail

# A plan with no independently owned implementation steps uses the serial
# fallback.  That fallback must reconcile missing reports before validating
# implementation notes, otherwise a successful coding turn is discarded.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGEGATE="$ROOT/scripts/stagegate.sh"
PROMPT="$ROOT/prompts/implement.md"
HANDOFF="$ROOT/prompts/test-evidence-handoff.md"
PROJECT_PLAN="$ROOT/prompts/project-plan.md"
UPDATED_PLAN="$ROOT/prompts/updated-plan.md"

fail() { echo "FAIL: $*" >&2; exit 1; }

serial_block="$(sed -n '/^[[:space:]]*IMPLEMENT)/,/^[[:space:]]*PREFLIGHT)/p' "$STAGEGATE")"
[[ "$serial_block" == *"Implementation omitted a required handoff; reconciling reports without rerunning source."* ]] || fail "serial reconciliation missing"

handoff_pos="$(printf '%s\n' "$serial_block" | grep -n 'prompts/test-evidence-handoff.md implementation-report' | head -1 | cut -d: -f1)"
validate_pos="$(printf '%s\n' "$serial_block" | grep -n 'implementation_notes.py" validate' | head -1 | cut -d: -f1)"
[[ -n "$handoff_pos" && -n "$validate_pos" && "$handoff_pos" -lt "$validate_pos" ]] || fail "serial reconciliation must precede notes validation"

grep -Fq 'A plan step labelled `Reconcile` is not an exception' "$PROMPT" || fail "serial prompt lacks reconciliation boundary"
grep -Fq 'Never run the approved full Verification commands block here' "$HANDOFF" || fail "handoff can rerun driver verification"
grep -Fq '`.uncle/workflow/documents/IMPLEMENTATION_NOTES.json`' "$HANDOFF" || fail "handoff does not write canonical notes"
grep -Fq '"kind":"automated-test-report"' "$HANDOFF" || fail "handoff does not produce canonical test-report JSON"
grep -Fq 'test_report.py" validate . application' "$STAGEGATE" || fail "application test report is not ingested"
grep -Fq 'test_report.py" validate . change' "$ROOT/scripts/change-workflow.sh" || fail "change test report is not ingested"
for prompt in "$PROJECT_PLAN" "$UPDATED_PLAN"; do
    grep -Fq 'must never instruct the implementation agent to run the `Verification commands`' "$prompt" || fail "$(basename "$prompt") can put driver verification in a reconcile step"
done

echo "serial implementation handoff tests passed"
