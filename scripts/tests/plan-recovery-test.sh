#!/usr/bin/env bash
set -uo pipefail
# This suite exercises the explicitly requested standalone assessment mode.
export WORKFLOW_EXECUTABILITY_REVIEW=1
UNCLE_TEST_FIXTURES_ONLY=1 source "$(dirname "$0")/gates-test.sh"

new_case unsupported-denial
set_state WAIT_UPDATED_PLAN_APPROVAL
green_baseline 0 'bash app/test.sh'
printf '\nRestriction R-1: DESIGN blanket tool denial; property mediated access.\n' >> "$REPO/CHANGE_PLAN.md"
hash_file "$REPO/CHANGE_PLAN.md" > "$REPO/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
printf 'AR-001: blanket denial is unsupported by this runner.\n' > "$REPO/ADVERSARIAL_REVIEW.md"
run_driver FAKE_ASSESS_NO_APPROVAL=1 FAKE_CAP_STATUS=UNSUPPORTED FAKE_IMPL='echo unsafe-launch > app/added.sh'
expect_no_file app/added.sh
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'
expect_in_file CHANGE_PLAN.md 'isolated-context revision'


new_case denial-revised-from-plan
set_state PLAN
run_driver_stdin "$(gate_input y y y y y n)" FAKE_ASSESS_NO_APPROVAL=1 FAKE_CAP_STATUS=UNSUPPORTED FAKE_PLAN_DENIAL=1 FAKE_IMPL='echo alternative > app/main.sh'
expect_status 0
expect_state COMPLETE
expect_in_file app/main.sh alternative
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'
expect_in_file .uncle/workflow/plan-executability/assessment.json '"status": "SUPPORTED"'

new_stagegate_case stagegate-alternative
stagegate_agent
printf '\nR-1: DESIGN blanket denial, required property mediated access.\n' >> "$REPO/UPDATED_PROJECT_PLAN.md"
set_state WAIT_UPDATED_PLAN_APPROVAL
run_stagegate_stdin "$(gate_input y y y y n)" FAKE_ASSESS_NO_APPROVAL=1 FAKE_CAP_STATUS=UNSUPPORTED FAKE_IMPL='echo alternative > app/main.sh'
expect_status 0
expect_in_file app/main.sh alternative
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'

for family in change stagegate; do
    if [[ "$family" == change ]]; then
        new_case supported-change
        green_baseline 0 'bash app/test.sh'
    else
        new_stagegate_case supported-stagegate
        stagegate_agent
    fi
    set_state IMPLEMENT
    if [[ "$family" == change ]]; then
        run_driver FAKE_IMPL='echo supported > app/added.sh'
    else
        run_stagegate FAKE_IMPL='echo supported > app/added.sh'
    fi
    expect_status 0
    expect_state WAIT_IMPLEMENT_APPROVAL
    expect_in_file app/added.sh supported
    expect_file .uncle/workflow/approvals/PLAN_EXECUTABILITY.sha256

done

new_case authority-all-dependent
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_DECISION=1 FAKE_IMPL='echo forbidden > app/added.sh'
expect_status 1
expect_no_file app/added.sh
expect_out 'May the external retention limit change?'
run_driver FAKE_DECISION=1 FAKE_IMPL='echo forbidden > app/added.sh'
expect_status 1
expect_no_file app/added.sh
expect_out 'May the external retention limit change?'

new_case independent-authority
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_DECISION=1 FAKE_INDEPENDENT=1 FAKE_IMPL='echo helper > app/helper.sh; echo attempt >> .uncle/workflow/attempts'
expect_status 1
expect_in_file app/helper.sh helper
expect_no_file app/added.sh
run_driver FAKE_DECISION=1 FAKE_INDEPENDENT=1 FAKE_IMPL='echo replay >> .uncle/workflow/attempts'
expect_status 1
COUNT=$((COUNT+1))
[[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 1 ]] || fail 'independent subset replayed'

