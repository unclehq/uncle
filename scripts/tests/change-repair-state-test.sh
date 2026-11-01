#!/usr/bin/env bash
# The change driver has a REPAIR state like stagegate.sh's: eligibility, one focused pass, the judge's verdicts, and where an exhausted repair goes.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CW="$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

body="$(awk '/^        REPAIR\)/{p=1;next} p&&/^        [A-Z_]+\)$/{exit} p{print}' "$CW")"
nextfn="$(awk '/^change_repair_next_stage\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$CW")"
[[ -n "$body" && -n "$nextfn" ]] || bad "could not extract the REPAIR state"

n=0
go() {   # <repair-count|none> <judge rc> <unrunnable|runnable> [repair-source] [env...] -> what the state did
    n="$(( $(cat "$work/n" 2>/dev/null || echo 0) + 1 ))"; echo "$n" > "$work/n"
    local dir="$work/p$n"; echo "$dir" > "$work/last"; mkdir -p "$dir/.uncle/workflow/documents" "$dir/.uncle/workflow/logs" "$dir/.uncle/docs"
    local src="${4:-.uncle/docs/TEST_REVIEW.md}"
    printf '%s\n' "$src" > "$dir/.uncle/workflow/repair-source"
    [[ "$1" == none ]] || printf '%s\n' "$1" > "$dir/.uncle/workflow/repair-count"
    : > "$dir/.uncle/docs/TEST_REVIEW.md"; echo '{}' > "$dir/.uncle/workflow/documents/TEST_REVIEW.json"; echo '{}' > "$dir/.uncle/workflow/documents/IMPLEMENTATION_NOTES.json"; echo '{}' > "$dir/.uncle/workflow/documents/FINAL_AUDIT.json"; : > "$dir/.uncle/docs/FINAL_AUDIT.md"; : > "$dir/.uncle/workflow/audit-verdict"; : > "$dir/.uncle/workflow/audit-verdict.original"
    [[ "$3" == unrunnable ]] && echo 'error when starting dev server' > "$dir/.uncle/workflow/logs/green-check.log" || : > "$dir/.uncle/workflow/logs/green-check.log"
    ( cd "$dir" && env -i PATH="$PATH" HOME="$HOME" "${@:5}" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'; GREEN_BG_PID=''; VERDICT_FILE='.uncle/workflow/audit-verdict'; AUDIT_OVERRIDE_FILE='.uncle/workflow/audit-override'
        WORKFLOW_AUTO_REPAIR_ATTEMPTS=\${WORKFLOW_AUTO_REPAIR_ATTEMPTS:-2}; BUDGET_IMPLEMENT=5; MODEL_IMPLEMENT=m
        require_file() { [[ -s \"\$1\" ]]; }
        record_nonblocking_failure() { echo \"nonblocking:\$1\"; }
        record_test_failure_disposition() { :; }
        set_state() { echo \"state=\$1\"; }
        plan_before_write() { echo \"plan_before:\$1\"; return 0; }
        plan_after_write() { return 0; }
        plan_revise() { :; }
        repair_begin() { REPAIR_PROMPT=prompt.md; }
        envelope_invalidate() { :; }; envelope_guard_begin() { :; }; envelope_guard_end() { :; }
        run_claude() { echo \"agent:\$2\"; }
        recover_missing_implementation_reports() { return 0; }
        repair_judge() { return $2; }
        start_green_check_bg() { echo green-restarted; }
        python3() { case \"\$*\" in *completion_preview*) return 0;; esac; command python3 \"\$@\"; }
        $nextfn
        for _ in 1; do case REPAIR in REPAIR)
        $body
        esac; done; echo end" 2>&1 )
}

out="$(go none 0 runnable)"
grep -q 'agent:repair' <<< "$out"                     || bad "no repair pass ran: $out"
grep -q 'plan_before:repair-1' <<< "$out"             || bad "the plan was not told about the repair"
grep -q 'green-restarted' <<< "$out" && grep -q 'state=TEST_REVIEW' <<< "$out" || bad "a repair that changed the tree should verify again and re-review: $out"
LAST="$(cat "$work/last")"
[[ ! -e "$LAST/.uncle/workflow/documents/TEST_REVIEW.json" && ! -e "$LAST/.uncle/docs/TEST_REVIEW.md" ]] || bad "the stale review was kept"
[[ "$(cat "$LAST/.uncle/workflow/repair-count")" == 1 ]] || bad "the pass was not counted"
[[ ! -e "$LAST/.uncle/workflow/documents/FINAL_AUDIT.json" && ! -e "$LAST/.uncle/docs/FINAL_AUDIT.md" && ! -e "$LAST/.uncle/workflow/audit-verdict" && ! -e "$LAST/.uncle/workflow/audit-verdict.original" ]] || bad "a repair left the stale final audit and its verdict in place"

out="$(go 1 0 runnable)"
grep -q 'plan_before:repair-2' <<< "$out" || bad "the second pass should be counted as 2"

out="$(go 0 3 runnable)"
grep -q 'state=' <<< "$out" && bad "a no-op pass (judge 3) should re-enter REPAIR without setting a state: $out"
grep -q 'green-restarted' <<< "$out" && bad "judge 3 must not restart verification: $out"

out="$(go 1 6 runnable)"
grep -q 'state=MANUAL_CHECKLIST' <<< "$out"                  || bad "spent passes with a runnable application go to the checklist: $out"
out="$(go 1 6 unrunnable)"
grep -q 'state=FINAL_AUDIT' <<< "$out"                || bad "spent passes with an unrunnable application go to the audit: $out"

out="$(go 2 0 runnable)"
grep -q 'agent:' <<< "$out" && bad "no pass may run once two are spent: $out"
grep -q 'state=MANUAL_CHECKLIST' <<< "$out" && grep -q 'nonblocking:TEST_REVIEW.md' <<< "$out" || bad "an ineligible repair of the test review goes on as unresolved evidence: $out"
out="$(go 2 0 unrunnable)"
grep -q 'state=FINAL_AUDIT' <<< "$out"                || bad "ineligible and unrunnable: final audit: $out"
out="$(go 2 0 runnable .uncle/docs/VERIFICATION_REPORT.md)"
grep -q 'state=FINAL_AUDIT' <<< "$out"                || bad "an ineligible repair of the checklist report goes to the audit: $out"
out="$(go none 0 runnable .uncle/docs/TEST_REVIEW.md WORKFLOW_AUTO_REPAIR_ATTEMPTS=0)"
grep -q 'agent:' <<< "$out" && bad "with no passes allowed nothing is repaired"


# once the checklist has run, spent passes go to the audit, never back through a checklist that already ran
out="$(go 1 6 runnable .uncle/docs/TEST_REVIEW.md)"
mkproj_marker() { :; }
dir="$work/ran"; mkdir -p "$dir/.uncle/workflow/logs"; : > "$dir/.uncle/workflow/checklist-ran"; : > "$dir/.uncle/workflow/logs/green-check.log"
got="$(cd "$dir" && env -i PATH="$PATH" bash --norc --noprofile -c "ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'; $nextfn; change_repair_next_stage")"
[[ "$got" == FINAL_AUDIT ]] || bad "after the checklist ran, the next stage must be FINAL_AUDIT, got '$got'"

# VALIDATE_CHECKLIST: a driver command that still fails is repaired before the audit; with no pass left it goes to the audit
vc="$(awk '/^        VALIDATE_CHECKLIST\)/{p=1;next} p&&/^        [A-Z_]+\)$/{exit} p{print}' "$CW" | awk '/: > "\$STATE_DIR\/checklist-ran"/{p=1} p{print} p&&/^            fi$/{exit}')"
[[ -n "$vc" ]] || bad "could not extract the regression routing from VALIDATE_CHECKLIST"
route() {   # <repair-count> <regressions> -> state=… and whether the marker was written
    local dir="$work/vc$((++n))"; mkdir -p "$dir/s"; printf '%s\n' "$1" > "$dir/s/repair-count"
    ( cd "$dir" && env -i PATH="$PATH" bash --norc --noprofile -c "
        STATE_DIR='s'; GREEN_CHECK=1; GREEN_CLASS='s/g.tsv'; GREEN_MD='s/green-check.md'; WORKFLOW_AUTO_REPAIR_ATTEMPTS=2
        printf 'PASS\tnpm ci\n' > s/g.tsv
        green_regressions() { echo $2; }
        record_nonblocking_failure() { echo \"nonblocking:\$1\"; }
        record_test_failure_disposition() { :; }
        set_state() { echo \"state=\$1\"; }
        for _ in 1; do
        $vc
        echo fell-through; done; [[ -e s/checklist-ran ]] && echo marked; cat s/repair-source 2>/dev/null" 2>&1 )
}
out="$(route 0 1)"
grep -q 'state=REPAIR' <<< "$out" && grep -q 'marked' <<< "$out" && grep -q 'green-check.md' <<< "$out" || bad "a remaining regression with passes left should repair: $out"
out="$(route 2 1)"
grep -q 'state=FINAL_AUDIT' <<< "$out" && grep -q 'nonblocking:green-check' <<< "$out" || bad "a remaining regression with no pass left should go to the audit: $out"
out="$(route 0 0)"
grep -q 'fell-through' <<< "$out" && ! grep -q 'state=' <<< "$out" || bad "no regression: fall through to the acceptance routing: $out"

# a run saved under the old checklist state name resumes at MANUAL_CHECKLIST, as stagegate.sh names it
gs="$(awk '/^get_state\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$CW")"
alias_of() { env -i PATH="$PATH" bash --norc --noprofile -c "STATE_FILE=x; state_read() { printf '%s' '$1'; }; $gs; get_state"; }
[[ "$(alias_of CHECKLIST)" == MANUAL_CHECKLIST ]] || bad "a saved CHECKLIST state does not resume at MANUAL_CHECKLIST"
[[ "$(alias_of MANUAL_CHECKLIST)" == MANUAL_CHECKLIST && "$(alias_of EXECUTE_CHECKLIST)" == EXECUTE_CHECKLIST ]] || bad "get_state changed a state that needed no alias"
grep -qE '^        CHECKLIST\)$' "$CW" && bad "the driver still has a CHECKLIST state"
grep -q "'manual-checklist':'MANUAL_CHECKLIST'" "$ROOT/scripts/lib/rerun_stage.py" || bad "rerun_stage does not name the checklist state MANUAL_CHECKLIST"

# the driver sends failing acceptance rows here, and nowhere else
grep -q "'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS' REPAIR" "$CW" || bad "VALIDATE_TEST_REVIEW does not route to REPAIR"
grep -q "acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT '' REPAIR" "$CW" || bad "VALIDATE_CHECKLIST does not route to REPAIR"
grep -q 'final_audit_override_recovery "$audit_class" "${STAGEGATE_RUN_ID:--}" 1' "$CW" || bad "a NOT READY audit does not take the repair-before-waiver route"
grep -q '^REPAIR_BASE_PROMPT=prompts/change/repair.md' "$CW" || bad "the change driver does not name its own repair prompt"
[[ -s "$ROOT/prompts/change/repair.md" ]] || bad "prompts/change/repair.md is missing"
grep -q 'UPDATED_PROJECT_PLAN\|AUTOMATED_TEST_REPORT' "$ROOT/prompts/change/repair.md" && bad "the change repair prompt names new-application documents"
[[ $fail == 0 ]] && echo "change-repair-state-test.sh: ok"
exit $fail
