#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
STATE_DIR="$work/workflow"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"
GREEN_CMDS="$STATE_DIR/commands"
GREEN_CUR="$STATE_DIR/current"
GREEN_CHECK=1
printf 'bash tests/browser.sh\n' > "$GREEN_CMDS"
printf '0\tbash tests/browser.sh\n' > "$GREEN_CUR"
printf 'PASS browser assertions\n' > "$LOG_DIR/green-check.log"
snapshot_checklist_checks
cmp "$GREEN_CUR" "$STATE_DIR/checklist-driver-checks/results.tsv"
cmp "$LOG_DIR/green-check.log" "$STATE_DIR/checklist-driver-checks/output.log"
printf '1\tbash tests/browser.sh\n' > "$GREEN_CUR"
printf 'FAIL focus assertion\n' > "$LOG_DIR/green-check.log"
snapshot_checklist_checks
grep -q '^1' "$STATE_DIR/checklist-driver-checks/results.tsv"
grep -q 'FAIL focus' "$STATE_DIR/checklist-driver-checks/output.log"
GREEN_CHECK=0
snapshot_checklist_checks
grep -q 'NOT RUN' "$STATE_DIR/checklist-driver-checks/README.md"
[[ ! -e "$STATE_DIR/checklist-driver-checks/results.tsv" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ ! -e "$STATE_DIR/checklist-driver-checks/output.log" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
GREEN_CHECK=1
: > "$GREEN_CMDS"
snapshot_checklist_checks
grep -q 'NOT RUN' "$STATE_DIR/checklist-driver-checks/README.md"
echo 'checklist-driver-checks-test.sh: fresh success/failure evidence and stale-evidence removal passed'