new_case stale-support
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL='echo supported > app/added.sh'
expect_status 0
set_state IMPLEMENT
printf '\n# changed adapter evidence\n' >> "$CASE/bin/fake-agent"
run_driver FAKE_ASSESS_NO_APPROVAL=1 FAKE_IMPL='echo replay > app/added.sh'
expect_in_file app/added.sh supported
expect_not_out 'Launching agent'


new_case live-verification-resume
green_baseline 0 'bash app/test.sh'
printf '| AC-2 | Live inference works | app/live-test.sh |\n' >> "$REPO/CHANGE_SPEC.md"
hash_file "$REPO/CHANGE_SPEC.md" > "$REPO/.uncle/workflow/approvals/CHANGE_SPEC.sha256"
printf '#!/bin/sh\ntest -f "%s"\n' "$CASE/auth-ready" > "$REPO/app/live-test.sh"
set_state IMPLEMENT
live_impl=$(cat <<'LIVE'
echo helper > app/added.sh
echo coding >> .uncle/workflow/attempts
cat > IMPLEMENTATION_NOTES.md <<'NOTES'
## Acceptance delivery
| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | app/added.sh | helper mock passes |
| AC-2 | INCOMPLETE | app/live-test.sh | missing auth |

```plan-blockers
[{"id":"B-1","class":"LIVE_VERIFICATION","requirement_ids":["AC-2"],"restriction_ids":[],"evidence":"auth unavailable","independent_work":"helper delivered"}]
```
NOTES
LIVE
)
run_driver FAKE_LIVE="$CASE/auth-ready" FAKE_IMPL="$live_impl"
expect_status 1
expect_in_file app/added.sh helper
expect_in_file IMPLEMENTATION_NOTES.md '| AC-2 | INCOMPLETE'
expect_no_file .uncle/workflow/implementation-completion-repair
run_driver FAKE_LIVE="$CASE/auth-ready" FAKE_IMPL='echo replay >> .uncle/workflow/attempts'
expect_status 1
expect_out 'prerequisite/evidence unchanged'
COUNT=$((COUNT+1))
[[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 1 ]] || fail 'live wait replayed coding'
printf 'available\n' > "$CASE/auth-ready"
verify_live=$(cat <<'VERIFY'
echo verify >> .uncle/workflow/live-attempts
if bash app/live-test.sh; then
    python3 - <<'PYCODE'
from pathlib import Path
p=Path('IMPLEMENTATION_NOTES.md')
p.write_text(p.read_text().split('```plan-blockers')[0].replace('INCOMPLETE', 'IMPLEMENTED').replace('missing auth', 'bash app/live-test.sh PASS'))
PYCODE
fi
VERIFY
)
run_driver FAKE_LIVE="$CASE/auth-ready" FAKE_VERIFY_LIVE="$verify_live" FAKE_IMPL='echo replay >> .uncle/workflow/attempts'
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
expect_in_file IMPLEMENTATION_NOTES.md '| AC-2 | IMPLEMENTED'
expect_no_file .uncle/workflow/implementation-completion-repair
COUNT=$((COUNT+1))
[[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 1 && $(wc -l < "$REPO/.uncle/workflow/live-attempts") -eq 1 ]] || fail 'live resume repeated a launch'


