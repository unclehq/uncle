#!/usr/bin/env bash
# A review that could not complete is a distinct unattended result: its own documented exit status (3), not the generic failure (1)
# and not the internal status 2 of implementation_incomplete_choice (issue 286).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
DRIVER="$ROOT/scripts/change-workflow.sh"
GATES="$ROOT/scripts/lib/implementation-gates.sh"

check "gates library parses" bash -n "$GATES"
check "driver parses" bash -n "$DRIVER"
check "driver names the review-incomplete result" grep -qiE 'review[- _]incomplete' "$DRIVER" "$GATES"
check "driver exits with status 3 for it" grep -qE 'exit 3|return 3|REVIEW_INCOMPLETE_EXIT=3|EXIT_REVIEW_INCOMPLETE=3' "$DRIVER" "$GATES"
check "exit status 3 is documented" grep -qiE '(exit|status)[^\n]*3[^\n]*review[- ]incomplete|review[- ]incomplete[^\n]*(exit|status)[^\n]*3' "$DRIVER" "$GATES"
check "generic failure still exits 1" grep -qE 'exit 1' "$DRIVER"

if ((fails)); then echo "review-incomplete-exit-test: $fails failed"; exit 1; fi
echo "review-incomplete-exit-test: ok"
