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
run_green_check() { echo green >> calls; }
plan_delivery_summary() { :; }
snapshot_checklist_groups() { :; }
snapshot_checklist_checks() { :; }
ensure_checklist_runner() { :; }
set_state() { echo "$1" > state; }
require_file() { test -s "$1"; }
check_document_budget() { test ! -e bad-report; }
run_claude() {
    echo execute >> calls
    echo report > VERIFICATION_REPORT.md
    echo defects > DEFECTS.md
}
while true; do
    state=$(cat state)
    [[ "$state" != FINAL_AUDIT ]] || exit 0
    eval "$(sed -n '/^        EXECUTE_CHECKLIST)/,/^        FINAL_AUDIT)/p' "$ROOT/scripts/change-workflow.sh" | sed '$d' | { printf 'case "$state" in\n'; cat; printf 'esac\n'; })"
done
EOF
echo MC-001 > MANUAL_CHECKLIST.md
echo EXECUTE_CHECKLIST > state
touch bad-report
if bash harness.sh; then exit 1; fi
[[ "$(cat state)" == VALIDATE_CHECKLIST ]]
if bash harness.sh; then exit 1; fi
[[ "$(grep -c '^execute$' calls)" == 1 ]]
[[ "$(grep -c '^green$' calls)" == 1 ]]
rm bad-report
bash harness.sh
[[ "$(cat state)" == FINAL_AUDIT ]]
[[ "$(grep -c '^execute$' calls)" == 1 ]]
echo 'change-checklist-resume-test: report retries do not repeat execution'
