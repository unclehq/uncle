#!/usr/bin/env bash
# The CHECKLIST state has one successor: VALIDATE_MANUAL_CHECKLIST, which
# validates and renders the checklist and then hands on to EXECUTE_CHECKLIST,
# where the checks are actually run.
#
# The delta panel's fast path saves only the parent synthesis model call, but
# it used to `set_state VALIDATE_CHECKLIST` -- two states further on. That
# skipped VALIDATE_MANUAL_CHECKLIST and EXECUTE_CHECKLIST entirely: the
# checklist was written and never executed, .uncle/workflow/checklist-groups/
# was never created, no execute-checklist log or cost row ever appeared, and
# VALIDATE_CHECKLIST's recovery wrote every row as "NOT RUN -- No
# check-specific execution evidence was recorded." The final audit then read
# those rows and returned NOT READY on a verification never attempted.
#
# Both exits from CHECKLIST must name the same successor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
driver="$ROOT/scripts/change-workflow.sh"

fail() { echo "checklist-delta-successor-test.sh: FAIL: $*" >&2; exit 1; }

# The CHECKLIST state body, from its label to the next state label.
body="$(awk '/^        CHECKLIST\)$/{p=1} p{print} p && /^        VALIDATE_MANUAL_CHECKLIST\)$/ && !/^        CHECKLIST\)$/{exit}' "$driver")"
[[ -n "$body" ]] || fail 'could not isolate the CHECKLIST state body'

# Every set_state inside CHECKLIST, excluding the next label the awk consumed.
targets="$(printf '%s\n' "$body" | grep -oE 'set_state [A-Z_]+' | awk '{print $2}' | sort -u)"
[[ -n "$targets" ]] || fail 'CHECKLIST sets no state at all'

while read -r target; do
    [[ -n "$target" ]] || continue
    [[ "$target" == VALIDATE_MANUAL_CHECKLIST ]] \
        || fail "CHECKLIST hands on to $target; the checklist would never be executed"
done <<< "$targets"

# The fast path must still be there: this test is about where it goes, not
# about removing it.
printf '%s\n' "$body" | grep -q 'CHECKLIST_PANEL_DIRECT' \
    || fail 'the delta fast path vanished; this test no longer covers it'

# And the chain it rejoins must still lead to execution.
awk '/^        VALIDATE_MANUAL_CHECKLIST\)$/{p=1} p{print} p && /^        EXECUTE_CHECKLIST\)$/{exit}' "$driver" \
    | grep -q 'set_state EXECUTE_CHECKLIST' \
    || fail 'VALIDATE_MANUAL_CHECKLIST no longer hands on to EXECUTE_CHECKLIST'

echo 'checklist-delta-successor-test.sh: both exits from CHECKLIST reach the execution stage'
