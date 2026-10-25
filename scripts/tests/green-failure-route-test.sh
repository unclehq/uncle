#!/usr/bin/env bash
set -euo pipefail

# What happens to a failing driver verification (for example `npx playwright test`).
# It used to get exactly one automatic repair, after which the run carried the
# remaining failures forward as "nonblocking evidence" and moved on, so most of a
# failing suite was never fixed.  The route is now: repair while attempts remain,
# then continue or ask.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FAILED=0
COUNT=0
check_eq() {
    COUNT=$((COUNT + 1))
    [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }
}

FUNC="$(ROOT="$ROOT" python3 -B - <<'PY'
import os, re
from pathlib import Path
source = (Path(os.environ["ROOT"]) / "scripts" / "stagegate.sh").read_text()
print(re.search(r"^green_failure_route\(\) \{.*?^}", source, re.M | re.S).group(0))
PY
)"
eval "$FUNC"

# continue-on-failure, repairs used, attempts
check_eq "first failure goes to repair" repair "$(green_failure_route 1 0 3)"
check_eq "second failure goes to repair" repair "$(green_failure_route 1 1 3)"
check_eq "third failure goes to repair" repair "$(green_failure_route 1 2 3)"
check_eq "attempts spent, continuing is configured: carry it forward" continue "$(green_failure_route 1 3 3)"
check_eq "attempts spent, continuing is not configured: ask the owner" ask "$(green_failure_route 0 3 3)"
check_eq "repair attempts of zero never repairs automatically (continue)" continue "$(green_failure_route 1 0 0)"
check_eq "repair attempts of zero never repairs automatically (ask)" ask "$(green_failure_route 0 0 0)"
check_eq "the default stays within the repair limit" repair "$(green_failure_route 1 3 4)"

# The driver uses it, with the configurable limit, in both places that used to hard-code one.
DRIVER="$ROOT/scripts/stagegate.sh"
COUNT=$((COUNT + 1))
grep -q 'repair_count_existing" -ge "\$WORKFLOW_AUTO_REPAIR_ATTEMPTS"' "$DRIVER" || { echo "FAIL: REPAIR still limits itself to a fixed number of attempts"; FAILED=$((FAILED + 1)); }
COUNT=$((COUNT + 1))
if grep -q 'repair_count_existing" -ge 1 \]\]' "$DRIVER"; then echo "FAIL: a hard-coded single repair remains"; FAILED=$((FAILED + 1)); fi
COUNT=$((COUNT + 1))
grep -q 'green_route="$(green_failure_route' "$DRIVER" || { echo "FAIL: the test-review routing does not use green_failure_route"; FAILED=$((FAILED + 1)); }

if [[ "$FAILED" -ne 0 ]]; then
    echo "green-failure-route-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "green-failure-route-test.sh: $COUNT checks passed"
