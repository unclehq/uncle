#!/usr/bin/env bash
# The change driver's final green check with an impacted-tests scope: scoped only when the class (or the operator) says so and the
# mapping is confident, the baseline untouched, the report honest about what was NOT RUN, and the full suite everywhere else.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
unset WORKFLOW_TEST_SCOPE UNCLE_STATUS_FILE UNCLE_SUPERVISION_HOST UNATTENDED

awk '/^run_green_check\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

new_project() {   # name class test_scope -- a git repo with Uncle's layout, one module edited
    local d="$TMP/$1"; rm -rf "$d"; mkdir -p "$d/scripts/lib" "$d/scripts/tests" "$d/.uncle/workflow/logs" "$d/.uncle/docs"
    for n in alpha beta gamma delta; do
        printf 'x = 1\n' > "$d/scripts/lib/${n}_module.py"
        printf 'import %s_module  # scripts/lib/%s_module.py\n' "$n" "$n" > "$d/scripts/tests/$n-checks-test.py"
    done
    printf '# alpha_module.py\n' > "$d/scripts/tests/alpha-driver-test.sh"; printf 'true\n' > "$d/scripts/tests/other-test.sh"
    printf 'plan\n' > "$d/.uncle/docs/BASELINE_REPORT.md"
    ( cd "$d" && git init -q && git add -A && git -c user.name=t -c user.email=t@e.t -c commit.gpgsign=false commit --no-gpg-sign -qm base )
    printf 'x = 2\n' > "$d/scripts/lib/alpha_module.py"
    printf '{"class":"%s","test_scope":"%s","features":{}}\n' "$2" "$3" > "$d/.uncle/workflow/change-class.json"
    echo "$d"
}

# call <dir> [env...] : one run_green_check; the commands it was asked to run are saved in $dir/ran, the report in the .md
call() {
    local d="$1"; shift
    (
        cd "$d"
        for assignment in "$@"; do export "$assignment"; done
        ROOT="$ROOT"; PROJECT_ROOT="$PWD"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"; GREEN_CHECK=1
        CHANGE_CLASS_PY="$ROOT/scripts/lib/change_class.py"
        GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"
        GREEN_CLASS="$STATE_DIR/green-check.tsv"; GREEN_MD="$STATE_DIR/green-check.md"; GREEN_BASE="$STATE_DIR/green-check.baseline.tsv"
        printf 'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh\n' > "$GREEN_CMDS"; : > "$GREEN_BASE"
        resolve_baseline_parallel_groups() { echo groups >> "$STATE_DIR/groups-resolved"; }
        green_run() { cp "$1" "$STATE_DIR/ran"; while IFS= read -r line; do printf '0\t%s\n' "$line"; done < "$1" > "$2"; }
        green_classify() { sed 's/^0\t/PASS\t/' "$2"; }
        green_report() { echo "report" > "$2"; }
        green_regressions() { grep -c '^REGRESSION' "$1" 2>/dev/null || true; }
        . "$ROOT/scripts/lib/change-class-stage.sh"
        . "$TMP/fn.sh"
        run_green_check
    ) 2>&1
}

d="$(new_project small small impacted)"; out="$(call "$d")"
check "small: the python runner runs only its impacted suite" grep -qx 'bash scripts/run-python-tests.sh -- alpha-checks' "$d/.uncle/workflow/ran"
check "small: the shell runner runs only its impacted suite" grep -qx 'bash scripts/run-shell-tests.sh -- alpha-driver' "$d/.uncle/workflow/ran"
check "small: the run says it is scoped" grep -q 'Final check scope: impacted tests only' <<< "$out"
check "small: the report carries the Test scope section" grep -q '^## Test scope' "$d/.uncle/workflow/green-check.md"
check "small: ...and names what was NOT RUN" grep -q 'were NOT RUN' "$d/.uncle/workflow/green-check.md"
check "small: the plan's parallel groups are not applied to a scoped list" test ! -e "$d/.uncle/workflow/groups-resolved"
check "small: the approved commands file (the baseline's) is untouched" test "$(cat "$d/.uncle/workflow/green-check.commands")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'

d="$(new_project risky risky full)"; out="$(call "$d")"
check "risky: the full commands run" test "$(cat "$d/.uncle/workflow/ran")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'
check "risky: there is no scope record" test ! -e "$d/.uncle/workflow/test-scope.json"
check "risky: the report has no scope section" bash -c '! grep -q "Test scope" "$1"' _ "$d/.uncle/workflow/green-check.md"

d="$(new_project forced small impacted)"; call "$d" WORKFLOW_TEST_SCOPE=full > /dev/null
check "WORKFLOW_TEST_SCOPE=full runs everything even for a small change" test "$(cat "$d/.uncle/workflow/ran")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'

d="$(new_project forcedin risky full)"; call "$d" WORKFLOW_TEST_SCOPE=impacted > /dev/null
check "WORKFLOW_TEST_SCOPE=impacted is the operator's override" grep -qx 'bash scripts/run-python-tests.sh -- alpha-checks' "$d/.uncle/workflow/ran"

d="$(new_project unsure small impacted)"; printf 'y = 1\n' > "$d/scripts/lib/orphan_module.py"; ( cd "$d" && git add -A && git -c user.name=t -c user.email=t@e.t -c commit.gpgsign=false commit --no-gpg-sign -qm o )
printf 'y = 2\n' > "$d/scripts/lib/orphan_module.py"
call "$d" > /dev/null
check "an unmapped changed file falls back to the full commands" test "$(cat "$d/.uncle/workflow/ran")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'

d="$(new_project ask standard ask)"; call "$d" > /dev/null
check "standard with no decision runs the full suite" test "$(cat "$d/.uncle/workflow/ran")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'
d="$(new_project askyes standard ask)"; echo impacted > "$d/.uncle/workflow/test-scope-decision"; call "$d" > /dev/null
check "standard with the operator's yes runs the impacted suites" grep -qx 'bash scripts/run-python-tests.sh -- alpha-checks' "$d/.uncle/workflow/ran"
d="$(new_project askno standard ask)"; echo full > "$d/.uncle/workflow/test-scope-decision"; call "$d" > /dev/null
check "standard with the operator's no runs the full suite" test "$(cat "$d/.uncle/workflow/ran")" == $'bash scripts/run-python-tests.sh\nbash scripts/run-shell-tests.sh'

# a scoped run and a full run of the same tree are different checks: the reuse fingerprint must not let one stand in for the other
d="$(new_project reuse small impacted)"; call "$d" > /dev/null; first="$(cut -d' ' -f1 "$d/.uncle/workflow/green-check.fingerprint")"
call "$d" WORKFLOW_TEST_SCOPE=full > "$TMP/second"
check "a full run is not served from the scoped run's cached result" bash -c '! grep -q "reusing that result" "$1"' _ "$TMP/second"
check "...and records a different fingerprint" test "$(cut -d' ' -f1 "$d/.uncle/workflow/green-check.fingerprint")" != "$first"

[[ "$fails" == 0 ]] && echo "test-scope-green-test.sh: all checks passed" || { echo "test-scope-green-test.sh: $fails failure(s)"; exit 1; }
