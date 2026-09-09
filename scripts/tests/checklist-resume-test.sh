#!/usr/bin/env bash
# Exercise the real state loop with costly external stages replaced by probes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
mkdir -p workflow
export ROOT
cat > harness.sh <<'SH'
set -euo pipefail
. "$ROOT/scripts/lib/acceptance.sh"
STATE_DIR=workflow
STATE_FILE=workflow/state
DIFF_GATE=1
GREEN_CHECK=1
GREEN_CLASS=workflow/green.tsv
GREEN_MD=workflow/green.md
UNATTENDED=0
for fn in get_state set_state require_file waive_file waived_ids record_waiver write_waivers acceptance_setup_pause acceptance_human_continue acceptance_after_waiver acceptance_transition; do
    eval "$(awk -v start="^${fn}\\(\\)" '$0 ~ start {active=1} active {print} active && /^}$/ {exit}' "$ROOT/scripts/stagegate.sh")"
done
verify_implementation_review() { echo approval >> calls; }
verify_approval() { :; }
ensure_repair_capacity() { :; }
check_verification_inputs() {
    echo integrity >> calls
    [[ ! -e invalid-inputs ]] || exit 9
}
check_document_budget() { echo budget >> calls; }
run_green_check() { echo green >> calls; }
green_regressions() { cat "$GREEN_CLASS"; }
snapshot_checklist_checks() { :; }
snapshot_checklist_groups() { :; }
ensure_checklist_runner() { :; }
run_stage() {
    echo "$1" >> calls
    case "$1" in
        EXECUTE_CHECKLIST)
            # Stop an accidental loop quickly, without calling any real agent.
            [[ "$(grep -c '^EXECUTE_CHECKLIST$' calls)" == 1 ]] || exit 8
            cp candidate.md VERIFICATION_REPORT.md
            printf 'No defects\n' > DEFECTS.md
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
    rm -f calls invalid-inputs
    rm -rf workflow/waivers
    printf 'EXECUTE_CHECKLIST\n' > workflow/state
    printf 'snapshot\n' > workflow/verification.manifest
    printf '0\n' > workflow/green.tsv
    report $'| COVERAGE | YES | PASS | ok |\n| INTEGRITY | YES | PASS | ok |\n| ASSERTIONS | YES | PASS | ok |\n| ORACLE | YES | PASS | ok |\n| NEGATIVE | YES | PASS | ok |\n| RESULTS | YES | PASS | ok |' TEST_REVIEW.md
}
run() { bash harness.sh > output 2>&1; }
count() { [[ "$(grep -c "^$1$" calls)" == "$2" ]]; }

# A human-blocked report must reach audit after exactly one execution.
reset
report '| MC-1 | YES | BLOCKED-HUMAN | awaiting Brian |' candidate.md
run
count EXECUTE_CHECKLIST 1
count FINAL_AUDIT 1
count green 1

# The actual incident: a description in ID pauses report validation. Multiple
# resumes and an in-place formatting correction must not rerun any checks.
reset
report '| REQ-71 (`:71` mutation validity) | YES | PASS | mutant assertions passed |' candidate.md
if run; then echo 'Malformed report advanced' >&2; exit 1; fi
[[ "$(cat workflow/state)" == VALIDATE_CHECKLIST ]]
grep -q 'not a plain identifier' output
if run; then echo 'Malformed report advanced on resume' >&2; exit 1; fi
count EXECUTE_CHECKLIST 1
count green 1
report '| REQ-71 | YES | PASS | mutant assertions passed; :71 mutation validity |' VERIFICATION_REPORT.md
run
count EXECUTE_CHECKLIST 1
count green 1
count FINAL_AUDIT 1

# Previously recorded waivers remain effective at the audit re-check too.
reset
report '| MC-1 | YES | BLOCKED-IMPOSSIBLE | unavailable platform |' candidate.md
mkdir -p workflow/waivers
printf 'reason: operator accepted platform limit\n' > workflow/waivers/MC-1
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
[[ "$(cat workflow/state)" == VALIDATE_CHECKLIST ]]
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
printf '1\n' > workflow/green.tsv
report '| MC-1 | YES | PASS | agent says ok |' candidate.md
run
count REPAIR 1
[[ "$(cat workflow/repair-source)" == workflow/green.md ]]
echo 'checklist-resume-test.sh: one execution, durable validation, audit, blockers, repair, and integrity passed'
