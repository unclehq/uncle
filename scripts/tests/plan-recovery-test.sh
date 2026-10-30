#!/usr/bin/env bash
set -uo pipefail
# This suite exercises the explicitly requested standalone assessment mode.
export WORKFLOW_EXECUTABILITY_REVIEW=1
UNCLE_TEST_FIXTURES_ONLY=1 source "$(dirname "$0")/gates-test.sh"

new_case unsupported-denial
set_state WAIT_UPDATED_PLAN_APPROVAL
green_baseline 0 'bash app/test.sh'
printf '\nRestriction R-1: DESIGN blanket tool denial; property mediated access.\n' >> "$REPO/.uncle/docs/CHANGE_PLAN.md"
hash_canonical CHANGE_PLAN > "$REPO/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
printf 'AR-001: blanket denial is unsupported by this runner.\n' > "$REPO/.uncle/docs/ADVERSARIAL_REVIEW.md"
run_driver FAKE_ASSESS_NO_APPROVAL=1 FAKE_CAP_STATUS=UNSUPPORTED FAKE_IMPL='echo unsafe-launch > app/added.sh'
expect_no_file app/added.sh
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'
expect_in_file .uncle/docs/CHANGE_PLAN.md 'isolated-context revision'

# Generated briefs live under .uncle/docs. Plan recovery must still recognize
# this as the change workflow and assess .uncle/docs/CHANGE_PLAN.md, never ask for the
# app-only .uncle/docs/UPDATED_PROJECT_PLAN.md.
new_case generated-change-brief
mkdir -p "$REPO/.uncle/docs"
mv "$REPO/CHANGE_REQUEST.md" "$REPO/.uncle/docs/CHANGE_REQUEST.md"
set_state WAIT_UPDATED_PLAN_APPROVAL
green_baseline 0 'bash app/test.sh'
run_driver FAKE_ASSESS_NO_APPROVAL=1 FAKE_CAP_STATUS=UNSUPPORTED FAKE_IMPL='echo unsafe-launch > app/generated-brief.sh'
expect_no_file app/generated-brief.sh
expect_not_out 'Missing canonical plan review input: .uncle/docs/UPDATED_PROJECT_PLAN.md'
expect_in_file .uncle/workflow/plan-recovery.json '"design_count": 1'


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
cp "$REPO/.uncle/docs/UPDATED_PROJECT_PLAN.md" "$REPO/.uncle/docs/PROJECT_PLAN.md"
sync_canonical PROJECT_PLAN
printf '\nR-1: DESIGN blanket denial, required property mediated access.\n' >> "$REPO/.uncle/docs/UPDATED_PROJECT_PLAN.md"
hash_canonical UPDATED_PROJECT_PLAN > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
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
jq '.acceptance_criteria += [{id:"AC-2",criterion:"Live inference works",verification:"app/live-test.sh"}]' \
    "$REPO/.uncle/workflow/documents/CHANGE_SPEC.json" > "$CASE/spec.json"
mv "$CASE/spec.json" "$REPO/.uncle/workflow/documents/CHANGE_SPEC.json"
hash_file "$REPO/.uncle/workflow/documents/CHANGE_SPEC.json" > "$REPO/.uncle/workflow/approvals/CHANGE_SPEC.sha256"
printf '#!/bin/sh\ntest -f "%s"\n' "$CASE/auth-ready" > "$REPO/app/live-test.sh"
set_state IMPLEMENT
live_impl=$(cat <<'LIVE'
echo helper > app/added.sh
echo coding >> .uncle/workflow/attempts
cat > .uncle/workflow/documents/IMPLEMENTATION_NOTES.json <<'NOTES'
{"schema":"uncle.artifact/v1","kind":"implementation-notes",
 "deliveries":[
   {"id":"AC-1","status":"IMPLEMENTED","changed_code":"app/added.sh","observed_verification":"helper mock passes"},
   {"id":"AC-2","status":"INCOMPLETE","changed_code":"app/live-test.sh","observed_verification":"missing auth"}],
 "plan_blockers":[{"id":"B-1","class":"LIVE_VERIFICATION","requirement_ids":["AC-2"],"restriction_ids":[],"evidence":"auth unavailable","independent_work":"helper delivered"}]}
NOTES
LIVE
)
run_driver FAKE_LIVE="$CASE/auth-ready" FAKE_IMPL="$live_impl"
expect_status 1
expect_in_file app/added.sh helper
COUNT=$((COUNT+1))
jq -e '[ .. | objects | select(.id? == "AC-2") | .status ] == ["INCOMPLETE"]' \
    "$REPO/.uncle/workflow/documents/IMPLEMENTATION_NOTES.json" >/dev/null || fail 'AC-2 must be INCOMPLETE'
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
import json
p=Path('.uncle/workflow/documents/IMPLEMENTATION_NOTES.json')
data=json.loads(p.read_text())
data['deliveries'][1].update(status='IMPLEMENTED', observed_verification='bash app/live-test.sh PASS')
data['plan_blockers']=[]
p.write_text(json.dumps(data))
PYCODE
fi
VERIFY
)
run_driver FAKE_LIVE="$CASE/auth-ready" FAKE_VERIFY_LIVE="$verify_live" FAKE_IMPL='echo replay >> .uncle/workflow/attempts'
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
COUNT=$((COUNT+1))
jq -e '[ .. | objects | select(.id? == "AC-2") | .status ] == ["IMPLEMENTED"]' \
    "$REPO/.uncle/workflow/documents/IMPLEMENTATION_NOTES.json" >/dev/null || fail 'AC-2 must be IMPLEMENTED'
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
    python3 - <<'BLOCK'
