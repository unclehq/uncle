#!/usr/bin/env bash
set -euo pipefail

# A checklist failure that no automatic repair is left for. Run 6 spent both repairs on early driver failures, then failed a checklist
# row on a plan that contradicted itself (a 13-character literal in a 12-character display), and stopped "for an explicit owner
# decision" with nobody there. A driver or test-review failure in that position already continued to the final audit; this makes the
# checklist case match it, for unattended runs only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FAILED=0
COUNT=0
check_eq() {
    COUNT=$((COUNT + 1))
    [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }
}
verdict() { if checklist_failure_continues "$@"; then printf continue; else printf stop; fi; }

FUNC="$(ROOT="$ROOT" python3 -B - <<'PY'
import os, re
from pathlib import Path
source = (Path(os.environ["ROOT"]) / "scripts" / "stagegate.sh").read_text()
print(re.search(r"^checklist_failure_continues\(\) \{.*?^}", source, re.M | re.S).group(0))
PY
)"
eval "$FUNC"

# source, continue-on-failure, unattended, repairs used, attempts
check_eq "unattended, repairs spent: the audit reads it" continue "$(verdict checklist-fail 1 1 2 2)"
check_eq "unattended, more used than allowed: the audit reads it" continue "$(verdict checklist-fail 1 1 3 2)"
check_eq "a repair is still available: not this route" stop "$(verdict checklist-fail 1 1 1 2)"
check_eq "no repair used yet: not this route" stop "$(verdict checklist-fail 1 1 0 2)"
check_eq "attended: a person is there, so it still stops" stop "$(verdict checklist-fail 1 0 2 2)"
check_eq "continuing on failure is off: it still stops" stop "$(verdict checklist-fail 0 1 2 2)"
check_eq "automatic repair is off (zero attempts): it still stops" stop "$(verdict checklist-fail 1 1 0 0)"
check_eq "a final-audit failure is not a checklist failure" stop "$(verdict .uncle/docs/FINAL_AUDIT.md 1 1 2 2)"
check_eq "a driver verification failure has its own route" stop "$(verdict .uncle/workflow/green-check.md 1 1 2 2)"
check_eq "an unrunnable application is never carried forward" stop "$(verdict .uncle/workflow/runtime-unrunnable-application 1 1 2 2)"

# The REPAIR arm asks before it stops, and what it does is record the failure and go to the final audit.
DRIVER="$ROOT/scripts/stagegate.sh"
asked="$(grep -n 'if checklist_failure_continues' "$DRIVER" | head -1 | cut -d: -f1)"
stopped="$(grep -n "echo 'Automatic repair is not eligible for this failure.'" "$DRIVER" | head -1 | cut -d: -f1)"
COUNT=$((COUNT + 1))
if [[ -z "$asked" || -z "$stopped" || "$asked" -ge "$stopped" ]]; then echo "FAIL: the REPAIR arm does not ask before it stops (asks at '$asked', stops at '$stopped')"; FAILED=$((FAILED + 1)); fi
arm="$(sed -n "${asked},$((asked + 8))p" "$DRIVER")"
COUNT=$((COUNT + 1))
grep -q "record_nonblocking_failure VERIFICATION_REPORT.json" <<< "$arm" || { echo "FAIL: the failure is not recorded as unresolved evidence"; FAILED=$((FAILED + 1)); }
COUNT=$((COUNT + 1))
grep -q "set_state FINAL_AUDIT" <<< "$arm" || { echo "FAIL: the run does not go on to the final audit"; FAILED=$((FAILED + 1)); }

if [[ "$FAILED" -ne 0 ]]; then
    echo "checklist-failure-route-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "checklist-failure-route-test.sh: $COUNT checks passed"
