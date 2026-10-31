#!/usr/bin/env bash
# The baseline starts with the flow, in the background, and is reused only when it is safe: it finished cleanly, the tree is the
# one it started from, and whatever the approved list asks for beyond it is run then (and only that).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
unset WORKFLOW_EARLY_BASELINE WORKFLOW_BASELINE_BACKGROUND

new_project() {
    local d="$TMP/$1"; rm -rf "$d"; mkdir -p "$d/scripts" "$d/src" "$d/.uncle/workflow/logs"
    printf '#!/bin/sh\n' > "$d/scripts/run-python-tests.sh"; printf '#!/bin/sh\n' > "$d/scripts/run-shell-tests.sh"
    printf 'one\n' > "$d/src/a.txt"
    ( cd "$d" && git init -q && git add -A && git -c user.name=t -c user.email=t@e.t -c commit.gpgsign=false commit --no-gpg-sign -qm base )
    echo "$d"
}

# run_in <dir> <script> : run a snippet with the library loaded and a stub green_run that records what it was asked to run
run_in() {
    local d="$1"; shift
    (
        cd "$d" || exit 1
        ROOT="$ROOT"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"; GREEN_CHECK=1; GREEN_BASE="$STATE_DIR/green-check.baseline.tsv"
        export ROOT STATE_DIR LOG_DIR
        green_run() {   # <commands> <out tsv> <log> -- every command "passes" unless FAKE_FAIL names it; the call is recorded
            printf '%s\n' "$(tr '\n' '|' < "$1")" >> "$STATE_DIR/green-runs"
            : > "$2"; : > "$3"
            while IFS= read -r c; do
                printf '$ %s\nran\n' "$c" >> "$3"
                if [[ "${FAKE_FAIL:-}" == "$c" ]]; then printf '1\t%s\n' "$c" >> "$2"; else printf '0\t%s\n' "$c" >> "$2"; fi
            done < "$1"
            [[ "${FAKE_RUN_STATUS:-0}" == 0 ]]
        }
        . "$ROOT/scripts/lib/early-baseline.sh"
        eval "$1"
    ) 2>&1
}
settle() { local i; for i in $(seq 1 100); do [[ -e "$1/.uncle/workflow/early-baseline/done" ]] && return 0; sleep 0.1; done; return 1; }

# --- start ---------------------------------------------------------------------------------------------------------------
d="$(new_project start)"; out="$(run_in "$d" early_baseline_start)"
check "start: announces the detected commands" grep -q 'Starting the project.s test baseline in the background now, before planning' <<< "$out"
check "start: returns before the suite finishes (it runs in the background)" test -e "$d/.uncle/workflow/early-baseline/started"
settle "$d"
check "start: both runners ran" test "$(cat "$d/.uncle/workflow/green-runs")" == 'bash scripts/run-python-tests.sh|bash scripts/run-shell-tests.sh|'
check "start: it recorded the tree fingerprint before and after" bash -c 'test -s "$1/fingerprint" && test "$(cat "$1/fingerprint")" == "$(cat "$1/fingerprint.after")"' _ "$d/.uncle/workflow/early-baseline"
check "start: a clean run is marked done 0" test "$(cat "$d/.uncle/workflow/early-baseline/done")" == 0

d="$(new_project off)"; run_in "$d" early_baseline_start > /dev/null; true
d2="$(new_project off2)"; run_in "$d2" 'WORKFLOW_EARLY_BASELINE=0 early_baseline_start' > /dev/null
check "WORKFLOW_EARLY_BASELINE=0 starts nothing" test ! -e "$d2/.uncle/workflow/early-baseline/started"
d3="$(new_project off3)"; run_in "$d3" 'GREEN_CHECK=0 early_baseline_start' > /dev/null
check "no green check, no early baseline" test ! -e "$d3/.uncle/workflow/early-baseline/started"
d4="$(new_project have)"; echo "0	x" > "$d4/.uncle/workflow/green-check.baseline.tsv"; run_in "$d4" early_baseline_start > /dev/null
check "an existing baseline is not started again" test ! -e "$d4/.uncle/workflow/early-baseline/started"
d5="$(new_project none)"; rm -f "$d5/scripts/run-"*; run_in "$d5" early_baseline_start > /dev/null
check "a project with no recognisable suite starts nothing" test ! -e "$d5/.uncle/workflow/early-baseline/started"
d6="$(new_project twice)"; run_in "$d6" 'early_baseline_start; early_baseline_start' > /dev/null; settle "$d6"
check "starting twice runs it once" test "$(wc -l < "$d6/.uncle/workflow/green-runs" | tr -d ' ')" == 1

# --- reuse ---------------------------------------------------------------------------------------------------------------
d="$(new_project reuse)"; run_in "$d" early_baseline_start > /dev/null; settle "$d"
printf 'bash scripts/run-shell-tests.sh\nbash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "reuse: succeeds when every approved command ran early" grep -q 'rc=0' <<< "$out"
check "reuse: rows come out in the approved order" test "$(cut -f2 "$d/.uncle/workflow/base.tsv" | tr '\n' '|')" == 'bash scripts/run-shell-tests.sh|bash scripts/run-python-tests.sh|'
check "reuse: nothing was run again" test "$(wc -l < "$d/.uncle/workflow/green-runs" | tr -d ' ')" == 1
check "reuse: the baseline log is the early run's" grep -q 'ran' "$d/.uncle/workflow/base.log"
check "reuse: says what it did" grep -q 'Reusing the baseline recorded at the start of the run: 2 command(s), 0 of them run just now' <<< "$out"

