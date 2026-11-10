#!/usr/bin/env bash
# PROJECT_PLAN spending-stop handling in scripts/stagegate.sh (AC-3, AC-4, AC-5, AC-7, AC-8).
# The stagegate helpers are extracted by name and run against stubbed workers that exit with chosen codes.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap '[[ -n "${KEEP:-}" ]] || rm -rf "$TMP"' EXIT
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected [$3] got [$2]"; fail=1; fi; }

# Fake ROOT: model-jobs.sh and the sections helper (gate = a, phases = "a b" then "c").
FR="$TMP/root"; mkdir -p "$FR/scripts/lib"
echo 'workflow_model_enter() { return 0; }' > "$FR/scripts/lib/model-jobs.sh"
cat > "$FR/scripts/lib/project_plan_sections.py" <<'PY'
import sys
print({'gate': 'a', 'phases': 'a b\nc'}[sys.argv[1]])
PY
FUNCS="$TMP/funcs.sh"
for fn in project_plan_spend_marker_valid project_plan_spend_worker_status project_plan_spend_any \
          project_plan_spend_finish project_plan_budget_cap project_plan_section_resumable \
          run_project_plan_sections_bounded; do
    awk -v f="$fn" '$0 ~ "^"f"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$HERE/scripts/stagegate.sh"
done > "$FUNCS"
[[ -s "$FUNCS" ]] || { echo "FAIL could not extract stagegate functions"; exit 1; }

# Runs the bounded scheduler with stub workers. $1 = "a=CODE b=CODE c=CODE" (marker written when code is 75 unless
# name is in NOMARKER / GARBAGE).  Prints the scheduler exit code.
run_case() {
    local spec="$1" jobs="${2:-4}"
    (
        set +e
        ROOT="$FR"; STATE_DIR="$TMP/state"; LOG_DIR="$TMP/logs"; mkdir -p "$STATE_DIR" "$LOG_DIR"
        PP_SPEND_DIR="$(mktemp -d "$TMP/spend.XXXXXX")"; PP_SPENDING_OPT_IN=1; PP_OTHER_FAILURES=0
        export PP_SPEND_DIR PP_SPENDING_OPT_IN
        . "$FUNCS"
        code_of() { local kv; for kv in $spec; do [[ "${kv%%=*}" == "$1" ]] && { echo "${kv##*=}"; return; }; done; echo 0; }
        project_plan_section_run() {
            local n="$1" c="$(code_of "$1")"
            export UNCLE_SPENDING_STOP_FILE="$PP_SPEND_DIR/$n.stop"
            if [[ "$c" == 75 ]]; then
                case " ${NOMARKER:-} " in *" $n "*) ;; *)
                    if [[ " ${GARBAGE:-} " == *" $n "* ]]; then echo 'not json' > "$PP_SPEND_DIR/$n.stop"
                    else echo '{"code":"budget_reached","scope":"x","limit_atomic":5,"used_atomic":6,"suggested_increase_atomic":null,"balance_atomic":null}' > "$PP_SPEND_DIR/$n.stop"; fi ;; esac
            fi
            [[ "$c" == 0 ]] && echo body > "$2/$n.md"
            echo "$n" >> "$TMP/started"
            return "$c"
        }
        project_plan_section_settle() { [[ -s "$2/$1.md" ]] && : > "$2/$1.done"; }
        mkdir -p "$TMP/sections"
        run_project_plan_sections_bounded "$TMP/sections" file "$jobs"
        echo "rc=$?" > "$TMP/rc"
        echo "other=$PP_OTHER_FAILURES" >> "$TMP/rc"
    ) >/dev/null 2>"$TMP/err"
    sed -n 's/^rc=//p' "$TMP/rc"
}
reset() { rm -rf "$TMP/state" "$TMP/sections" "$TMP/started" "$TMP/rc" "$TMP/logs"; }

# All succeed.
reset; check "success returns 0" "$(run_case 'a=0 b=0 c=0')" 0
# AC-3/AC-4: spending stop with a valid marker -> 75, stop-reason written, finished sections kept.
reset; rc="$(run_case 'a=0 b=75 c=0')"
check "valid marker returns 75" "$rc" 75
check "stop-reason starts spending_limit" "$(head -c 14 "$TMP/state/stop-reason" 2>/dev/null)" spending_limit
check "finished section a kept" "$([[ -s "$TMP/sections/a.md" ]] && echo yes)" yes
check "dependent section c not started" "$(grep -c '^c$' "$TMP/started" 2>/dev/null)" 0
# AC-8: ordinary failure -> 1 and no stop-reason.
reset; check "ordinary failure returns 1" "$(run_case 'a=0 b=1 c=0')" 1
check "no stop-reason for ordinary failure" "$([[ -e "$TMP/state/stop-reason" ]] && echo yes || echo no)" no
# Exit 75 without / with garbage marker is an ordinary failure.
reset; NOMARKER=b check "75 with no marker returns 1" "$(NOMARKER=b run_case 'a=0 b=75 c=0')" 1
reset; check "75 with garbage marker returns 1" "$(GARBAGE=b run_case 'a=0 b=75 c=0')" 1
check "garbage marker writes no stop-reason" "$([[ -e "$TMP/state/stop-reason" ]] && echo yes || echo no)" no
# Mixed: one worker 75, another ordinary failure -> 75; failure count recorded; finished sections kept.
reset; rc="$(run_case 'a=0 b=75 c=1')"
check "mixed outcome returns 75" "$rc" 75
check "mixed outcome keeps finished a" "$([[ -s "$TMP/sections/a.md" ]] && echo yes)" yes
# Mixed with the ordinary failure inside the first phase.
reset; rc="$(run_case 'a=1 b=75 c=0')"
check "mixed (gate fails ordinary) returns 75" "$rc" 75
check "mixed records other_failures=1" "$(grep -c 'other_failures=1' "$TMP/state/stop-reason" 2>/dev/null)" 1

# AC-7: budget cap.
capcheck() { ( PP_SPEND_DIR="$TMP/cap"; rm -rf "$PP_SPEND_DIR"; mkdir -p "$PP_SPEND_DIR"; [[ -z "${2-}" ]] || printf '%s' "$2" > "$PP_SPEND_DIR/w.budget"
               . "$FUNCS"; project_plan_budget_cap 14 ); }
check "cap remaining 10000000 -> 14" "$(capcheck x 10000000)" 14
check "cap remaining 1000000 -> 2" "$(capcheck x 1000000)" 2
check "cap remaining 399999 -> 1" "$(capcheck x 399999)" 1
check "cap remaining 0 -> 1" "$(capcheck x 0)" 1
check "cap remaining -5 -> 1" "$(capcheck x -5)" 1
check "cap non-integer leaves concurrency" "$(capcheck x abc)" 14
check "cap absent leaves concurrency" "$(capcheck x)" 14

# AC-8 / resume: only a finished-and-marked section is reusable, and only when resuming.
d="$TMP/res"; mkdir -p "$d"; echo body > "$d/a.md"
res() { ( . "$FUNCS"; PP_RESUME="$1"; project_plan_section_resumable a "$d" file && echo yes || echo no ); }
check "no .done marker -> rerun" "$(res 1)" no
: > "$d/a.done"
check "done + resume -> skip" "$(res 1)" yes
check "done but not resuming -> rerun" "$(res 0)" no
: > "$d/a.md"
check "empty output -> rerun" "$(res 1)" no

exit "$fail"
