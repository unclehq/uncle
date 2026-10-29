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
mkdir -p "$STATE_DIR" "$LOG_DIR"
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
green_application_not_runnable
UNATTENDED=1
if route_unrunnable_application; then
    echo 'runtime route should request a transition' >&2
    exit 1
else
    [[ "$?" == 2 ]]
fi
[[ "$(<"$STATE_DIR/next")" == IMPLEMENT ]]

if route_unrunnable_application; then
    echo 'persistent runtime failure should stop rather than loop' >&2
    exit 1
else
    [[ "$?" == 1 ]]
fi

echo 'runtime readiness tests passed'
