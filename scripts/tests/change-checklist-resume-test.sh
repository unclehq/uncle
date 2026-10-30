#!/usr/bin/env bash
# Exercise the actual change execution/validation cases without real agents or Git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ROOT
cd "$work"
cat > harness.sh <<'EOF'
set -euo pipefail
MODEL_EXECUTE=fake EFFORT_EXECUTE=low BUDGET_EXECUTE=1
STATE_DIR=.uncle/workflow
LOG_DIR=$STATE_DIR/logs
run_green_check() { echo green >> calls; }
# The checks now run beside the stage; the contract is that they are still
# started exactly once and their result is still collected exactly once.
start_green_check_bg() { run_green_check; }
wait_green_check_bg() { echo collected >> calls; }
plan_delivery_summary() { :; }
snapshot_checklist_groups() { :; }
snapshot_checklist_checks() { :; }
ensure_checklist_runner() { :; }
run_parallel_checklist_workers() { :; }
set_state() { echo "$1" > state; }
require_file() { test -s "$1"; }
# Inject a report-recovery failure at the durable validation boundary.
# Presentation budgets no longer gate canonical report validation.
recover_missing_checklist_reports() {
    test ! -e bad-report || return 1
    python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only
}
run_claude() {
    echo execute >> calls
    printf '# Verification report\n\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-001 | YES | PASS | greeting shown |\n' > .uncle/docs/VERIFICATION_REPORT.md
    echo defects > .uncle/docs/DEFECTS.md
    python3 - <<'PYTIME'
import os
marker = '.uncle/workflow/execute-checklist.started'
report = '.uncle/docs/VERIFICATION_REPORT.md'
os.utime(report, (os.stat(marker).st_mtime + 1, os.stat(marker).st_mtime + 1))
PYTIME
}
for fn in green_requires_implementation_repair checklist_execution_delivered; do
    eval "$(awk -v start="^${fn}\\(\\)" '$0 ~ start {active=1} active {print} active && /^}$/ {exit}' "$ROOT/scripts/change-workflow.sh")"
done
# Verification is started by the preceding stage and collected on checklist
# entry. Resuming VALIDATE_CHECKLIST must never start or collect it again.
[[ "$(cat state)" != EXECUTE_CHECKLIST ]] || start_green_check_bg
while true; do
    state=$(cat state)
    [[ "$state" != FINAL_AUDIT ]] || exit 0
    eval "$(sed -n '/^        EXECUTE_CHECKLIST)/,/^        FINAL_AUDIT)/p' "$ROOT/scripts/change-workflow.sh" | sed '$d' | { printf 'case "$state" in\n'; cat; printf 'esac\n'; })"
done
EOF
mkdir -p .uncle/docs .uncle/workflow/documents .uncle/workflow/logs
printf '%s\n' '{"schema":"uncle.artifact/v1","kind":"manual-checklist","checks":[{"id":"MC-001","exact_action":"check","expected_result":"greeting"}]}' > .uncle/workflow/documents/MANUAL_CHECKLIST.json
printf '## MC-001\nExact action: check\nExpected result: greeting\n' > .uncle/docs/MANUAL_CHECKLIST.md
echo EXECUTE_CHECKLIST > state
touch bad-report
if bash harness.sh; then exit 1; fi
[[ "$(cat state)" == VALIDATE_CHECKLIST ]]
if bash harness.sh; then exit 1; fi
[[ "$(grep -c '^execute$' calls)" == 1 ]]
[[ "$(grep -c '^green$' calls)" == 1 ]]
[[ "$(grep -c '^collected$' calls)" == 1 ]]
rm bad-report
bash harness.sh
[[ "$(cat state)" == FINAL_AUDIT ]]
[[ "$(grep -c '^execute$' calls)" == 1 ]]
# Every started check is collected: a background run must never be abandoned.
[[ "$(grep -c '^green$' calls)" == "$(grep -c '^collected$' calls)" ]]
echo 'change-checklist-resume-test: report retries do not repeat execution'
