#!/usr/bin/env bash
# Exercise the real state loop with costly external stages replaced by probes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
mkdir -p .uncle/workflow .uncle/docs
export ROOT
cat > harness.sh <<'SH'
set -euo pipefail
. "$ROOT/scripts/lib/acceptance.sh"
. "$ROOT/scripts/lib/state.sh"
STATE_DIR=.uncle/workflow
STATE_FILE=.uncle/workflow/state
LOG_DIR="$STATE_DIR/logs"
DIFF_GATE=1
GREEN_CHECK=1
GREEN_CLASS=.uncle/workflow/green.tsv
GREEN_CMDS=.uncle/workflow/commands
GREEN_MD=.uncle/workflow/green.md
UNATTENDED=0
WORKFLOW_AUTO_REPAIR=1
WORKFLOW_AUTO_REPAIR_ATTEMPTS=1
WORKFLOW_CONTINUE_ON_TEST_FAILURE=0
. "$ROOT/scripts/lib/waivers.sh"
# ensure_acceptance_canonical/acceptance_json_ids live in the shared
# acceptance-gate lib (the stagegate/change-workflow consolidation moved them
# out of stagegate.sh itself), so the per-function awk extraction below never
# finds them there.
. "$ROOT/scripts/lib/acceptance-gate.sh"
for fn in get_state set_state require_file canonical_artifact_path record_nonblocking_failure has_nonblocking_failure green_failure_route; do
    eval "$(awk -v start="^${fn}\\(\\)" '$0 ~ start {active=1} active {print} active && /^}$/ {exit}' "$ROOT/scripts/stagegate.sh")"
done
unattended_prewarm_stage_for_state() { :; }
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
run_green_check() { echo green >> calls; }
# Real background verification (scripts/lib/background-verify.sh) is not
# under test here. Verification synchronization moved from a direct
# run_green_check call inside EXECUTE_CHECKLIST (never called that way any
# more) to awaiting the backgrounded result via green_wait_final; that is now
# the actual point in the real code where "was verification freshly done, or
# already available" is decided, so the call-count probe moved here with it.
green_wait_final() { echo green >> calls; return 0; }
run_green_check_auto() { :; }
green_failed_ids() { :; }
green_regressions() { cat "$GREEN_CLASS"; }
plan_delivery_summary() { :; }
plan_before_write() { :; }
plan_after_write() { :; }
repair_judge() { :; }
snapshot_checklist_checks() { :; }
snapshot_checklist_groups() { :; }
ensure_checklist_runner() { :; }
# Runtime-readiness routing (app-runnability, scaffold reconciliation) is a
# separate concern from this test's resume/malformed-report behavior; treat
# the application as always runnable so EXECUTE_CHECKLIST proceeds normally.
route_unrunnable_application() { return 0; }
# Starts a background plan/source-only investigation pass; per its own
# docstring it never opens a result file, so skipping it here is safe.
run_test_review_investigate() { :; }
# Only acts when UNATTENDED=1; this harness runs attended (UNATTENDED=0).
prewarm_checklist_browser() { :; }
run_stage() {
    echo "$1" >> calls
    case "$1" in
        TEST_REVIEW) printf 'Compacting report\n' > .uncle/docs/TEST_REVIEW.md ;;
        EXECUTE_CHECKLIST)
            # Stop an accidental loop quickly, without calling any real agent.
            # A malformed VERIFICATION_REPORT.md now gets one automatic
            # format-only retry (same shape as TEST_REVIEW.md's own), so two
            # calls in a row is expected; a third would be a real loop.
            [[ "$(grep -c '^EXECUTE_CHECKLIST$' calls)" -le 2 ]] || exit 8
            cp candidate.md .uncle/docs/VERIFICATION_REPORT.md
            printf 'No defects\n' > .uncle/docs/DEFECTS.md
            ;;
        FINAL_AUDIT|REPAIR) exit 0 ;;
        *) exit 7 ;;
    esac
}
eval "$(sed -n '/^while true; do/,$p' "$ROOT/scripts/stagegate.sh")"
SH
report() {
    printf '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n%s\n' "$1" > "$2"
}
reset() {
    printf '## MC-1\nExact action: check\nExpected result: greeting\n' > .uncle/docs/MANUAL_CHECKLIST.md
    rm -f calls invalid-inputs .uncle/workflow/repair-count .uncle/workflow/repair-source \
          .uncle/workflow/checklist-evidence-handoff-attempted .uncle/workflow/test-evidence-reconcile
    rm -rf .uncle/workflow/waivers
    printf 'EXECUTE_CHECKLIST\n' > .uncle/workflow/state
    printf 'snapshot\n' > .uncle/workflow/verification.manifest
    printf '0\n' > .uncle/workflow/green.tsv
    # EXECUTE_CHECKLIST now validates the canonical JSON mirror
    # (lib/checklist_document.py --validate-json), not the rendered
    # Markdown; keep both forms in sync the way manual-checklist panels do.
    # Every other canonical execution artifact must be cleared too: unlike
    # the Markdown-only era, VALIDATE_CHECKLIST only regenerates
    # EXECUTE_CHECKLIST.json when it is missing, so a stale one left over
    # from a previous scenario in this same run is read as real evidence
    # instead of being derived fresh from this scenario's candidate.md.
    rm -rf .uncle/workflow/documents
    mkdir -p .uncle/workflow/documents
    rm -f .uncle/workflow/execute-checklist-format-retry.md \
          .uncle/workflow/checklist-evidence-handoff-attempted \
          .uncle/workflow/test-evidence-reconcile
    printf '%s\n' '{"schema":"uncle.artifact/v1","kind":"manual-checklist","checks":[{"id":"MC-1","exact_action":"check","expected_result":"greeting","exclusive_resources":[],"depends_on":[]}]}' > .uncle/workflow/documents/MANUAL_CHECKLIST.json
    report $'| COVERAGE | YES | PASS | ok |\n| INTEGRITY | YES | PASS | ok |\n| ASSERTIONS | YES | PASS | ok |\n| ORACLE | YES | PASS | ok |\n| NEGATIVE | YES | PASS | ok |\n| RESULTS | YES | PASS | ok |' .uncle/docs/TEST_REVIEW.md
}
run() { local status=0; bash harness.sh > output 2>&1 || status=$?; if [[ "$status" != 0 ]]; then cat output >&2; fi; return "$status"; }
count() { [[ "$(grep -c "^$1$" calls)" == "$2" ]]; }

