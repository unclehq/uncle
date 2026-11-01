#!/usr/bin/env bash
# After the automatic repair passes are used up, a failure that remains goes straight to the final audit; before that, or when repair
# was never available, the checklists still run; and a clean test review after successful repairs is not skipped past them.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SG="$ROOT/scripts/stagegate.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

route() {   # <WORKFLOW_REPAIR> <attempts> <used|none> [POSTFLIGHT] [runnable|unrunnable]; the application is unrunnable unless said otherwise
    local used="$3" stub='green_application_not_runnable() { return 0; }'
    [[ "${5:-unrunnable}" == unrunnable ]] || stub='green_application_not_runnable() { return 1; }'
    rm -f "$work/repair-count"; [[ "$used" == none ]] || printf '%s\n' "$used" > "$work/repair-count"
    env -i bash --norc --noprofile -c "
        STATE_DIR='$work'; WORKFLOW_REPAIR='$1'; WORKFLOW_AUTO_REPAIR_ATTEMPTS='$2'
        ${4:+WORKFLOW_POSTFLIGHT_GREEN_CHECK='$4'}
        $stub
        $(awk '/^repair_exhausted\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SG")
        $(awk '/^test_review_next_stage\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SG")
        test_review_next_stage"
}
[[ "$(route 1 2 2)" == FINAL_AUDIT ]]        || bad "two passes used of two should go to the audit"
[[ "$(route 1 2 3)" == FINAL_AUDIT ]]        || bad "more passes than allowed should go to the audit"
[[ "$(route 1 1 1)" == FINAL_AUDIT ]]        || bad "the only pass used should go to the audit"
[[ "$(route 1 2 1)" == MANUAL_CHECKLIST ]]   || bad "a pass remains: the checklists still run"
[[ "$(route 1 2 none)" == MANUAL_CHECKLIST ]] || bad "no pass has run: the checklists still run"
[[ "$(route 1 0 0)" == MANUAL_CHECKLIST ]]   || bad "attempts of 0 means repair never ran: the checklists still run"
[[ "$(route 0 0 0)" == MANUAL_CHECKLIST ]]   || bad "repair off: the checklists still run (it was never attempted)"
[[ "$(route 0 2 2)" == MANUAL_CHECKLIST ]]   || bad "repair off wins over a stale count"
[[ "$(route 1 2 2 0)" == MANUAL_CHECKLIST ]] || bad "WORKFLOW_POSTFLIGHT_GREEN_CHECK=0 keeps the checklists before the audit"

# Severity: with the passes used up, only an application that cannot build or start (or a runner that ran no tests) skips the checklists.
[[ "$(route 1 2 2 1 runnable)" == MANUAL_CHECKLIST ]]   || bad "a runnable application with a failing test still gets the checklists"
[[ "$(route 1 2 2 1 unrunnable)" == FINAL_AUDIT ]]      || bad "an unrunnable application goes straight to the audit"
[[ "$(route 1 2 1 1 unrunnable)" == MANUAL_CHECKLIST ]] || bad "a pass remains: even an unrunnable application takes the checklists route"

# The driver uses it where a failure is known to remain, and only there.
start="$(grep -n '^        VALIDATE_TEST_REVIEW)' "$SG" | tail -1 | cut -d: -f1)"
end="$(grep -n '^        REPAIR)' "$SG" | tail -1 | cut -d: -f1)"
block="$(sed -n "${start},${end}p" "$SG")"
[[ "$(grep -c 'acceptance_transition .uncle/docs/TEST_REVIEW.md "\$(test_review_next_stage)"' <<<"$block")" == 3 ]] \
    || bad "the three failing-check routes in VALIDATE_TEST_REVIEW do not use test_review_next_stage"
grep -q "continue_nonblocking_test_review MANUAL_CHECKLIST || \\\\" <<<"$block" \
    || bad "the nonblocking route lost its call"
grep -q "^                    acceptance_transition .uncle/docs/TEST_REVIEW.md MANUAL_CHECKLIST 'COVERAGE" <<<"$block" \
    || bad "a clean test review must still go on to MANUAL_CHECKLIST"
sed -n '/^continue_nonblocking_test_review()/,/^}/p' "$SG" | grep -q 'test_review_next_stage' \
    || bad "continue_nonblocking_test_review does not route an exhausted failure to the audit"
[[ $fail == 0 ]] && echo "repair-exhausted-route-test.sh: ok"
exit $fail
