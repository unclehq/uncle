#!/usr/bin/env bash
# Uncle's own baseline records two commands -- the shell runner and the Python runner -- as one parallel group, and never
# `unittest discover`, which runs zero tests on hyphenated file names. The prompt says so, AGENTS.md says so, and the driver
# accepts exactly the group the prompt tells the model to write.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
prompt="$ROOT/prompts/change/baseline.md"

check "the baseline prompt names the Python runner" grep -q 'bash scripts/run-python-tests.sh' "$prompt"
check "it warns off unittest discover and says why" bash -c 'grep -q "unittest discover" "$1" && grep -q "NO TESTS RAN" "$1"' _ "$prompt"
check "it tells the model to declare the pair as one group" bash -c 'grep -q "parallel_groups" "$1" && grep -q "\`1 2\`" "$1"' _ "$prompt"
check "it says new Python tests are hyphenated" grep -q 'scripts/tests/<name>-test.py' "$prompt"
check "AGENTS.md carries the same instruction" bash -c 'grep -q "run-python-tests.sh" "$1" && grep -q "NO TESTS RAN" "$1"' _ "$ROOT/AGENTS.md"
check "CONTRIBUTING.md documents the runner" grep -q 'run-python-tests.sh' "$ROOT/CONTRIBUTING.md"
check "the shell runner's own instruction is still there" grep -q 'bash scripts/run-shell-tests.sh' "$prompt"

# The driver accepts the group the prompt tells the model to write, for those two commands.
. "$ROOT/scripts/lib/green-check.sh"
printf 'bash scripts/run-shell-tests.sh\nbash scripts/run-python-tests.sh\n' > "$TMP/commands"
cat > "$TMP/report" <<'REPORT'
# Baseline report

## Parallel verification groups

```text
1 2
```
REPORT
resolve_baseline_parallel_groups "$TMP/report" "$TMP/commands" "$TMP/groups" 2> "$TMP/err"
check "the driver accepts '1 2' for the two commands" test "$(cat "$TMP/groups")" == "1 2"
check "and says nothing about invalid groups" test ! -s "$TMP/err"
printf '1 3\n' > /dev/null
sed -i.bak 's/^1 2$/1 5/' "$TMP/report" && rm -f "$TMP/report.bak"
resolve_baseline_parallel_groups "$TMP/report" "$TMP/commands" "$TMP/groups2" 2> "$TMP/err2"
check "a group naming a command that is not there is refused, and the run stays sequential" test ! -s "$TMP/groups2" -a -s "$TMP/err2"

[[ "$fails" == 0 ]] && echo "baseline-python-runner-test.sh: all checks passed" || { echo "baseline-python-runner-test.sh: $fails failure(s)"; exit 1; }
