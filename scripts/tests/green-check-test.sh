#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/lib/green-check.sh — the independent verification
# run that stops the implementation stage from being the only witness to its
# own test results.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/green-check.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0

fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    if [[ "$actual" != "$expected" ]]; then
        fail "$name — expected '$expected', got '$actual'"
    fi
}

check_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if ! grep -qF "$needle" "$file"; then
        fail "$name — expected to find: $needle"
        sed 's/^/    /' < "$file"
    fi
}

check_not_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if grep -qF "$needle" "$file"; then
        fail "$name — did not expect to find: $needle"
        sed 's/^/    /' < "$file"
    fi
}

# --- verify_commands: the approved command block ---------------------------

DOC="$TMP/BASELINE_REPORT.md"
cat > "$DOC" <<'EOF'
# Baseline Report

## 7. Existing automated-test coverage

Example of how someone might run one suite:

```
this is prose in a block that is not the command section
```

## 8. Exact build and test commands executed

```
make test
$ npm run lint
# a comment, not a command

  bash -n scripts/*.sh
```

No build step exists.

## 9. Baseline test results

```
make test: 12 passed
```
EOF

check_eq "commands come from the named section only" \
    "make test npm run lint bash -n scripts/*.sh " \
    "$(verify_commands "$DOC" | tr '\n' ' ')"

check_eq "no commands section: nothing to run" "" \
    "$(printf '# Report\n\nNo commands here.\n' > "$TMP/bare.md"; verify_commands "$TMP/bare.md")"

check_eq "missing file: nothing to run" "" "$(verify_commands "$TMP/nope.md")"

# The new-application pipeline names its section differently.
cat > "$TMP/UPDATED_PROJECT_PLAN.md" <<'EOF'
# Updated Project Plan

## Verification commands

```
pytest -q
ruff check .
```

## Non-goals
EOF
check_eq "the plan's own heading is recognised" "pytest -q ruff check . " \
    "$(verify_commands "$TMP/UPDATED_PROJECT_PLAN.md" | tr '\n' ' ')"

# A block that is never closed must not swallow the rest of the document.
cat > "$TMP/unclosed.md" <<'EOF'
## Verification commands

