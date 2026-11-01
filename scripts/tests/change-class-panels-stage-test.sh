#!/usr/bin/env bash
# The shell helpers and driver wiring that apply the class profile to the stages after planning, run against a real
# change-class.json: the classified value is used, an explicit environment value wins, and no classification changes nothing.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

mkdir -p "$work/p/.uncle/workflow"
. "$ROOT/scripts/lib/change-class-stage.sh"
cd "$work/p"

put() {   # put <json fields...>
    printf '{%s}\n' "$1" > .uncle/workflow/change-class.json
}

eq "no classification: panel default stands" "$(change_class_panel checklist_lenses 'a b c' X_UNSET)" "a b c"
eq "no classification: subset default stands" "$(change_class_panel_subset final_audit_lenses 'a b' X_UNSET)" "a b"
change_class_implement_single && bad "no classification must not mean a single session"

put '"checklist_lenses": ["coverage","regressions"], "final_audit_lenses": ["verification","waivers"], "execute_workers": 2, "implement_mode": "single"'
eq "classified panel" "$(change_class_panel checklist_lenses 'a b c' X_UNSET)" "coverage regressions"
eq "classified worker cap" "$(change_class_panel execute_workers 8 X_UNSET)" "2"
change_class_implement_single || bad "a single-session class was not recognised"
eq "subset keeps only what the driver's default has" \
    "$(change_class_panel_subset checklist_lenses 'coverage invariants resources' X_UNSET)" "coverage"
eq "subset never adds a lens the default left out (new apps have no regressions lens)" \
    "$(change_class_panel_subset final_audit_lenses 'verification scope regression waivers' X_UNSET)" "verification waivers"
eq "an empty intersection falls back to the default" \
    "$(change_class_panel_subset checklist_lenses 'invariants resources' X_UNSET)" "invariants resources"

export WORKFLOW_CHECKLIST_LENSES='coverage invariants'
eq "an explicit environment value wins" "$(change_class_panel checklist_lenses 'a b' WORKFLOW_CHECKLIST_LENSES)" "coverage invariants"
unset WORKFLOW_CHECKLIST_LENSES

put '"implement_mode": "auto"'
change_class_implement_single && bad "auto must not be a single session"

# The drivers must actually use them.
cw="$ROOT/scripts/change-workflow.sh"; sg="$ROOT/scripts/stagegate.sh"
grep -q 'change_class_implement_single && return 1' "$cw" || bad "stepwise_implementation_enabled ignores the class"
grep -q 'change_class_panel checklist_lenses' "$cw" || bad "change checklist panel ignores the class"
grep -q 'change_class_panel final_audit_lenses' "$cw" || bad "change final audit ignores the class"
grep -q 'change_class_panel execute_workers' "$cw" || bad "change execute workers ignore the class"
grep -q 'change_class_panel_subset final_audit_lenses' "$sg" || bad "app final audit ignores the class"
grep -q 'change_class_panel_subset checklist_lenses' "$sg" || bad "app checklist panel ignores the class"
grep -q 'change_class_panel execute_workers' "$sg" || bad "app execute workers ignore the class"
[[ "$(grep -c 'test_review_lenses)' "$sg")" -ge 5 ]] || bad "app test-review panel does not use the class lenses everywhere"
grep -q 'for lens in coverage assertions oracle' "$sg" && bad "a hard-coded test-review lens loop is left"
[[ $fail == 0 ]] && echo "change-class-panels-stage-test.sh: ok"
exit $fail
