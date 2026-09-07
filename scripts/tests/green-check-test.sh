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

green_report "$TMP/class.tsv" "$TMP/green.md" BASELINE_REPORT.md .uncle/workspace/logs/green-check.log

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

if [[ "$FAILED" -ne 0 ]]; then
    echo "green-check-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "green-check-test.sh: $COUNT checks passed"
