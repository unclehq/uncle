#!/usr/bin/env bash
# launch(): an unattended driver that just vanishes mid-run (machine slept, a
# parent shell died, anything that takes the process out before it can write
# why) must be resumed automatically -- the whole point of "unattended" is
# that nobody is there to notice and restart it by hand. But a stop the
# driver chose on purpose (a recorded stop-reason, or reaching COMPLETE) must
# never be silently retried: that would route around the exact human gates
# CLAUDE.md requires, and around a repair budget that ran out for a reason.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected [$2] got [$3]"; fi; }

sed -n '/^launch() {/,/^choose_model() {/p' "$ROOT/uncle" | sed '$d' > "$temp/fn.sh"
grep -q '^launch() {' "$temp/fn.sh" || { echo 'FATAL: could not extract launch'; exit 2; }

C_RED=""; C_YELLOW=""; C_RESET=""
UNCLE_LAUNCH_RETRY_DELAY=0
cd "$temp"
mkdir -p .uncle/workflow
# shellcheck disable=SC1090
source "$temp/fn.sh"

calls_file="$temp/calls"

# --- a clean, attended run is never retried, even if it "fails" -----------
: > "$calls_file"
fake_driver() { echo x >> "$calls_file"; return 1; }
launch fake_driver
check "an attended failure is not retried" "1" "$(wc -l < "$calls_file" | tr -d ' ')"

# --- COMPLETE is a terminal state: no retry, even unattended --------------
: > "$calls_file"
printf 'COMPLETE' > .uncle/workflow/state
rm -f .uncle/workflow/stop-reason
fake_driver_complete() { echo x >> "$calls_file"; return 0; }
launch fake_driver_complete --unattended
check "COMPLETE is never retried" "1" "$(wc -l < "$calls_file" | tr -d ' ')"

# --- a recorded stop-reason is a deliberate stop: no retry -----------------
: > "$calls_file"
printf 'REPAIR' > .uncle/workflow/state
printf 'human' > .uncle/workflow/stop-reason
fake_driver_human() { echo x >> "$calls_file"; return 1; }
launch fake_driver_human --unattended
check "a recorded stop-reason is never retried" "1" "$(wc -l < "$calls_file" | tr -d ' ')"
rm -f .uncle/workflow/stop-reason

# --- the actual gap: process gone, non-terminal state, no reason ----------
# Simulates a driver that dies unexpectedly on its first two launches (state
# left mid-run, no stop-reason -- exactly what an unexplained process death
# looks like) and succeeds, reaching COMPLETE, on the third.
: > "$calls_file"
printf 'TEST_REVIEW' > .uncle/workflow/state
fake_driver_flaky() {
    echo x >> "$calls_file"
    local n; n="$(wc -l < "$calls_file" | tr -d ' ')"
    if [[ "$n" -ge 3 ]]; then
        printf 'COMPLETE' > .uncle/workflow/state
        return 0
    fi
    return 1
}
launch fake_driver_flaky --unattended
check "an unexplained death is resumed automatically" "3" "$(wc -l < "$calls_file" | tr -d ' ')"
check "it reaches COMPLETE once the driver actually finishes" "COMPLETE" "$(cat .uncle/workflow/state)"

# --- a run that never recovers stops after the bound, not forever ----------
: > "$calls_file"
printf 'REPAIR' > .uncle/workflow/state
rm -f .uncle/workflow/stop-reason
fake_driver_stuck() { echo x >> "$calls_file"; return 1; }
launch fake_driver_stuck --unattended
check "a persistently unexplained failure stops at the bound, not forever" "5" "$(wc -l < "$calls_file" | tr -d ' ')"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "launch-self-heal-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "launch-self-heal-test.sh: $PASS checks passed"