new_case implementation-design-contradiction
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
design_impl=$(cat <<'DESIGN'
echo retained > app/added.sh
echo attempt >> .uncle/workflow/attempts
if [[ ! -f .uncle/workflow/contradiction-reported ]]; then
    touch .uncle/workflow/contradiction-reported
    sed -i.bak 's/IMPLEMENTED/INCOMPLETE/' IMPLEMENTATION_NOTES.md
    rm IMPLEMENTATION_NOTES.md.bak
    cat >> IMPLEMENTATION_NOTES.md <<'BLOCK'
```plan-blockers
[{"id":"B-1","class":"DESIGN","requirement_ids":["AC-1"],"restriction_ids":[],"evidence":"runner rejects generated denial","independent_work":"helper retained"}]
```
BLOCK
fi
DESIGN
)
run_driver FAKE_IMPL="$design_impl"
expect_status 0
expect_state WAIT_PLAN_APPROVAL
expect_in_file app/added.sh retained
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'
expect_no_file .uncle/workflow/implementation-completion-repair
run_driver_stdin "$(gate_input y y y n)" FAKE_IMPL="$design_impl"
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
expect_in_file app/added.sh retained
COUNT=$((COUNT+1))
[[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 2 ]] || fail 'revised plan did not receive exactly one new implementation'

for independent in 0 1; do
    new_stagegate_case "stagegate-authority-$independent"
    stagegate_agent
    set_state IMPLEMENT
    if [[ "$independent" == 1 ]]; then
        run_stagegate FAKE_DECISION=1 FAKE_INDEPENDENT=1 FAKE_IMPL='echo helper > app/helper.sh; echo attempt >> .uncle/workflow/attempts'
        expect_in_file app/helper.sh helper
        run_stagegate FAKE_DECISION=1 FAKE_INDEPENDENT=1 FAKE_IMPL='echo replay >> .uncle/workflow/attempts'
        COUNT=$((COUNT+1))
        [[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 1 ]] || fail 'stagegate replayed independent steps'
    else
        run_stagegate FAKE_DECISION=1 FAKE_IMPL='echo forbidden > app/added.sh'
        expect_no_file app/added.sh
    fi
    expect_status 1
    expect_out 'May the external retention limit change?'
done


new_stagegate_case stagegate-default-repair-bound
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL FAKE_IMPL="printf '#!/bin/sh\necho changed\n' > app/main.sh"
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count 4
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count 4

new_stagegate_case incomplete-resume-retry
stagegate_agent
cat > "$REPO/REQUIREMENTS_INTERPRETATION.md" <<'SPEC'
## Acceptance criteria
| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Greeting works | bash app/test.sh |
SPEC
set_state IMPLEMENT
incomplete_impl=$(cat <<'IMPL'
echo attempt >> .uncle/workflow/attempts
cat > IMPLEMENTATION_NOTES.md <<'NOTES'
## Acceptance delivery
| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | INCOMPLETE | app/main.sh | missing check |
NOTES
IMPL
)
run_stagegate FAKE_IMPL="$incomplete_impl"
expect_status 1
expect_state IMPLEMENT
expect_out 'Implementation delivery is incomplete'
complete_impl=$(cat <<'IMPL'
echo attempt >> .uncle/workflow/attempts
echo fixed > app/main.sh
cat > IMPLEMENTATION_NOTES.md <<'NOTES'
## Acceptance delivery
| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | app/main.sh | bash app/test.sh PASS |
NOTES
IMPL
)
run_stagegate_stdin "$(gate_input y)" FAKE_IMPL="$complete_impl"
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
expect_in_file app/main.sh fixed
COUNT=$((COUNT+1))
[[ $(wc -l < "$REPO/.uncle/workflow/attempts") -eq 2 ]] || fail 'explicit resume retry did not run exactly once'

new_case references-and-approval-routing
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="python3 -B '$ROOT/scripts/tests/chat-test.py' -q ChatSafetyTests.test_provider_credentials_excluded_from_picker_and_payload ChatSafetyTests.test_rejects_escape_and_symlink_race ChatInteractionTests.test_menu_and_text_isolation > .uncle/workflow/security-check.log 2>&1 || exit; echo checked > app/added.sh"
expect_status 0
expect_in_file app/added.sh checked
expect_in_file .uncle/workflow/security-check.log 'Ran 3 tests'
expect_in_file .uncle/workflow/security-check.log OK

if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT plan recovery checks failed"; exit 1; fi
echo "$COUNT plan recovery checks passed"