```
make test
EOF
check_eq "an unclosed block still yields its commands" "make test" \
    "$(verify_commands "$TMP/unclosed.md")"

# --- green_run: statuses are recorded, not reported ------------------------

CMDS="$TMP/cmds"
cat > "$CMDS" <<'EOF'
true
false
sh -c 'exit 3'
cat
EOF

green_run "$CMDS" "$TMP/run.tsv" "$TMP/run.log" > "$TMP/run.out"

check_eq "one row per command" "4" "$(grep -c . "$TMP/run.tsv")"
check_eq "a passing command records 0"  "0" "$(awk -F'\t' '$2 == "true"  {print $1}' "$TMP/run.tsv")"
check_eq "a failing command records 1"  "1" "$(awk -F'\t' '$2 == "false" {print $1}' "$TMP/run.tsv")"
check_eq "the real exit status is kept" "3" "$(awk -F'\t' '$2 ~ /exit 3/ {print $1}' "$TMP/run.tsv")"

# `cat` with an open stdin would consume the rest of the command list; the
# fourth row existing at all is the assertion that it did not.
check_eq "a command that reads stdin cannot eat the list" "0" \
    "$(awk -F'\t' '$2 == "cat" {print $1}' "$TMP/run.tsv")"

check_contains "the log keeps the command" '$ false' "$TMP/run.log"
check_contains "progress names the failure" "FAIL(3)" "$TMP/run.out"
check_contains "progress names the pass" "PASS      true" "$TMP/run.out"

# --- green_classify: a pre-existing failure is not this change's fault -----

printf '0\tmake test\n1\tshellcheck .\n0\tmake lint\n' > "$TMP/base.tsv"
printf '1\tmake test\n1\tshellcheck .\n0\tmake lint\n1\tnew-check\n' > "$TMP/cur.tsv"

green_classify "$TMP/base.tsv" "$TMP/cur.tsv" > "$TMP/class.tsv"

check_eq "green before, red now, is a regression" "REGRESSION" \
    "$(awk -F'\t' '$2 == "make test" {print $1}' "$TMP/class.tsv")"
check_eq "red before and still red is pre-existing" "PREEXISTING" \
    "$(awk -F'\t' '$2 == "shellcheck ." {print $1}' "$TMP/class.tsv")"
check_eq "green throughout is a pass" "PASS" \
    "$(awk -F'\t' '$2 == "make lint" {print $1}' "$TMP/class.tsv")"
check_eq "a command with no baseline that fails is a regression" "REGRESSION" \
    "$(awk -F'\t' '$2 == "new-check" {print $1}' "$TMP/class.tsv")"
check_eq "two regressions counted" "2" "$(green_regressions "$TMP/class.tsv")"

# Fixing a pre-existing failure is visible, and is not a regression.
printf '0\tshellcheck .\n' > "$TMP/fixed.tsv"
check_eq "red before, green now, is fixed" "FIXED" \
    "$(green_classify "$TMP/base.tsv" "$TMP/fixed.tsv" | cut -f1)"

# With no baseline at all, every failure blocks. An unrecorded baseline is not
# evidence of a prior failure.
check_eq "no baseline: every failure is a regression" "3" \
    "$(green_classify "$TMP/absent.tsv" "$TMP/cur.tsv" | grep -c '^REGRESSION' || true)"
check_eq "no classified rows: no regressions" "0" "$(green_regressions "$TMP/absent.tsv")"

# --- green_report ----------------------------------------------------------

green_report "$TMP/class.tsv" "$TMP/green.md" BASELINE_REPORT.md .uncle/workflow/logs/green-check.log

check_contains "report names the regressed command" "make test" "$TMP/green.md"
check_contains "report states the regression count" "2 command(s) regressed" "$TMP/green.md"
check_contains "report names its source document" "BASELINE_REPORT.md" "$TMP/green.md"

green_report "$TMP/fixed.tsv.class" "$TMP/notrun.md" BASELINE_REPORT.md /dev/null
check_contains "nothing to run is reported as NOT RUN" "NOT RUN" "$TMP/notrun.md"
check_not_contains "NOT RUN is never rendered as a pass" "No regressions" "$TMP/notrun.md"

# With no baseline, a failure is a failure: "regressed" would claim something
# about a past that never existed.
green_report "$TMP/class.tsv" "$TMP/nobase.md" UPDATED_PROJECT_PLAN.md log 0
check_contains "no baseline: failures are reported as failures" \
    "2 command(s) failed." "$TMP/nobase.md"
check_not_contains "no baseline: nothing is said to have regressed" \
    "regressed" "$TMP/nobase.md"
check_contains "no baseline: the row label is FAIL" "| FAIL |" "$TMP/nobase.md"

green_classify "$TMP/base.tsv" "$TMP/fixed.tsv" > "$TMP/clean.tsv"
green_report "$TMP/clean.tsv" "$TMP/clean.md" BASELINE_REPORT.md log
check_contains "a clean run says so" "No regressions" "$TMP/clean.md"

# Driver-run tests must not inherit the live project or UI channel.
printf '%s\n' 'test -z "${UNCLE_PROJECT_ROOT:-}${UNCLE_STATUS_FILE:-}${UNCLE_CONFIG:-}${STAGEGATE_ORIGIN_ISSUE:-}"' > "$TMP/isolated.commands"
UNCLE_PROJECT_ROOT="$TMP/live" UNCLE_STATUS_FILE="$TMP/status" UNCLE_CONFIG="$TMP/config" STAGEGATE_ORIGIN_ISSUE=6 \
    green_run "$TMP/isolated.commands" "$TMP/isolated.tsv" "$TMP/isolated.log" > "$TMP/isolated.out"
check_contains "child checks receive no live workflow settings" "PASS" "$TMP/isolated.out"

# Invalid model-generated scheduling falls back before approval; commands stay exact.
cat > "$TMP/plan.md" <<'PLAN'
## Parallel verification groups

```text
2 4 5
```

## Verification commands

```sh
printf one
printf two
printf three
```
PLAN
verify_commands "$TMP/plan.md" > "$TMP/commands.before"
(cd "$TMP" && repair_parallel_groups plan.md commands.before) > "$TMP/repair.out" 2>&1
verify_commands "$TMP/plan.md" > "$TMP/commands.after"
COUNT=$((COUNT + 1))
cmp "$TMP/commands.before" "$TMP/commands.after" || fail "repair changed commands"
COUNT=$((COUNT + 1))
verify_parallel_groups "$TMP/plan.md" "$TMP/commands.after" > "$TMP/groups" || fail "serial fallback invalid"
check_eq "fallback has no parallel groups" "" "$(cat "$TMP/groups")"
check_contains "fallback is explained" "commands will run serially" "$TMP/repair.out"

# --- a command written across lines runs whole, not in fragments ------------
# `sh -c '` ... `'` used to be split per line: the first and last lines failed
# on their own and the lines between ran as top-level commands.

cat > "$TMP/MULTILINE_PLAN.md" <<'PLAN'
## Verification commands

```sh
sh -c '
  set -e
  echo inside-quotes >> "$MARK"
  if true; then
    echo nested >> "$MARK"
  fi