# A human-blocked report must reach audit after exactly one execution.
# green_wait_final is awaited at two real synchronization points -- once
# before EXECUTE_CHECKLIST runs, once again in FINAL_AUDIT -- but the
# background verification work itself (the expensive part) still runs
# exactly once; this is a wait/checkpoint count, not a rerun count.
reset
report '| MC-1 | YES | BLOCKED-HUMAN | awaiting Brian |' candidate.md
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1
count green 2

# Unsupported ID syntax pauses report validation. Multiple
# resumes and an in-place formatting correction must not rerun any checks
# beyond the one automatic format-only retry a malformed report now gets
# (the same shape as TEST_REVIEW.md's own retry) before this pauses for a
# person: two EXECUTE_CHECKLIST/green calls total for this scenario, not one,
# and no further ones on a later resume that changes nothing.
reset
report '| REQ-71 `:71` mutation validity | YES | PASS | mutant assertions passed |' candidate.md
if run; then echo 'Malformed report advanced' >&2; exit 1; fi
[[ "$(cat .uncle/workflow/state)" == VALIDATE_CHECKLIST ]]
grep -q 'not a plain identifier' output
if run; then echo 'Malformed report advanced on resume' >&2; exit 1; fi
count EXECUTE_CHECKLIST 2
count green 2

# Resuming report validation must still enforce protected input integrity,
# exercised here (the one scenario in this file that stays paused at
# VALIDATE_CHECKLIST across a resume) rather than against BLOCKED-SETUP below,
# which no longer pauses in postflight-only mode.
touch invalid-inputs
rc=0
run || rc=$?
[[ "$rc" == 9 ]]
count EXECUTE_CHECKLIST 2
rm -f invalid-inputs

report '| REQ-71 | YES | PASS | mutant assertions passed; :71 mutation validity |' .uncle/docs/VERIFICATION_REPORT.md
run
count EXECUTE_CHECKLIST 2
# +1 over the pre-correction count: FINAL_AUDIT is its own green_wait_final
# checkpoint, reached for the first time only once this scenario's report is
# finally valid.
count green 3
count FINAL_AUDIT 1

# Previously recorded waivers remain effective at the audit re-check too.
reset
report '| MC-1 | YES | BLOCKED-IMPOSSIBLE | unavailable platform |' candidate.md
mkdir -p .uncle/workflow/waivers
printf 'reason: operator accepted platform limit\n' > .uncle/workflow/waivers/MC-1
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1

# A checklist FAIL is a judged defect (not an ambiguous or unreviewed
# finding) and enters REPAIR even in the current default postflight-only
# mode -- restored by explicit operator decision after this round found
# postflight-only mode had silently relaxed it to "forwarded to audit as
# nonblocking evidence" along with every other non-PASS status. See the
# matching comment and fix in scripts/stagegate.sh's VALIDATE_CHECKLIST.
reset
report '| MC-1 | YES | FAIL | assertion failed |' candidate.md
run
count EXECUTE_CHECKLIST 1
count REPAIR 1

# BLOCKED-SETUP, BLOCKED-HUMAN, and BLOCKED-IMPOSSIBLE are judged-but-not-
# code-fixable outcomes, not format defects or FAILs -- that scoping was an
# explicit part of the same decision above. In postflight-only mode all
# three reach audit directly after one execution, the same shape as
# BLOCKED-HUMAN (first scenario) and BLOCKED-IMPOSSIBLE (above); none of them
# pause for a person the way they used to before postflight-only was the
# default (that pause-for-setup contract still holds in the legacy
# WORKFLOW_POSTFLIGHT_GREEN_CHECK=0 path, exercised by other suites).
reset
report '| MC-1 | YES | BLOCKED-SETUP | install browser |' candidate.md
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1

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