d="$(new_project partial)"; run_in "$d" early_baseline_start > /dev/null; settle "$d"
printf 'npm install\nbash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "partial: reuse still succeeds" grep -q 'rc=0' <<< "$out"
check "partial: only the command the early run did not run is run now" test "$(tail -1 "$d/.uncle/workflow/green-runs")" == 'npm install|'
check "partial: both are in the baseline, in the approved order" test "$(cut -f2 "$d/.uncle/workflow/base.tsv" | tr '\n' '|')" == 'npm install|bash scripts/run-python-tests.sh|'
check "partial: the log has both runs" bash -c 'grep -q "npm install" "$1" && grep -q "run-python-tests" "$1"' _ "$d/.uncle/workflow/base.log"

d="$(new_project changed)"; run_in "$d" early_baseline_start > /dev/null; settle "$d"; printf 'two\n' > "$d/src/a.txt"
printf 'bash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "a tree that changed since the start is not reused" grep -q 'rc=1' <<< "$out"
check "...and says so" grep -q 'The tree changed after the early baseline started' <<< "$out"

d="$(new_project failed)"; run_in "$d" 'FAKE_RUN_STATUS=1 early_baseline_start' > /dev/null; settle "$d"
printf 'bash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "an early run that failed to complete is not reused" grep -q 'rc=1' <<< "$out"

d="$(new_project dirtied)"; run_in "$d" 'green_run() { printf "x\n" > src/new.txt; printf "0\t%s\n" "$(head -1 "$1")" > "$2"; : > "$3"; }; early_baseline_start' > /dev/null; settle "$d"
printf 'bash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "a run that dirtied the tree it describes is not reused" grep -q 'rc=1' <<< "$out"

d="$(new_project never)"; printf 'bash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "nothing started means nothing to reuse" grep -q 'rc=1' <<< "$out"

# --- a run still in progress is joined, not abandoned ----------------------------------------------------------------------
d="$(new_project joined)"; run_in "$d" 'green_run() { sleep 3; printf "0\t%s\n" "$(head -1 "$1")" > "$2"; printf "$ %s\nran\n" "$(head -1 "$1")" > "$3"; }; early_baseline_start' > /dev/null
printf 'bash scripts/run-python-tests.sh\n' > "$d/.uncle/workflow/approved"
out="$(run_in "$d" 'early_baseline_reuse .uncle/workflow/approved "$STATE_DIR/base.tsv" "$STATE_DIR/base.log"; echo "rc=$?"')"
check "an early run still going is waited for" grep -q 'still running' <<< "$out"
check "...and then reused" grep -q 'rc=0' <<< "$out"

# --- the real capture_green_baseline uses it ---------------------------------------------------------------------------------
awk '/^capture_green_baseline\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/change-workflow.sh" > "$TMP/capture.sh"
check "capture_green_baseline extracted" test -s "$TMP/capture.sh"
capture() {  # <dir> -- run capture_green_baseline with an approved list of both runners; prints its output
    local d="$1"
    (
        cd "$d" || exit 1
        ROOT="$ROOT"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"; GREEN_CHECK=1
        GREEN_BASE="$STATE_DIR/green-check.baseline.tsv"; GREEN_SOURCE="$STATE_DIR/green-check.source"; GREEN_CMDS="$STATE_DIR/green-check.commands"
        printf '{"verification_commands":"bash scripts/run-python-tests.sh\\nbash scripts/run-shell-tests.sh"}' > "$STATE_DIR/baseline.json"
        mkdir -p "$STATE_DIR/documents"; cp "$STATE_DIR/baseline.json" "$STATE_DIR/documents/BASELINE_REPORT.json"
        require_file() { :; }
        hash_file() { cksum < "$1" | cut -d' ' -f1; }
        verify_commands() { printf 'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh\n'; }
        resolve_baseline_parallel_groups() { :; }
        green_run() { printf 'FULLRUN\n' >> "$STATE_DIR/capture-runs"; : > "$2"; : > "$3"; while IFS= read -r c; do printf '0\t%s\n' "$c" >> "$2"; done < "$1"; }
        . "$ROOT/scripts/lib/early-baseline.sh"
        . "$TMP/capture.sh"
        capture_green_baseline
    ) 2>&1
}
d="$(new_project capture)"; run_in "$d" early_baseline_start > /dev/null; settle "$d"
out="$(capture "$d")"
check "capture: the early results become the baseline" test "$(cut -f2 "$d/.uncle/workflow/green-check.baseline.tsv" | tr '\n' '|')" == 'bash scripts/run-python-tests.sh|bash scripts/run-shell-tests.sh|'
check "capture: the approved list is not run again" test ! -e "$d/.uncle/workflow/capture-runs"
check "capture: the baseline is bound to the approved report" test -s "$d/.uncle/workflow/green-check.source"
check "capture: says it reused the early baseline" grep -q 'Reusing the baseline recorded at the start of the run' <<< "$out"

d="$(new_project capture-fallback)"; run_in "$d" early_baseline_start > /dev/null; settle "$d"; printf 'two\n' > "$d/src/a.txt"
out="$(capture "$d")"
check "capture: a changed tree falls back to running the approved list" test "$(cat "$d/.uncle/workflow/capture-runs")" == FULLRUN
check "capture: the fallback baseline still exists" test -s "$d/.uncle/workflow/green-check.baseline.tsv"

d="$(new_project capture-none)"
out="$(capture "$d")"
check "capture: with no early run it behaves exactly as before" test "$(cat "$d/.uncle/workflow/capture-runs")" == FULLRUN

[[ "$fails" == 0 ]] && echo "early-baseline-stage-test.sh: all checks passed" || { echo "early-baseline-stage-test.sh: $fails failure(s)"; exit 1; }