import json
from pathlib import Path
p = Path('.uncle/workflow/documents/IMPLEMENTATION_NOTES.json')
data = json.loads(p.read_text())
data['deliveries'][0]['status'] = 'INCOMPLETE'
data['plan_blockers'] = [{"id":"B-1","class":"DESIGN","requirement_ids":["AC-1"],"restriction_ids":[],"evidence":"runner rejects generated denial","independent_work":"helper retained"}]
p.write_text(json.dumps(data))
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


# Keep the configured four-attempt bound independent of attended defaults.
new_stagegate_case stagegate-repair-bound
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_MAX_REPAIRS=4 WORKFLOW_CONTINUE_ON_TEST_FAILURE=0 WORKFLOW_AUTO_REPAIR_ATTEMPTS=4 WORKFLOW_TEST_REVIEW_PANEL=0 WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL FAKE_IMPL="printf '#!/bin/sh\necho changed\n' > app/main.sh"
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count 4
run_stagegate WORKFLOW_MAX_REPAIRS=4 WORKFLOW_CONTINUE_ON_TEST_FAILURE=0 WORKFLOW_AUTO_REPAIR_ATTEMPTS=4 WORKFLOW_TEST_REVIEW_PANEL=0 WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count 4

new_stagegate_case incomplete-resume-retry
stagegate_agent
cat > "$REPO/.uncle/docs/REQUIREMENTS_INTERPRETATION.md" <<'SPEC'
## Acceptance criteria
| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Greeting works | bash app/test.sh |
SPEC
set_state IMPLEMENT
incomplete_impl=$(cat <<'IMPL'
echo attempt >> .uncle/workflow/attempts
cat > .uncle/workflow/documents/IMPLEMENTATION_NOTES.json <<'NOTES'
{"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [{"id": "AC-1", "status": "INCOMPLETE", "changed_code": "app/main.sh", "observed_verification": "missing check"}]}
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
cat > .uncle/workflow/documents/IMPLEMENTATION_NOTES.json <<'NOTES'
{"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [{"id": "AC-1", "status": "IMPLEMENTED", "changed_code": "app/main.sh", "observed_verification": "bash app/test.sh PASS"}]}
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
# Exercise the unchanged exclusion assertions with a virtual credential file:
# no credential-named file may be created or opened, even as a test canary.
cat > "$CASE/chat-safety.py" <<'CHAT'
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

names = {'self-hosted-keys.json', '.uncle-self-hosted-keys.json'}
virtual = {}
real_write, real_walk, real_open = Path.write_text, os.walk, os.open

def write(path, text, *args, **kwargs):
    if path.name in names:
        virtual.setdefault(path.parent.resolve(), set()).add(path.name)
        return len(text)
    return real_write(path, text, *args, **kwargs)

def walk(top, *args, **kwargs):
    for base, dirs, files in real_walk(top, *args, **kwargs):
        yield base, dirs, files + sorted(virtual.get(Path(base).resolve(), ()))

def guarded_open(path, *args, **kwargs):
    if Path(os.fsdecode(path)).name in names:
        raise AssertionError('credential exclusion must happen before opening a file')
    return real_open(path, *args, **kwargs)

script = sys.argv.pop(1)
sys.argv[0] = script
with patch.object(Path, 'write_text', write), patch.object(os, 'walk', walk), patch.object(os, 'open', guarded_open):
    runpy.run_path(script, run_name='__main__')
CHAT
run_driver FAKE_IMPL="python3 -B '$CASE/chat-safety.py' '$ROOT/scripts/tests/chat-test.py' -q ChatSafetyTests.test_provider_credentials_excluded_from_picker_and_payload ChatSafetyTests.test_rejects_escape_and_symlink_race ChatInteractionTests.test_menu_and_text_isolation > .uncle/workflow/security-check.log 2>&1 || exit; echo checked > app/added.sh"
expect_status 0
expect_in_file app/added.sh checked
expect_in_file .uncle/workflow/security-check.log 'Ran 3 tests'
expect_in_file .uncle/workflow/security-check.log OK

# Darwin may report EPERM for a reaped, empty process group. It must not
# replace the workflow's exit code, or treat a live/inaccessible group as gone.
CASE_NAME=process-group-cleanup
COUNT=$((COUNT+1))
python3 - "$ROOT" <<'PYLOCK' || fail 'process-group cleanup contract failed'
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts/lib'))
spec = importlib.util.spec_from_file_location('executability', Path(sys.argv[1]) / 'scripts/lib/plan-executability.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
with patch.object(mod.os, 'kill', side_effect=PermissionError), patch.object(mod.sys, 'platform', 'darwin'):
    with patch.object(mod.subprocess, 'check_output', return_value='456\n789\n'):
        assert not mod.alive(-123)
        assert mod.alive(123)
    with patch.object(mod.subprocess, 'check_output', return_value='123\n'):
        assert mod.alive(-123)
    with patch.object(mod.subprocess, 'check_output', side_effect=OSError):
        assert mod.alive(-123)
    with patch.object(mod.sys, 'platform', 'linux'):
        assert mod.alive(-123)
with tempfile.TemporaryDirectory() as directory:
    os.chdir(directory)
    with patch.object(mod.os, 'killpg', side_effect=PermissionError), patch.object(mod, 'alive', return_value=False):
        assert mod._lock_run_once(['bash', '-c', 'exit 7']) == 7
    assert json.loads((mod.STATE / 'driver.lock').read_text())['pgid'] is None
    with patch.object(mod.os, 'killpg', side_effect=PermissionError), patch.object(mod, 'alive', return_value=True):
        try:
            mod._lock_run_once(['bash', '-c', 'exit 7'])
        except PermissionError:
            pass
        else:
            raise AssertionError('permission failure for a live group was swallowed')
PYLOCK

if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT plan recovery checks failed"; exit 1; fi
echo "$COUNT plan recovery checks passed"
