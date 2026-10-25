#!/usr/bin/env bash
set -euo pipefail

# A test review with FAILED rows (assertions too weak to reject an injected defect,
# a missing test) used to be carried forward as "nonblocking evidence" whenever the
# driver's green check passed, so the gap was never repaired.  While automatic
# attempts remain it now goes to repair; rows that are only NOT RUN or BLOCKED are
# evidence gaps no code change closes, and still pass through.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT + 1)); [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }; }

FUNCS="$(ROOT="$ROOT" python3 -B - <<'PY'
import os, re
from pathlib import Path
source = (Path(os.environ["ROOT"]) / "scripts" / "stagegate.sh").read_text()
for name in ("continue_nonblocking_test_review", "green_failure_route"):
    print(re.search(r"^" + name + r"\(\) \{.*?^}", source, re.M | re.S).group(0))
PY
)"

STATE_DIR="$TMP/state"; mkdir -p "$STATE_DIR/documents"
write_review() {  # status of the ASSERTIONS row; the rest are PASS
    python3 - "$STATE_DIR/documents/TEST_REVIEW.json" "$1" <<'PY'
import json, sys
rows = [{'id': i, 'required': True, 'status': 'PASS', 'evidence': 'ok'} for i in ('COVERAGE', 'INTEGRITY', 'ORACLE', 'NEGATIVE', 'RESULTS')]
rows.append({'id': 'ASSERTIONS', 'required': True, 'status': sys.argv[2], 'evidence': 'observed'})
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': rows}, open(sys.argv[1], 'w'))
PY
}

run() {  # $1 next state, $2 repairs used; prints "<return status> <state set>"
    (
        eval "$FUNCS"
        WORKFLOW_CONTINUE_ON_TEST_FAILURE=1; WORKFLOW_AUTO_REPAIR=1; WORKFLOW_AUTO_REPAIR_ATTEMPTS=3
        GREEN_CHECK=1; GREEN_CLASS="$TMP/class"; printf 'PASS\tcmd\n' > "$GREEN_CLASS"
        printf '%s' "$2" > "$STATE_DIR/repair-count"
        green_regressions() { printf 0; }
        record_nonblocking_failure() { :; }
        set_state() { echo "state=$1"; }
        ROOT="$ROOT"
        status=0
        out="$(continue_nonblocking_test_review "$1" 2>&1)" || status=$?
        echo "return=$status $(grep -o 'state=.*' <<<"$out" || true) $(grep -c 'sending them to repair' <<<"$out" || true)"
    )
}

write_review FAIL
check "failed rows, attempts left: not carried forward (goes to repair)" "return=1  1" "$(run MANUAL_CHECKLIST 0)"
check "failed rows, second attempt still repairs" "return=1  1" "$(run MANUAL_CHECKLIST 2)"
check "failed rows, attempts spent: carried forward" "return=0 state=MANUAL_CHECKLIST 0" "$(run MANUAL_CHECKLIST 3)"
check "failed rows at final audit are never sent back to repair" "return=0 state=FINAL_AUDIT 0" "$(run FINAL_AUDIT 0)"

write_review 'NOT RUN'
check "rows that are only NOT RUN pass through" "return=0 state=MANUAL_CHECKLIST 0" "$(run MANUAL_CHECKLIST 0)"
write_review PASS
check "a passing review is not a finding at all" "return=1  0" "$(run MANUAL_CHECKLIST 0)"

# REPAIR accepts a test-review source, not only the green check.
check "REPAIR runs for a test-review finding" yes "$(grep -q 'repair_source" != .uncle/docs/TEST_REVIEW.md' "$ROOT/scripts/stagegate.sh" && echo yes || echo no)"

if [[ "$FAILED" -ne 0 ]]; then echo "test-review-repair-route-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "test-review-repair-route-test.sh: $COUNT checks passed"
