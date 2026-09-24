#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/scripts/stagegate.sh"
BLOCK="$(sed -n '/repair_judge || repair_status=\$?/,/plan_after_write || plan_status=\$?/p' "$SOURCE")"
fail() { echo "FAIL: $*" >&2; exit 1; }
[[ "$BLOCK" == *'Repair changed the test-review evidence base; invalidating review and rerunning verification.'* ]] || fail "test-review repair invalidation missing"
[[ "$BLOCK" == *'rm -f .uncle/docs/TEST_REVIEW.md "$STATE_DIR/documents/TEST_REVIEW.json"'* ]] || fail "canonical review is not invalidated"
green_line="$(printf '%s\n' "$BLOCK" | grep -n 'run_green_check' | head -1 | cut -d: -f1)"
state_line="$(printf '%s\n' "$BLOCK" | grep -n 'set_state TEST_REVIEW' | head -1 | cut -d: -f1)"
[[ -n "$green_line" && -n "$state_line" && "$green_line" -lt "$state_line" ]] || fail "fresh test review must follow green check"
echo 'repair-test-review-invalidation-test.sh: repair invalidates canonical review before a fresh green check and review'
