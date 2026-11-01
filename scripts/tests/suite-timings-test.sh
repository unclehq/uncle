#!/usr/bin/env bash
# The suite runners report how long each suite took, slowest first, and can write the whole table for sorting.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

p="$TMP/p"; mkdir -p "$p/scripts/tests"
printf '#!/usr/bin/env bash\nsleep 2\n' > "$p/scripts/tests/slow-test.sh"
printf '#!/usr/bin/env bash\nsleep 1\n' > "$p/scripts/tests/middle-test.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$p/scripts/tests/fast-test.sh"
printf '#!/usr/bin/env bash\nexit 3\n' > "$p/scripts/tests/broken-test.sh"
printf 'import time\ntime.sleep(1.5)\n' > "$p/scripts/tests/py-slow-test.py"
printf 'print("ok")\n' > "$p/scripts/tests/py-fast-test.py"

WORKFLOW_SUITE_TIMINGS="$TMP/shell.tsv" bash "$ROOT/scripts/run-shell-tests.sh" --project-root "$p" > "$TMP/shell.out" 2>&1
check "the shell run announces its slowest suites" grep -q '^Slowest shell suites:' "$TMP/shell.out"
check "the table is written"                        test -s "$TMP/shell.tsv"
check "every suite that ran has a row"              test "$(wc -l < "$TMP/shell.tsv" | tr -d ' ')" == 4
check "slowest first"                               test "$(head -1 "$TMP/shell.tsv" | cut -f3)" == "scripts/tests/slow-test.sh"
check "the rows are in descending order"            python3 -c "
rows=[float(l.split('\t')[0]) for l in open('$TMP/shell.tsv')]
raise SystemExit(0 if rows==sorted(rows,reverse=True) else 1)"
check "a failing suite keeps its exit status"       grep -q $'\t3\tscripts/tests/broken-test.sh' "$TMP/shell.tsv"
check "durations are wall seconds, not zero"        python3 -c "
rows=dict((l.split('\t')[2].strip(),float(l.split('\t')[0])) for l in open('$TMP/shell.tsv'))
raise SystemExit(0 if rows['scripts/tests/slow-test.sh']>=1.8 and rows['scripts/tests/fast-test.sh']<1.5 else 1)"

WORKFLOW_SUITE_TIMINGS="$TMP/py.tsv" bash "$ROOT/scripts/run-python-tests.sh" --project-root "$p" > "$TMP/py.out" 2>&1
check "the python run reports timings too"          grep -q '^Slowest python suites:' "$TMP/py.out"
check "python: slowest first"                       test "$(head -1 "$TMP/py.tsv" | cut -f3)" == "scripts/tests/py-slow-test.py"

bash "$ROOT/scripts/run-shell-tests.sh" --project-root "$p" > "$TMP/plain.out" 2>&1
check "without the variable nothing is written"     test ! -e "$TMP/never.tsv"
check "the slowest list is still printed"           grep -q '^Slowest shell suites:' "$TMP/plain.out"
[[ $fails == 0 ]] && echo "suite-timings-test.sh: ok"
exit $fails
