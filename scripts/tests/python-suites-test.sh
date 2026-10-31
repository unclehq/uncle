#!/usr/bin/env bash
# run-python-tests.sh: the Python suites, one process each, several at once -- and the shell runner's output, which shares the
# engine, must not change. Fixture projects only; nothing here runs the repository's own suites.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

fixture() {   # name -> a project with passing suites (two that sleep 3 s), one helper that must never run
    local p="$TMP/$1"; mkdir -p "$p/scripts/tests"
    printf 'print("ok")\n' > "$p/scripts/tests/ok-test.py"
    printf 'import time; time.sleep(3)\nprint("slow a")\n' > "$p/scripts/tests/slow-a-test.py"
    printf 'import time; time.sleep(3)\nprint("slow b")\n' > "$p/scripts/tests/slow-b-test.py"
    printf 'open("%s/helper-ran", "w").write("x")\n' "$TMP" > "$p/scripts/tests/helper.py"
    printf 'open("%s/not-a-suite-ran", "w").write("x")\n' "$TMP" > "$p/scripts/tests/notes_test.py"   # wrong suffix: _test, not -test
    echo "$p"
}
now() { python3 -c 'import time; print(time.monotonic())'; }
secs() { python3 -c "print(round($2 - $1, 1))"; }

P="$(fixture pass)"
t0="$(now)"; out="$(bash "$ROOT/scripts/run-python-tests.sh" --project-root "$P" 2>&1)"; rc=$?; t1="$(now)"
check "all passing: exit 0" test "$rc" == 0
check "all passing: python summary, not shell" grep -q '^Python suites: 3 passed, 0 failed, 0 skipped\.$' <<< "$out"
check "all passing: announces what it runs" grep -q '^Running 3 python suites with up to 4 workers\.$' <<< "$out"
check "suites run at once: two 3 s suites take well under 6 s" python3 -c "import sys; sys.exit(0 if $(secs "$t0" "$t1") < 5.0 else 1)"
check "files not named *-test.py are never run" test ! -e "$TMP/helper-ran" -a ! -e "$TMP/not-a-suite-ran"

t0="$(now)"; bash "$ROOT/scripts/run-python-tests.sh" --project-root "$P" --jobs 1 > /dev/null 2>&1; t1="$(now)"
check "--jobs 1 runs them one after another (>= 6 s)" python3 -c "import sys; sys.exit(0 if $(secs "$t0" "$t1") >= 5.8 else 1)"

# A failing suite fails the run, and is named.
F="$(fixture fail)"; printf 'import sys; print("boom"); sys.exit(1)\n' > "$F/scripts/tests/bad-test.py"
out="$(bash "$ROOT/scripts/run-python-tests.sh" --project-root "$F" 2>&1)"; rc=$?
check "a failing suite: exit 1" test "$rc" == 1
check "a failing suite is named with its status" grep -q '^FAIL(1) scripts/tests/bad-test\.py$' <<< "$out"
check "a failing suite: summary counts it" grep -q '^Python suites: 3 passed, 1 failed, 0 skipped\.$' <<< "$out"
check "a failing suite's own output is shown" grep -q '^boom$' <<< "$out"

# Selecting suites by name; bad arguments.
out="$(bash "$ROOT/scripts/run-python-tests.sh" --project-root "$P" -- ok 2>&1)"
check "a named suite runs alone" grep -q '^Python suites: 1 passed, 0 failed, 0 skipped\.$' <<< "$out"
check "a bad suite name is refused" bash -c '! bash "$1" --project-root "$2" -- "Bad_Name" > /dev/null 2>&1' _ "$ROOT/scripts/run-python-tests.sh" "$P"
check "--jobs 0 is refused" bash -c '! bash "$1" --project-root "$2" --jobs 0 > /dev/null 2>&1' _ "$ROOT/scripts/run-python-tests.sh" "$P"
check "an unknown flag is refused with the usage line" bash -c '[[ "$(bash "$1" --nope 2>&1)" == *"Usage: bash scripts/run-python-tests.sh"* ]]' _ "$ROOT/scripts/run-python-tests.sh"
mkdir -p "$TMP/empty/scripts/tests"
check "a project with no suites fails" bash -c '! bash "$1" --project-root "$2" > /dev/null 2>&1' _ "$ROOT/scripts/run-python-tests.sh" "$TMP/empty"

# The shell runner shares the engine; its output must be what it always was (a local variable once shadowed the new
# parameter and turned its summary into "Pass suites:").
S="$TMP/shell"; mkdir -p "$S/scripts/tests"; printf '#!/usr/bin/env bash\nexit 0\n' > "$S/scripts/tests/ok-test.sh"
out="$(bash "$ROOT/scripts/run-shell-tests.sh" --project-root "$S" 2>&1)"
check "shell runner: its announcement is unchanged" grep -q '^Running 1 shell suites with up to 4 workers\.$' <<< "$out"
check "shell runner: its summary is unchanged" grep -q '^Shell suites: 1 passed, 0 failed, 0 skipped\.$' <<< "$out"

[[ "$fails" == 0 ]] && echo "python-suites-test.sh: all checks passed" || { echo "python-suites-test.sh: $fails failure(s)"; exit 1; }
