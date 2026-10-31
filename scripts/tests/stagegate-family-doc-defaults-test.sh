#!/usr/bin/env bash
# Phase (a) of the stagegate/change-workflow consolidation: stagegate.sh gained
# family-conditional document-path variables (PLAN_DOC, PLAN_DOC_NAME,
# TEST_REPORT_DOC) so the shared IMPLEMENT/WAIT_IMPLEMENT_APPROVAL/
# MANUAL_CHECKLIST/EXECUTE_CHECKLIST/VALIDATE_CHECKLIST/FINAL_AUDIT/
# WAIT_AUDIT_OVERRIDE states can eventually be shared with change-workflow.sh.
# This must be a no-op for every existing app-family run: with WORKFLOW_FAMILY
# unset (or "app"), each variable must resolve to exactly the historical
# hardcoded path it replaced.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

eval_family_vars() {
    # Source just enough of stagegate.sh's family-default block in isolation
    # by extracting it verbatim and running it in a subshell, rather than
    # executing the whole driver (which requires a full project/run context).
    local family="$1"
    local block
    block="$(sed -n '/^WORKFLOW_FAMILY="\${WORKFLOW_FAMILY:-app}"$/,/^fi$/p' "$ROOT/scripts/stagegate.sh")"
    [[ -n "$block" ]] || { echo 'FATAL: could not extract family-default block from stagegate.sh' >&2; exit 2; }
    (
        WORKFLOW_FAMILY="$family"
        eval "$block"
        printf 'PLAN_DOC=%s\nPLAN_DOC_NAME=%s\nTEST_REPORT_DOC=%s\n' \
            "$PLAN_DOC" "$PLAN_DOC_NAME" "$TEST_REPORT_DOC"
    )
}

# --- app family (default / unset) must byte-match the pre-refactor hardcoded
# paths that used to appear directly at the IMPLEMENT/WAIT_IMPLEMENT_APPROVAL
# call sites. ---
out="$(eval_family_vars app)"
plan_doc="$(printf '%s\n' "$out" | sed -n 's/^PLAN_DOC=//p')"
plan_name="$(printf '%s\n' "$out" | sed -n 's/^PLAN_DOC_NAME=//p')"
test_report_doc="$(printf '%s\n' "$out" | sed -n 's/^TEST_REPORT_DOC=//p')"

[[ "$plan_doc" == ".uncle/docs/UPDATED_PROJECT_PLAN.md" ]] && ok || bad "app-plan-doc" "got '$plan_doc'"
[[ "$plan_name" == "UPDATED_PROJECT_PLAN" ]] && ok || bad "app-plan-doc-name" "got '$plan_name'"
[[ "$test_report_doc" == ".uncle/docs/AUTOMATED_TEST_REPORT.md" ]] && ok || bad "app-test-report-doc" "got '$test_report_doc'"

# unset WORKFLOW_FAMILY must behave identically to "app" (the real driver
# never sets it, so this is the path every existing run actually takes).
out_unset="$(
    block="$(sed -n '/^WORKFLOW_FAMILY="\${WORKFLOW_FAMILY:-app}"$/,/^fi$/p' "$ROOT/scripts/stagegate.sh")"
    unset WORKFLOW_FAMILY
    eval "$block"
    printf 'PLAN_DOC=%s\nPLAN_DOC_NAME=%s\nTEST_REPORT_DOC=%s\n' \
        "$PLAN_DOC" "$PLAN_DOC_NAME" "$TEST_REPORT_DOC"
)"
[[ "$out_unset" == "$out" ]] && ok || bad "unset-matches-app" "unset WORKFLOW_FAMILY diverged from explicit 'app'"

# --- the IMPLEMENT/WAIT_IMPLEMENT_APPROVAL call sites must actually use the
# variables (not just define them unused). ---
grep -q 'verify_approval \\\s*$' "$ROOT/scripts/stagegate.sh" 2>/dev/null || true
if grep -q '"\$PLAN_DOC"' "$ROOT/scripts/stagegate.sh" && grep -q '"\$PLAN_DOC_NAME"' "$ROOT/scripts/stagegate.sh"; then
    ok
else
    bad "plan-doc-wired" "PLAN_DOC/PLAN_DOC_NAME are defined but never referenced"
fi
if grep -q '"\$TEST_REPORT_DOC"' "$ROOT/scripts/stagegate.sh"; then ok
else bad "test-report-doc-wired" "TEST_REPORT_DOC is defined but never referenced"; fi

# No literal hardcoded UPDATED_PROJECT_PLAN.md/AUTOMATED_TEST_REPORT.md should
# remain inside the IMPLEMENT state block (lines between the IMPLEMENT and
# WAIT_IMPLEMENT_APPROVAL case labels in the main loop) -- if one does, the
# variable indirection is incomplete and a change-family caller would see the
# wrong document.
# stagegate.sh has two "IMPLEMENT)" case labels (run_stage()'s internal
# dispatch and the main loop's own state); only the main loop's -- the one
# immediately preceding WAIT_IMPLEMENT_APPROVAL) -- is the state this test
# means. Anchor on the last IMPLEMENT) before that label, not the first one
# in the file.
wait_line="$(grep -n '^        WAIT_IMPLEMENT_APPROVAL)$' "$ROOT/scripts/stagegate.sh" | head -1 | cut -d: -f1)"
implement_line="$(grep -n '^        IMPLEMENT)$' "$ROOT/scripts/stagegate.sh" | awk -F: -v w="$wait_line" '$1 < w { line = $1 } END { print line }')"
# The PREFLIGHT-revalidation hash check ("has the plan changed since the
# backgrounded probe started?") is deliberately excluded: it is app-only
# machinery with no change-family analogue at all (change-workflow.sh has no
# PREFLIGHT state), documented as a scoped exception rather than forced into
# PLAN_DOC in phase (a) of the stagegate/change-workflow consolidation.
implement_block="$(sed -n "${implement_line},${wait_line}p" "$ROOT/scripts/stagegate.sh" | tail -n +2 \
    | grep -v 'preflight-plan\.sha256')"
if printf '%s' "$implement_block" | grep -q '\.uncle/docs/UPDATED_PROJECT_PLAN\.md\|\.uncle/docs/AUTOMATED_TEST_REPORT\.md'; then
    bad "no-stray-literals" "IMPLEMENT block still has a hardcoded app-family doc path alongside the variables"
else
    ok
fi

echo "stagegate-family-doc-defaults-test.sh: $PASS checks passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