'
echo second >> "$MARK"
for i in 1 2; do
  echo "loop $i" >> "$MARK"
done
```
PLAN
verify_commands "$TMP/MULTILINE_PLAN.md" > "$TMP/multi.commands"
check_eq "multi-line: three commands, not nine fragments" "3" "$(wc -l < "$TMP/multi.commands" | tr -d ' ')"
export MARK="$TMP/multi.mark"; : > "$MARK"
(cd "$TMP" && green_run "$TMP/multi.commands" "$TMP/multi.tsv" "$TMP/multi.log") > /dev/null
check_eq "multi-line: every command passes" "0 0 0" "$(cut -f1 "$TMP/multi.tsv" | tr '\n' ' ' | sed 's/ $//')"
check_eq "multi-line: the script ran as written" "inside-quotes nested second loop 1 loop 2" "$(tr '\n' ' ' < "$MARK" | sed 's/ $//')"
printf '%s\n' "sh -c 'unterminated" "echo ok" > "$TMP/broken.commands"
check_eq "an unterminated quote is left for the shell to report" "$(cat "$TMP/broken.commands")" "$(python3 "$ROOT/scripts/lib/fold_shell_commands.py" < "$TMP/broken.commands")"

# --- a check that waits forever is ended, not waited on ----------------------
# A test runner probing a port that something else holds open without answering
# hung a run for good: the sequential loop had no time limit.

printf '%s\n' 'echo before' 'sleep 60' 'echo after' > "$TMP/hang.commands"
started=$SECONDS
(cd "$TMP" && WORKFLOW_CHECK_TIMEOUT_SECONDS=2 green_run "$TMP/hang.commands" "$TMP/hang.tsv" "$TMP/hang.log") > /dev/null
check_eq "hang: the loop finished promptly" yes "$([[ $((SECONDS - started)) -lt 30 ]] && echo yes || echo no)"
check_eq "hang: the stuck command is a failure with the timeout status" "0 124 0" "$(cut -f1 "$TMP/hang.tsv" | tr '\n' ' ' | sed 's/ $//')"
check_contains "hang: the log says it timed out" "TIMEOUT after 2s" "$TMP/hang.log"
check_not_contains "hang: nothing after the sleep ran inside it" "never" "$TMP/hang.log"

# --- a failing command in a pipeline is a failure -----------------------------
# `npx playwright test … | tee out.log` reported PASS when Playwright failed: the
# pipeline's status was tee's.  A plan's own `set -o pipefail` on an earlier line
# never reaches the shell that runs the next line.

printf '%s\n' 'false | tee /dev/null' 'true | tee /dev/null' 'sh -c "exit 7" | cat' > "$TMP/pipe.commands"
(cd "$TMP" && green_run "$TMP/pipe.commands" "$TMP/pipe.tsv" "$TMP/pipe.log") > /dev/null
check_eq "pipefail: a failing command before tee fails the check" "1 0 7" "$(cut -f1 "$TMP/pipe.tsv" | tr '\n' ' ' | sed 's/ $//')"

if [[ "$FAILED" -ne 0 ]]; then
    echo "green-check-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "green-check-test.sh: $COUNT checks passed"
