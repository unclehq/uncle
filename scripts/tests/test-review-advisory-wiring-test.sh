#!/usr/bin/env bash
# VALIDATE_TEST_REVIEW calls test_review_advisory.py before any routing
# decision is made from TEST_REVIEW.json, gated to unattended runs only, with
# a kill switch, and ledgers what it downgrades rather than acting silently.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

block="$(sed -n '/^        VALIDATE_TEST_REVIEW)/,/^        [A-Z_]*)/p' "$ROOT/scripts/stagegate.sh")"
[[ -n "$block" ]] || { echo 'FATAL: could not extract VALIDATE_TEST_REVIEW'; exit 2; }

if printf '%s' "$block" | grep -q 'test_review_advisory.py'; then ok; else bad "calls-advisory-tool" "VALIDATE_TEST_REVIEW does not call test_review_advisory.py"; fi
if printf '%s' "$block" | grep -q 'WORKFLOW_ADVISORY_TEST_REVIEW'; then ok; else bad "has-kill-switch" "no WORKFLOW_ADVISORY_TEST_REVIEW kill switch"; fi
if printf '%s' "$block" | grep -qE '\$UNATTENDED.*== 1'; then ok; else bad "gated-to-unattended" "advisory downgrade is not gated to UNATTENDED"; fi
if printf '%s' "$block" | grep -q 'record_nonblocking_failure TEST_REVIEW.json'; then ok; else bad "ledgers-the-downgrade" "a downgrade is not recorded to the nonblocking-failures ledger"; fi
# The call must happen before the canonical JSON feeds any acceptance_json.py
# routing decision, or the downgrade never has a chance to change the result.
advisory_line="$(printf '%s' "$block" | grep -n 'test_review_advisory.py' | head -1 | cut -d: -f1)"
first_route_line="$(printf '%s' "$block" | grep -n 'acceptance_json.py' | head -1 | cut -d: -f1)"
if [[ -n "$advisory_line" && -n "$first_route_line" && "$advisory_line" -lt "$first_route_line" ]]; then
    ok
else
    bad "runs-before-routing" "advisory downgrade (line $advisory_line) does not precede the first routing read (line $first_route_line)"
fi

bash -n "$ROOT/scripts/stagegate.sh" && ok || bad "syntax" "stagegate.sh fails bash -n"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "test-review-advisory-wiring-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "test-review-advisory-wiring-test.sh: $PASS checks passed"
