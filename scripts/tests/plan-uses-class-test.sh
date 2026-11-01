#!/usr/bin/env bash
# CLASSIFY runs before PROJECT_PLAN in the application flow, and the plan uses the class: a small application is planned in
# to a size budget, and the plan's size is checked again afterwards (which can only raise the class). A small application keeps
# the sectioned plan: the single-pass plan wrote Owns: entries that were commands, not files, and was rejected on every retry.
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

# --- the sections gate: the class does not turn sections off -----------------------------------------------------------------
gate() {   # [env...]
    env -i bash --norc --noprofile -c "$(printf '%s\n' "$@")
        $(awk '/^project_plan_sections_enabled\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SG")
        project_plan_sections_enabled && echo sections || echo single"
}
[[ "$(gate)" == sections ]] || bad "sections must stay on by default, including for a small application"
[[ "$(gate 'WORKFLOW_PROJECT_PLAN_SECTIONS=0')" == single ]] || bad "an explicit 0 still turns sections off"
grep -q 'change_class_plan_single' "$SG" "$ROOT/scripts/lib/change-class-stage.sh" && bad "the class must not switch the plan to a single pass"

# --- the budget goes to the sections that size the plan ----------------------------------------------------------------
budget_for() {   # <section name> -> appended text
    local f="$work/section-$1.md"; printf 'base\n' > "$f"
    env -i bash --norc --noprofile -c "
        change_class_budget() { printf 'BUDGET\n'; }
        $(awk '/^project_plan_section_budget\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SG")
        project_plan_section_budget '$1' '$f'"
    tr '\n' ' ' < "$f"
}
[[ "$(budget_for steps)" == "base BUDGET " ]] || bad "the steps section does not get the budget"
[[ "$(budget_for sequence)" == "base BUDGET " ]] || bad "the sequence section does not get the budget"
[[ "$(budget_for design)" == "base " ]] || bad "a section that does not size the plan got the budget"
[[ "$(grep -c 'project_plan_section_budget "$name" "$prompt"' "$SG")" == 2 ]] || bad "both delivery modes must apply the budget"

# --- the helpers, against a real change-class.json -------------------------------------------------------------------------
mkdir -p "$work/p/.uncle/workflow"; cd "$work/p"
STATE_DIR="$PWD/.uncle/workflow"
. "$ROOT/scripts/lib/change-class-stage.sh"
put() { printf '%s\n' "$1" > .uncle/workflow/change-class.json; }
[[ -z "$(change_class_budget)" ]] || bad "no classification must give no budget"
put '{"family": "app", "class": "small"}'
[[ "$(change_class_budget)" == *"classified **small**"* ]] || bad "a small app got no budget"
[[ -z "$(WORKFLOW_CLASSIFY=0 change_class_budget)" ]] || bad "WORKFLOW_CLASSIFY=0 must give no budget"
put '{"family": "app", "class": "standard"}'
put '{"family": "change", "class": "small"}'

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
