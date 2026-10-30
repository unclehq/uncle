#!/usr/bin/env bash
# Exercise the real state loop with costly external stages replaced by probes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
mkdir -p .uncle/workflow/logs .uncle/workflow/documents .uncle/docs
export ROOT
cat > harness.sh <<'SH'
set -euo pipefail
. "$ROOT/scripts/lib/acceptance.sh"
. "$ROOT/scripts/lib/state.sh"
STATE_DIR=.uncle/workflow
STATE_FILE=.uncle/workflow/state
DIFF_GATE=1
GREEN_CHECK=1
GREEN_CLASS=.uncle/workflow/green.tsv
GREEN_CMDS=.uncle/workflow/commands
GREEN_MD=.uncle/workflow/green.md
UNATTENDED=0
LOG_DIR=$STATE_DIR/logs
WORKFLOW_POSTFLIGHT_GREEN_CHECK=0
WORKFLOW_CONTINUE_ON_TEST_FAILURE=0
WORKFLOW_AUTO_REPAIR_ATTEMPTS=1
. "$ROOT/scripts/lib/gates.sh"
. "$ROOT/scripts/lib/triage.sh"
. "$ROOT/scripts/lib/waivers.sh"
for fn in get_state set_state require_file canonical_artifact_path ensure_acceptance_canonical acceptance_json_ids unattended_prewarm_stage_for_state acceptance_setup_pause acceptance_human_continue acceptance_after_waiver acceptance_transition continue_nonblocking_test_review green_failure_route; do
    eval "$(awk -v start="^${fn}\\(\\)" '$0 ~ start {active=1} active {print} active && /^}$/ {exit}' "$ROOT/scripts/stagegate.sh")"
done
supervision_validation_failed() { :; }
preserve_requirements_source() { :; }
verify_implementation_review() { echo approval >> calls; }
verify_approval() { :; }
ensure_repair_capacity() { :; }
plan_executability_enabled() { return 1; }
repair_begin() { :; }
check_verification_inputs() {
    echo integrity >> calls
    [[ ! -e invalid-inputs ]] || exit 9
}
check_document_budget() { echo budget >> calls; }
# The verifier starts before checklist execution. Waiting or visiting audit
# reuses that result; a format retry must not rerun the verifier either.
green_wait_final() {
    if [[ ! -e "$STATE_DIR/green-collected" ]]; then
        echo green >> calls
        touch "$STATE_DIR/green-collected"
    fi
}
run_green_check_auto() { :; }
route_unrunnable_application() { return 0; }
run_test_review_investigate() { :; }
prewarm_checklist_browser() { :; }
green_failed_ids() { :; }
green_regressions() { cat "$GREEN_CLASS"; }
plan_delivery_summary() { :; }
plan_before_write() { :; }
snapshot_checklist_checks() { :; }
snapshot_checklist_groups() { :; }
ensure_checklist_runner() { :; }
run_stage() {
    echo "$1" >> calls
    case "$1" in
        TEST_REVIEW)
            printf 'Compacting report\n' > .uncle/docs/TEST_REVIEW.md
            rm -f "$STATE_DIR/documents/TEST_REVIEW.json"
            ;;
        EXECUTE_CHECKLIST)
            # Stop an accidental loop quickly, without calling any real agent.
            # A malformed VERIFICATION_REPORT.md now gets one automatic
            # format-only retry (same shape as TEST_REVIEW.md's own), so two
            # calls in a row is expected; a third would be a real loop.
            [[ "$(grep -c '^EXECUTE_CHECKLIST$' calls)" -le 2 ]] || exit 8
            cp candidate.md .uncle/docs/VERIFICATION_REPORT.md
            printf 'No defects\n' > .uncle/docs/DEFECTS.md
            python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only
            ;;
        FINAL_AUDIT) exit 0 ;;
        *) exit 7 ;;
    esac
}
# Stop at the repair boundary: this suite checks routing, not repair agents.
eval "$(sed -n '/^while true; do/,$p' "$ROOT/scripts/stagegate.sh" | sed '/^    state="$(get_state)"/a\
    if [[ "$state" == REPAIR ]]; then echo REPAIR >> calls; exit 0; fi
