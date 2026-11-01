#!/usr/bin/env bash
# The final-audit panel bounds each lens: a lens with no valid packet is run once more, alone; if it still has none it is documented and
# the audit continues with the other lenses; only a panel with no valid lens at all stops. Both drivers, the real function.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

case_no=0
fresh() { case_no=$((case_no + 1)); project="$work/case-$case_no"; }
run_panel() {   # <driver> <lenses that never deliver> <lenses that fail once>  -> "rc=N"; runs in $project (call fresh first)
    local driver="$1" never="$2" once="$3"
    mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/workflow/logs" "$project/.uncle/docs"
    ( cd "$project" && env -i PATH="$PATH" HOME="$HOME" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'; CODEX_EFFORT_AUDIT=low
        NEVER=' $never '; ONCE=' $once '
        stage_uses_self_hosted() { return 1; }
        change_class_panel() { printf '%s' \"\$2\"; }
        change_class_panel_subset() { printf '%s' \"\$2\"; }
        record_nonblocking_failure() { printf '%s\t%s\n' \"\$1\" \"\$2\" >> .uncle/workflow/ledger; }
        packet() {   # prompt output name
            local lens=\"\${3#final-audit-review-worker-}\"; lens=\"\${lens%-retry}\"
            echo \"\$3\" >> .uncle/workflow/calls
            [[ \"\$NEVER\" != *\" \$lens \"* ]] || return 0
            if [[ \"\$ONCE\" == *\" \$lens \"* && \$(grep -cE \"^final-audit-review-worker-\$lens(-retry)?\$\" .uncle/workflow/calls) == 1 ]]; then return 0; fi
            printf '%s' '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"final-audit-worker-packet\",\"findings\":[]}' > \"\$2\"
        }
        run_codex_review() { packet \"\$@\"; }
        run_codex() { packet \"\$@\"; }
        $(awk '/^audit_review_call\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/$driver")
        $(awk '/^run_final_audit_panel\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/$driver")
        run_final_audit_panel 2>/dev/null
        echo rc=\$?" 2>&1 )
}
count() { grep -c "^final-audit-review-worker-$1\$" "$project/.uncle/workflow/calls" 2>/dev/null || echo 0; }
lenses_in() { python3 -c "
import json,sys
d=json.load(open('$project/.uncle/workflow/documents/FINAL_AUDIT_WORKERS.json'))
print(' '.join(sorted(k for k in (d.get('workers') or d.get('packets') or {}) )) if isinstance(d.get('workers') or d.get('packets'), dict) else json.dumps(d)[:200])" 2>/dev/null; }

for driver in stagegate.sh change-workflow.sh; do
    fresh; out="$(run_panel "$driver" '' '')"
    [[ "$out" == *rc=0 ]] || bad "$driver: a healthy panel failed: $out"
    eq "$driver: every lens ran once" "$(count verification)$(count scope)$(count regression)$(count waivers)" 1111
    [[ ! -e "$project/.uncle/workflow/ledger" ]] || bad "$driver: a healthy panel recorded a failure"

    fresh; out="$(run_panel "$driver" '' 'scope')"
    [[ "$out" == *rc=0 ]] || bad "$driver: a lens that recovered on retry stopped the panel: $out"
    eq "$driver: only the failed lens ran again" "$(count verification)$(count scope)$(count scope-retry)$(count regression)$(count waivers)" 11111
    [[ ! -e "$project/.uncle/workflow/ledger" ]] || bad "$driver: a recovered lens was recorded as a failure"

    fresh; out="$(run_panel "$driver" 'waivers' '')"
    [[ "$out" == *rc=0 ]] || bad "$driver: a lens that never delivered stopped the audit: $out"
    eq "$driver: the missing lens was tried exactly twice" "$(count waivers)$(count waivers-retry)" 11
    eq "$driver: the others ran once" "$(count verification)$(count scope)$(count regression)" 111
    grep -q 'lens waivers did not complete' "$project/.uncle/workflow/ledger" 2>/dev/null || bad "$driver: the missing lens is not documented"
    [[ -s "$project/.uncle/workflow/documents/FINAL_AUDIT_WORKERS.json" ]] || bad "$driver: no collated packet was written"
    grep -q waivers "$project/.uncle/workflow/documents/FINAL_AUDIT_WORKERS.json" && bad "$driver: the missing lens is in the collated packet"

    fresh; out="$(run_panel "$driver" 'verification scope regression waivers' '')"
    [[ "$out" == *rc=1 ]] || bad "$driver: a panel with no lens must stop: $out"
done
for driver in stagegate.sh change-workflow.sh; do
    grep -q 'workflow_bounded_lens final-audit' "$ROOT/scripts/$driver" || bad "$driver does not bound the final-audit lenses"
done
[[ $fail == 0 ]] && echo "final-audit-lens-bound-test.sh: ok"
exit $fail
