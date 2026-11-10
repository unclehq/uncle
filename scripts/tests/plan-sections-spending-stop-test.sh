#!/usr/bin/env bash
# Issue 230: a spending stop in one section worker keeps the finished sections, starts no new worker,
# and a resume runs only the missing ones. Drives the real bounded scheduler with stubbed workers.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
STATE_DIR="$WORK/state"; LOG_DIR="$WORK/logs"; DIR="$STATE_DIR/project-plan-sections"
mkdir -p "$STATE_DIR" "$LOG_DIR" "$DIR/prompts"
fail=0; check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected '$3', got '$2'"; fail=1; fi; }

# The scheduler as it is in stagegate.sh, not a copy.
eval "$(sed -n '/^run_project_plan_sections_bounded() {/,/^}/p' "$ROOT/scripts/stagegate.sh")"
workflow_model_enter() { return 0; }
project_plan_section_settle() { [[ -s "$2/$1.md" ]]; }
project_plan_section_run() {   # name directory delivery
    echo "$1" >> "$WORK/started"
    if [[ "$1" == "${STOP_AT:-}" ]]; then echo 'Stopped: the task spending limit ($6.00) was reached.' > "$STATE_DIR/spending-stop"; return 1; fi
    sleep 0.2; echo "# $1" > "$2/$1.md"
}
export -f project_plan_section_run workflow_model_enter project_plan_section_settle 2>/dev/null || true

: > "$WORK/started"
STOP_AT=design UNCLE_PLAN_SECTIONS_RESUME=0 run_project_plan_sections_bounded "$DIR" file 3 >/dev/null 2>&1
check "bounded run fails on a spending stop" "$?" "1"
check "marker left for the stage" "$([[ -s "$STATE_DIR/spending-stop" ]] && echo yes)" "yes"
total="$(python3 -B "$ROOT/scripts/lib/project_plan_sections.py" phases | wc -w | tr -d ' ')"
check "not every section was started" "$([[ "$(wc -l < "$WORK/started" | tr -d ' ')" -lt "$total" ]] && echo yes)" "yes"
kept="$(ls "$DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')"
check "finished sections are kept on disk" "$([[ "$kept" -ge 1 ]] && echo yes)" "yes"

# Resume: the limit was raised. Only what is missing runs.
rm -f "$STATE_DIR/spending-stop"; : > "$WORK/started"
UNCLE_PLAN_SECTIONS_RESUME=1 run_project_plan_sections_bounded "$DIR" file 3 >/dev/null 2>&1
check "resume completes" "$?" "0"
check "resume restarts no finished section" "$(sort "$WORK/started" | uniq -d | wc -l | tr -d ' ')" "0"
check "resume ran fewer workers than a fresh run" "$([[ "$(wc -l < "$WORK/started" | tr -d ' ')" -lt "$total" ]] && echo yes)" "yes"
check "every section ends up on disk" "$(ls "$DIR"/*.md | wc -l | tr -d ' ')" "$total"
exit "$fail"
