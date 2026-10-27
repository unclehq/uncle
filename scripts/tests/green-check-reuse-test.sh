#!/usr/bin/env bash
# run_green_check against an unchanged tree: a clean result and a failing result are both reused (the
# commands run once), and any change to the tree -- or switching reuse off -- runs them again.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

awk '/^run_green_check\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

new_project() {   # name
    local dir="$TMP/$1"; mkdir -p "$dir/src" "$dir/.uncle/workflow/logs" "$dir/.uncle/docs"
    printf 'one\n' > "$dir/src/a.js"; printf 'plan\n' > "$dir/.uncle/docs/UPDATED_PROJECT_PLAN.md"
    echo "$dir"
}

# call <dir> <outcome clean|failed> [env assignments...] : one run_green_check call; prints its output
call() {
    local dir="$1" outcome="$2"; shift 2
    (
        cd "$dir"
        for assignment in "$@"; do export "$assignment"; done
        ROOT="$ROOT"; PROJECT_ROOT="$PWD"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        GREEN_CHECK=1; GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"
        GREEN_CLASS="$STATE_DIR/green-check.tsv"; GREEN_MD="$STATE_DIR/green-check.md"
        verify_commands() { printf 'npm test\n'; }
        verify_parallel_groups() { return 0; }
        parallel_groups_format_hint() { :; }
        check_verification_inputs() { :; }
        green_run() { echo run >> "$STATE_DIR/runs"; printf '%s\tnpm test\n' "$([[ "$FAKE_OUTCOME" == clean ]] && echo 0 || echo 1)" > "$2"; }
        green_classify() { printf '%s\tnpm test\n' "$([[ "$FAKE_OUTCOME" == clean ]] && echo PASS || echo REGRESSION)" < /dev/null; }
        green_report() { echo "report" > "$2"; }
        green_regressions() { grep -c '^REGRESSION' "$1" 2>/dev/null || true; }
        FAKE_OUTCOME="$outcome"
        . "$TMP/fn.sh"
        run_green_check
    ) 2>&1
}
runs() { wc -l < "$1/.uncle/workflow/runs" 2>/dev/null | tr -d ' ' || echo 0; }

# --- clean: the second call reuses -----------------------------------------------------------------------
d="$(new_project clean)"
call "$d" clean > "$TMP/o1"; call "$d" clean > "$TMP/o2"
check "clean: the commands ran once"                   test "$(runs "$d")" == 1
check "clean: the second call says it reused"          grep -q 'already passed on this exact tree' "$TMP/o2"
check "clean: the fingerprint records the outcome"     grep -q ' clean$' "$d/.uncle/workflow/green-check.fingerprint"

# --- failed: reused too, and the failure is still reported -----------------------------------------------
d="$(new_project failed)"
call "$d" failed > "$TMP/f1"; rc1=$?; call "$d" failed > "$TMP/f2"; rc2=$?
check "failed: the commands ran once"                  test "$(runs "$d")" == 1
check "failed: the second call says it reused"         grep -q 'already failed on this exact tree' "$TMP/f2"
check "failed: the failure is still reported (nonzero, with the command named)" bash -c 'grep -q "npm test" "$1"' _ "$TMP/f2"
check "failed: the fingerprint records the outcome"    grep -q ' failed$' "$d/.uncle/workflow/green-check.fingerprint"

# --- any change runs it again ----------------------------------------------------------------------------
d="$(new_project changed)"
call "$d" failed > /dev/null; printf 'two\n' > "$d/src/a.js"; call "$d" clean > "$TMP/c2"
check "an edited file: the commands ran again"         test "$(runs "$d")" == 2
check "an edited file: the new result replaced the old" grep -q ' clean$' "$d/.uncle/workflow/green-check.fingerprint"
d="$(new_project newfile)"
call "$d" clean > /dev/null; printf 'x\n' > "$d/src/b.js"; call "$d" clean > /dev/null
check "a new file: the commands ran again"             test "$(runs "$d")" == 2

# --- the switches ---------------------------------------------------------------------------------------
d="$(new_project norefail)"
call "$d" failed WORKFLOW_GREEN_CHECK_REUSE_FAILED=0 > /dev/null; call "$d" failed WORKFLOW_GREEN_CHECK_REUSE_FAILED=0 > /dev/null
check "REUSE_FAILED=0: a failure runs again"           test "$(runs "$d")" == 2
d="$(new_project noreuse)"
call "$d" clean WORKFLOW_GREEN_CHECK_REUSE=0 > /dev/null; call "$d" clean WORKFLOW_GREEN_CHECK_REUSE=0 > /dev/null
check "REUSE=0: nothing is reused"                     test "$(runs "$d")" == 2
d="$(new_project cmdchange)"
call "$d" clean > /dev/null
( cd "$d"; ROOT="$ROOT"; PROJECT_ROOT="$PWD"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
  GREEN_CHECK=1; GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"
  GREEN_CLASS="$STATE_DIR/green-check.tsv"; GREEN_MD="$STATE_DIR/green-check.md"
  verify_commands() { printf 'npm run other\n'; }; verify_parallel_groups() { return 0; }; parallel_groups_format_hint() { :; }
  check_verification_inputs() { :; }
  green_run() { echo run >> "$STATE_DIR/runs"; printf '0\tnpm run other\n' > "$2"; }
  green_classify() { printf 'PASS\tnpm run other\n'; }; green_report() { echo r > "$2"; }; green_regressions() { echo 0; }
  . "$TMP/fn.sh"; run_green_check > /dev/null 2>&1 )
check "different commands: the commands ran again"     test "$(runs "$d")" == 2

[[ "$fails" == 0 ]] && echo "green-check-reuse-test.sh: all checks passed" || exit 1