'
)"
SH
report() {
    printf '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n%s\n' "$1" > "$2"
}
reset() {
    printf '## MC-1\nExact action: check\nExpected result: greeting\n' > .uncle/docs/MANUAL_CHECKLIST.md
    rm -f calls invalid-inputs
    rm -rf .uncle/workflow/waivers .uncle/workflow/documents
    rm -f .uncle/workflow/*-format-retry.md .uncle/workflow/green-collected
    mkdir -p .uncle/workflow/documents
    printf '%s\n' '{"schema":"uncle.artifact/v1","kind":"manual-checklist","checks":[{"id":"MC-1","exact_action":"check","expected_result":"greeting"}]}' > .uncle/workflow/documents/MANUAL_CHECKLIST.json
    printf 'EXECUTE_CHECKLIST\n' > .uncle/workflow/state
    printf 'snapshot\n' > .uncle/workflow/verification.manifest
    printf '0\n' > .uncle/workflow/green.tsv
    report $'| COVERAGE | YES | PASS | ok |\n| INTEGRITY | YES | PASS | ok |\n| ASSERTIONS | YES | PASS | ok |\n| ORACLE | YES | PASS | ok |\n| NEGATIVE | YES | PASS | ok |\n| RESULTS | YES | PASS | ok |' .uncle/docs/TEST_REVIEW.md
    python3 "$ROOT/scripts/lib/acceptance_context.py" --export-json .uncle/docs/TEST_REVIEW.md . TEST_REVIEW
}
run() { local status=0; bash harness.sh > output 2>&1 || status=$?; if [[ "$status" != 0 ]]; then cat output >&2; fi; return "$status"; }
count() { [[ "$(grep -c "^$1$" calls)" == "$2" ]]; }

# A human-blocked report must reach audit after exactly one execution.
reset
report '| MC-1 | YES | BLOCKED-HUMAN | awaiting Brian |' candidate.md
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1
count green 1

# Unsupported ID syntax pauses report validation. Multiple
# resumes and an in-place formatting correction must not rerun any checks
# beyond the one automatic format-only retry a malformed report now gets
# (the same shape as TEST_REVIEW.md's own retry) before this pauses for a
# person: two EXECUTE_CHECKLIST calls but only one collected green result,
# and no further ones on a later resume that changes nothing.
reset
report '| REQ-71 `:71` mutation validity | YES | PASS | mutant assertions passed |' candidate.md
if run; then echo 'Malformed report advanced' >&2; exit 1; fi
[[ "$(cat .uncle/workflow/state)" == VALIDATE_CHECKLIST ]]
grep -q 'not a plain identifier' output
if run; then echo 'Malformed report advanced on resume' >&2; exit 1; fi
count EXECUTE_CHECKLIST 2
count green 1
report '| REQ-71 | YES | PASS | mutant assertions passed; :71 mutation validity |' .uncle/docs/VERIFICATION_REPORT.md
python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only
run
count EXECUTE_CHECKLIST 2
count green 1
count FINAL_AUDIT 1

# Previously recorded waivers remain effective at the audit re-check too.
reset
report '| MC-1 | YES | BLOCKED-IMPOSSIBLE | unavailable platform |' candidate.md
mkdir -p .uncle/workflow/waivers
printf 'reason: operator accepted platform limit\n' > .uncle/workflow/waivers/MC-1
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1

# Defects still enter repair, and setup still pauses rather than passing.
reset
report '| MC-1 | YES | FAIL | assertion failed |' candidate.md
run
count EXECUTE_CHECKLIST 1
count REPAIR 1
reset
report '| MC-1 | YES | BLOCKED-SETUP | install browser |' candidate.md
if run; then echo 'Setup blocker advanced' >&2; exit 1; fi
[[ "$(cat .uncle/workflow/state)" == VALIDATE_CHECKLIST ]]
if run; then echo 'Setup blocker advanced on resume' >&2; exit 1; fi
count EXECUTE_CHECKLIST 1

# Resuming report validation must still enforce protected input integrity.
touch invalid-inputs
rc=0
run || rc=$?
[[ "$rc" == 9 ]]
count EXECUTE_CHECKLIST 1

# Fresh driver failures cannot be laundered by a passing agent report.
reset
printf '1\n' > .uncle/workflow/green.tsv
report '| MC-1 | YES | PASS | agent says ok |' candidate.md
run
count REPAIR 1
[[ "$(cat .uncle/workflow/repair-source)" == .uncle/workflow/green.md ]]
# A malformed saved review must not replay the reviewer beyond the one
# automatic format-only retry it now gets (two TEST_REVIEW calls total for
# this scenario), and a later resume that changes nothing must not replay it
# again.
reset
printf 'TEST_REVIEW\n' > .uncle/workflow/state
rm -f .uncle/workflow/documents/TEST_REVIEW.json
if run; then echo 'Malformed test review advanced' >&2; exit 1; fi
[[ "$(cat .uncle/workflow/state)" == VALIDATE_TEST_REVIEW ]]
count TEST_REVIEW 2
if run; then echo 'Malformed saved review advanced' >&2; exit 1; fi
count TEST_REVIEW 2
touch invalid-inputs
rc=0; run || rc=$?
[[ "$rc" == 9 ]]
count TEST_REVIEW 2
echo 'checklist-resume-test.sh: one execution, durable validation, audit, blockers, repair, and integrity passed'
