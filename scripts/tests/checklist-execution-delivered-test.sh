#!/usr/bin/env bash
# EXECUTE_CHECKLIST used to run the stage once and move on unconditionally.
#
# A real run ended that stage after a single turn whose entire output was
# "Waiting for the batch run to finish." -- the checks were still running in
# the background. The driver went on, VALIDATE_CHECKLIST wrote its own
# placeholder, FINAL_AUDIT read that placeholder and returned NOT READY, and
# the background batch rewrote .uncle/docs/VERIFICATION_REPORT.md three
# minutes later, after the audit had bound the tree. Publication was then
# refused with "Reviewed files changed; rerun FINAL_AUDIT." and no PR existed.
#
# Two things have to be true for that not to recur: a report left over from an
# earlier attempt must not count as this attempt's delivery, and the driver's
# own fabricated record must never count as delivery at all.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

project="$work/project"
mkdir -p "$project/.uncle/docs" "$project/.uncle/workflow"
cd "$project"

fail() { echo "checklist-execution-delivered-test.sh: FAIL: $*" >&2; exit 1; }

cat > harness.sh <<'EOF'
set -uo pipefail
STATE_DIR=.uncle/workflow
EOF
awk '/^checklist_execution_delivered\(\)/{p=1} p{print} p && /^}$/{exit}' \
    "$ROOT/scripts/change-workflow.sh" >> harness.sh
cat >> harness.sh <<'EOF'
checklist_execution_delivered && echo DELIVERED || echo NOT_DELIVERED
EOF

verdict() { bash harness.sh; }

# 1. Nothing on disk.
[[ "$(verdict)" == NOT_DELIVERED ]] || fail 'an absent report counted as delivery'

# 2. The driver's own fabricated record. verification() stamps this heading on
#    every row set it invents; it is not evidence of anything being run.
printf '# Verification report\n\n## Driver-owned incomplete result\n\nThe execution stage did not produce a check-specific report.\n' \
    > .uncle/docs/VERIFICATION_REPORT.md
[[ "$(verdict)" == NOT_DELIVERED ]] || fail "the driver's own placeholder counted as delivery"

# 3. A real report, but left behind by an earlier attempt: it predates the
#    marker this attempt wrote before starting the stage.
printf '# Verification report\n\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | PASS | ran it |\n' \
    > .uncle/docs/VERIFICATION_REPORT.md
sleep 1
: > .uncle/workflow/execute-checklist.started
[[ "$(verdict)" == NOT_DELIVERED ]] || fail "an earlier attempt's report counted as this attempt's delivery"

# 4. A real report written by this attempt.
sleep 1
printf '# Verification report\n\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | PASS | ran it |\n' \
    > .uncle/docs/VERIFICATION_REPORT.md
[[ "$(verdict)" == DELIVERED ]] || fail 'a report written by this attempt was rejected'

# The stage must no longer walk straight from the runner into VALIDATE_CHECKLIST.
block="$(awk '/^        EXECUTE_CHECKLIST\)$/{p=1} p{print} p && /^        VALIDATE_CHECKLIST\)$/{exit}' \
    "$ROOT/scripts/change-workflow.sh")"
printf '%s\n' "$block" | grep -q 'checklist_execution_delivered' \
    || fail 'EXECUTE_CHECKLIST no longer checks that results were delivered'

echo 'checklist-execution-delivered-test.sh: only this attempt’s real report counts as delivered results'
