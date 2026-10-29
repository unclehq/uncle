#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

sed -n '/^# A failed assertion can be useful delivery evidence/,/^promote_winner_work() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/helpers.sh"
STATE_DIR="$temp/state"
LOG_DIR="$temp/logs"
GREEN_MD="$temp/green-check.md"
GREEN_CUR="$temp/green-check.current.tsv"
GREEN_CLASS="$temp/green-check.class.tsv"
GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"
mkdir -p "$STATE_DIR/documents" "$STATE_DIR/parallel-implementation-groups" \
    "$STATE_DIR/parallel/notes" "$LOG_DIR" "$temp/.uncle/docs"
cd "$temp"
touch "$GREEN_MD"
set_state() { printf '%s\n' "$1" > "$STATE_DIR/next"; }
# shellcheck disable=SC1090
source "$temp/helpers.sh"

printf '%s\n' 'AssertionError: expected 5 to equal 6' > "$LOG_DIR/green-check.log"
if green_application_not_runnable; then
    echo 'ordinary assertion failure was incorrectly treated as a runtime failure' >&2
    exit 1
fi

printf '%s\n' 'src/App.jsx (2:31): "formatDisplay" is not exported by "src/calc.js"' > "$LOG_DIR/green-check.log"
touch "$STATE_DIR/parallel-implementation-complete" \
      "$STATE_DIR/parallel-implementation-report-complete" \
      "$STATE_DIR/parallel-implementation-serial-fallback" \
      "$STATE_DIR/green-check.fingerprint" \
      "$GREEN_OVERRIDE_FILE" \
      "$STATE_DIR/parallel-implementation-groups/group-1" \
      "$STATE_DIR/parallel/notes/step-1.json" \
      "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" \
      "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json"
printf '%s\n' 'old report' > .uncle/docs/IMPLEMENTATION_NOTES.md
printf '%s\n' 'old report' > .uncle/docs/AUTOMATED_TEST_REPORT.md
green_application_not_runnable
UNATTENDED=1
if route_unrunnable_application; then
    echo 'runtime route should request a transition' >&2
    exit 1
else
    [[ "$?" == 2 ]]
fi
# A forced full IMPLEMENT re-entry used to discard every merged worker's
# completion marker here, so IMPLEMENT reran the entire parallel fan-out
# from scratch for what was usually a small, localized fix. REPAIR is the
# bounded path every other green-check failure already uses -- it builds
# on top of the existing merged implementation rather than discarding it,
# so none of that state should be touched.
[[ "$(<"$STATE_DIR/next")" == REPAIR ]] || { echo 'runtime route did not go to the bounded REPAIR path' >&2; exit 1; }
[[ "$(cat "$STATE_DIR/repair-source")" == "$GREEN_MD" ]] || { echo 'runtime repair did not record the green-check as its source' >&2; exit 1; }
[[ -e "$LOG_DIR/green-check.log" ]] || { echo 'runtime repair discarded green-check evidence' >&2; exit 1; }
for kept in \
    "$STATE_DIR/parallel-implementation-complete" \
    "$STATE_DIR/parallel-implementation-report-complete" \
    "$STATE_DIR/parallel-implementation-serial-fallback" \
    "$STATE_DIR/green-check.fingerprint" \
    "$GREEN_OVERRIDE_FILE" \
    "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" \
    "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json" \
    .uncle/docs/IMPLEMENTATION_NOTES.md \
    .uncle/docs/AUTOMATED_TEST_REPORT.md \
    "$STATE_DIR/parallel-implementation-groups/group-1" \
    "$STATE_DIR/parallel/notes/step-1.json"; do
    [[ -e "$kept" ]] || { echo "runtime repair discarded completed implementation state: $kept" >&2; exit 1; }
done

printf '%s\n' 'Error: No test files found' > "$LOG_DIR/green-check.log"
green_application_not_runnable || { echo 'empty test discovery was incorrectly treated as nonblocking' >&2; exit 1; }

# Checklist workers must not run until the implementation green check has
# completed and the runtime route has handled fatal build/module/test-discovery
# failures. Final audit keeps the same guard as a reuse safety net.
validate_review="$(sed -n '/^        VALIDATE_TEST_REVIEW)/,/^        MANUAL_CHECKLIST)/p' "$ROOT/scripts/stagegate.sh")"
[[ "$validate_review" == *'green_wait_final'* ]] || { echo 'missing checklist green-check wait' >&2; exit 1; }
[[ "$validate_review" == *'route_unrunnable_application'* ]] || { echo 'checklist runtime errors were not routed to implementation' >&2; exit 1; }
python3 - "$validate_review" <<'PY'
import sys
block = sys.argv[1]
if block.index('green_wait_final') > block.rindex('route_unrunnable_application'):
    raise SystemExit('runtime route precedes checklist verification')
PY

final_audit="$(sed -n '/^        FINAL_AUDIT)/,/^        VALIDATE_AUDIT)/p' "$ROOT/scripts/stagegate.sh")"
[[ "$final_audit" == *'green_wait_final'* ]] || { echo 'final audit lost green-check reuse guard' >&2; exit 1; }

if route_unrunnable_application; then
    echo 'persistent runtime failure should stop rather than loop' >&2
    exit 1
else
    [[ "$?" == 1 ]]
fi

echo 'runtime readiness tests passed'
