#!/usr/bin/env bash
# CLASSIFY runs before PROJECT_PLAN in the application flow, and the plan uses the class: a small application is planned in
# one pass to a size budget, and the plan's size is checked again afterwards (which can only raise the class).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SG="$ROOT/scripts/stagegate.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

# --- the order of the states ----------------------------------------------------------------------------------------------
state_block() { awk -v s="        $1)" '$0 == s {p=1; next} p && /^        [A-Z_]+\)$/ {exit} p' "$SG" | tail -n +1; }
# the second dispatch (the real state machine) is the one after DERIVE_BRIEF's wait; take the last block with that label
last_block() { awk -v s="        $1)" '$0 == s {buf=""; p=1; next} p && /^        [A-Z_]+\)$/ {p=0} p {buf = buf $0 "\n"} END {printf "%s", buf}' "$SG"; }
last_block VALIDATE_REQUIREMENTS | grep -q 'set_state CLASSIFY' || bad "VALIDATE_REQUIREMENTS does not go to CLASSIFY"
last_block CLASSIFY | grep -q 'classify_change_stage app .uncle/docs/REQUIREMENTS_INTERPRETATION.md' || bad "CLASSIFY does not classify the interpretation"
last_block CLASSIFY | grep -q 'set_state WAIT_REQUIREMENTS_APPROVAL' || bad "CLASSIFY does not go on to the requirements gate"
last_block PROJECT_PLAN | grep -q 'change_class_recheck app .uncle/docs/PROJECT_PLAN.md' || bad "PROJECT_PLAN does not recheck the class"
last_block PROJECT_PLAN | grep -q 'set_state WAIT_PLAN_APPROVAL' || bad "PROJECT_PLAN does not go to the plan gate"
last_block PROJECT_PLAN | grep -q 'set_state CLASSIFY' && bad "PROJECT_PLAN still routes through CLASSIFY"
grep -q 'change_class_budget' "$ROOT/scripts/lib/gates.sh" || bad "the plan prompt does not get the class budget"

# --- the sections gate, run for real --------------------------------------------------------------------------------------
gate() {   # <class-says-single: yes|no> [env...]
    local single="$1"; shift
    env -i bash --norc --noprofile -c "$(printf '%s\n' "$@")
        $(awk '/^project_plan_sections_enabled\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SG")
        change_class_plan_single() { [[ '$single' == yes ]]; }
        project_plan_sections_enabled && echo sections || echo single"
}
[[ "$(gate yes)" == single ]]   || bad "a small application should be planned in one pass by default"
[[ "$(gate no)" == sections ]]  || bad "a larger application keeps the sectioned plan"
[[ "$(gate yes 'WORKFLOW_PROJECT_PLAN_SECTIONS=1')" == sections ]] || bad "an explicit WORKFLOW_PROJECT_PLAN_SECTIONS=1 must win over the class"
[[ "$(gate no 'WORKFLOW_PROJECT_PLAN_SECTIONS=0')" == single ]]    || bad "an explicit 0 still turns sections off"

# --- the helpers, against a real change-class.json -------------------------------------------------------------------------
mkdir -p "$work/p/.uncle/workflow"; cd "$work/p"
STATE_DIR="$PWD/.uncle/workflow"
. "$ROOT/scripts/lib/change-class-stage.sh"
put() { printf '%s\n' "$1" > .uncle/workflow/change-class.json; }
change_class_plan_single && bad "no classification must not mean a one-pass plan"
[[ -z "$(change_class_budget)" ]] || bad "no classification must give no budget"
put '{"family": "app", "class": "small"}'
change_class_plan_single || bad "a small app was not recognised"
[[ "$(change_class_budget)" == *"classified **small**"* ]] || bad "a small app got no budget"
WORKFLOW_CLASSIFY=0 change_class_plan_single && bad "WORKFLOW_CLASSIFY=0 must switch the one-pass plan off"
[[ -z "$(WORKFLOW_CLASSIFY=0 change_class_budget)" ]] || bad "WORKFLOW_CLASSIFY=0 must give no budget"
put '{"family": "app", "class": "standard"}'
change_class_plan_single && bad "a standard app must keep the sectioned plan"
put '{"family": "change", "class": "small"}'
change_class_plan_single && bad "a change request is not planned by the application planner"

# --- the budget reaches the real plan prompt (project-plan is a synthesis stage with its own early return) ------------------
printf '# Project plan prompt\nWrite the plan.\n' > "$work/plan-prompt.md"
composed() {   # the prompt gated_prompt builds for the plan stage, run for real
    env -i PATH="$PATH" HOME="$HOME" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='$work/p/.uncle/workflow'; LOG_DIR='$work/logs'; mkdir -p \"\$LOG_DIR\"
        . '$ROOT/scripts/lib/gates.sh'; . '$ROOT/scripts/lib/change-class-stage.sh'
        cd '$work/p'
        f=\$(gated_prompt '$work/plan-prompt.md' project-plan agent) && cat \"\$f\""
}
put '{"family": "app", "class": "small"}'
[[ "$(composed)" == *"Build class (binding)"* ]] || bad "a small application's plan prompt has no budget"
[[ "$(composed)" == *"at most 12 implementation steps and 30 owned files"* ]] || bad "the budget paragraph does not state the limits"
put '{"family": "app", "class": "standard"}'
[[ "$(composed)" == *"Build class (binding)"* ]] && bad "a standard application's plan prompt must not get the small budget"
rm -f .uncle/workflow/change-class.json
[[ "$(composed)" == *"Build class (binding)"* ]] && bad "no classification must mean no budget"
[[ "$(WORKFLOW_CLASSIFY=0 composed)" == *"Write the plan."* ]] || bad "the plan prompt itself must still be composed"
[[ $fail == 0 ]] && echo "plan-uses-class-test.sh: ok"
exit $fail
