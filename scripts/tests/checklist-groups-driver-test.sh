#!/usr/bin/env bash
# The driver hands the checklist stage its execution plan, or tells it plainly
# that there is no plan. Never a third thing: an absent, unreadable, or
# contradictory checklist has to end in "run one at a time", and none of those
# may stop the run — the checklist is the verification, and a formatting fault
# in a declaration is not a reason to skip verifying the product.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/proj"
cd "$work/proj"
STATE_DIR="workflow"
DIR="$STATE_DIR/checklist-groups"
mkdir -p "$STATE_DIR"

check() {
    printf '\n### %s\n- Priority: Critical\n- Exclusive resources: %s\n- Depends on: %s\n- Exact action: run it\n' \
        "$1" "$2" "$3"
}

# --- a checklist that declared its resources ---------------------------------
{
    echo '# Manual checklist'
    check MC-001 none none
    check MC-002 none none
    check MC-003 port:5173 none
    check MC-004 port:5173 MC-003
} > MANUAL_CHECKLIST.md

out="$(snapshot_checklist_groups)"
[[ -s "$DIR/groups.txt" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ "$(cat "$DIR/groups.txt")" == "MC-001 MC-002 MC-003
MC-004" ]]
grep -q 'group(s) from' <<< "$out"
grep -q 'before starting the next' "$DIR/README.md"

# --- a declaration that cannot be scheduled ----------------------------------
# Non-fatal by design: under `set -e` this must not take the driver down.
{
    echo '# Manual checklist'
    check MC-001 none MC-404
} > MANUAL_CHECKLIST.md
status=0
out="$(snapshot_checklist_groups)" || status=$?
[[ "$status" == 0 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ ! -e "$DIR/groups.txt" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
grep -q 'NOT DECLARED' "$DIR/README.md"
grep -q 'MC-404' "$DIR/README.md"
grep -q 'one check at a time' <<< "$out"

# --- a stale plan is never left readable -------------------------------------
printf 'MC-900 MC-901\n' > "$DIR/groups.txt"
{
    echo '# Manual checklist'
    printf '\n### MC-001\n- Exact action: run it\n'
} > MANUAL_CHECKLIST.md
snapshot_checklist_groups > /dev/null
[[ "$(cat "$DIR/groups.txt")" == "MC-001" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
grep -q 'scheduled alone' "$DIR/README.md"

# --- no checklist at all -----------------------------------------------------
rm -f MANUAL_CHECKLIST.md
printf 'MC-900 MC-901\n' > "$DIR/groups.txt"
status=0
snapshot_checklist_groups > /dev/null || status=$?
[[ "$status" == 0 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ ! -e "$DIR/groups.txt" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
grep -q 'NOT DECLARED' "$DIR/README.md"

# --- the deriver cannot run at all -------------------------------------------
# No python3, or a checkout without the helper. The stage still has to be told
# there is no plan, and a previous run's plan must not survive to be read as
# this run's: that file is the only thing standing between "no grouping" and
# a grouping for a checklist nobody derived.
{
    echo '# Manual checklist'
    check MC-001 none none
    check MC-002 none none
} > MANUAL_CHECKLIST.md
printf 'MC-900 MC-901\n' > "$DIR/groups.txt"
status=0
( GATES_LIB_DIR="$work/nowhere"; snapshot_checklist_groups > /dev/null ) || status=$?
[[ "$status" == 0 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ ! -e "$DIR/groups.txt" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
grep -q 'NOT DECLARED' "$DIR/README.md"

# --- the prompt and the driver agree on where the plan lives -----------------
grep -q '\.uncle/workflow/checklist-groups/README\.md' "$ROOT/prompts/execute-checklist.md"
grep -q '\.uncle/workflow/checklist-groups/README\.md' "$ROOT/prompts/change/execute-change-checklist.md"

echo 'checklist-groups-driver-test.sh: plan written, bad declarations and a missing deriver degrade to serial, stale plans removed'
