#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/lib/triage.sh: the failure bundle (AC-1..AC-5).
#
# Bundles are built in scratch project directories. The exit filter is driven
# through the same EXIT-trap shape the drivers install, and once through each
# real driver, because the hook that matters is the one the driver runs.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/triage.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# No stage may reach a real runner from a test: every stage command is a stub that fails.
export UNCLE_CONFIG=/dev/null WORKFLOW_AGENT_CMD=/usr/bin/false WORKFLOW_REVIEWER_CMD=/usr/bin/false WORKFLOW_CODEX_CMD=/usr/bin/false
unset UNCLE_STATUS_STAGE UNCLE_DRIVER_SUPERVISED UNCLE_PROJECT_ROOT 2>/dev/null || true

FAILED=0
COUNT=0
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    [[ "$actual" == "$expected" ]] || fail "$name — expected '$expected', got '$actual'"
}
check_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    grep -qF -- "$needle" "$file" || fail "$name — expected to find: $needle"
}
check_not_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if grep -qF -- "$needle" "$file"; then fail "$name — did not expect: $needle"; fi
}
check_le() {
    local name="$1" actual="$2" cap="$3"
    COUNT=$((COUNT + 1))
    [[ "$actual" -le "$cap" ]] || fail "$name — $actual exceeds $cap"
}

fresh() {
    local dir="$TMP/$1"
    rm -rf "$dir"
    mkdir -p "$dir/.uncle/workflow/logs"
    printf '%s' "$dir"
}

# --- AC-1: every section, present or MISSING ---------------------------------

P="$(fresh full)"
cd "$P"
printf '42:IMPLEMENT\n' > .uncle/workflow/state
printf '2\n' > .uncle/workflow/repair-count
printf 'VERIFICATION_REPORT.md\n' > .uncle/workflow/repair-source
printf '## Green check\n\nall green\n' > .uncle/workflow/green-check.md
printf '{"type":"assistant","text":"exec log line"}\n' > .uncle/workflow/logs/execute-checklist.jsonl
printf '# notes\nSee AC-3.\n' > IMPLEMENTATION_NOTES.md
printf '# report\n| MC-2 | FAIL | see AC-1 |\n' > VERIFICATION_REPORT.md
printf '| ID | Criterion |\n|---|---|\n| AC-1 | first |\n| AC-2 | second |\n| AC-3 | third |\n' > CHANGE_SPEC.md
printf '| `MC-2` | check two |\n| MC-9 | check nine |\n' > MANUAL_CHECKLIST.md
TRIAGE_EXIT_STATUS=1 write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
B=.uncle/workflow/TRIAGE.md
check_contains "state token" "- state: IMPLEMENT" "$B"
check_contains "exit status" "- exit status: 1" "$B"
check_contains "failing stage from newest log" "- failing stage: execute-checklist" "$B"
check_contains "repair-count" "- repair-count: 2" "$B"
check_contains "repair-source" "- repair-source: VERIFICATION_REPORT.md" "$B"
check_contains "log tail section" "## Stage log tail: execute-checklist" "$B"
check_contains "log tail content" "exec log line" "$B"
check_contains "mapped report" "## VERIFICATION_REPORT.md" "$B"
check_contains "mapped report content" "| MC-2 | FAIL | see AC-1 |" "$B"
check_contains "notes embedded" "## IMPLEMENTATION_NOTES.md" "$B"
check_contains "green-check embedded" "all green" "$B"
check_contains "unmapped DEFECTS marked missing" "MISSING: DEFECTS.md" "$B"
check_contains "cited rows heading" "## Cited plan rows" "$B"
check_contains "cited AC-1 row" "CHANGE_SPEC.md: | AC-1 | first |" "$B"
check_not_contains "uncited AC-2 absent" "| AC-2 | second |" "$B"
check_not_contains "notes citation not counted as failing report" "| AC-3 | third |" "$B"

# Same layout, every input absent: each section says MISSING, never an error.
P="$(fresh empty)"
cd "$P"
TRIAGE_EXIT_STATUS=42 write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
check_contains "empty: state missing" "- state: MISSING" "$B"
check_contains "empty: stage missing" "- failing stage: MISSING" "$B"
check_contains "empty: log missing" "MISSING: no stage log" "$B"
check_contains "empty: reports missing" "MISSING: no report is mapped" "$B"
check_contains "empty: notes missing" "MISSING: IMPLEMENTATION_NOTES.md" "$B"
check_contains "empty: green missing" "MISSING: .uncle/workflow/green-check.md" "$B"
check_contains "empty: rows missing" "MISSING: no plan ids cited" "$B"

# UNCLE_STATUS_STAGE wins over the newest log.
P="$(fresh status)"
cd "$P"
printf 'old\n' > .uncle/workflow/logs/baseline.jsonl
sleep 1
printf 'new\n' > .uncle/workflow/logs/final-audit.jsonl
UNCLE_STATUS_STAGE=baseline write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
check_contains "UNCLE_STATUS_STAGE names the stage" "- failing stage: baseline" "$B"
check_contains "status stage maps to its report" "MISSING: BASELINE_REPORT.md" "$B"

# CLI form used by the TUI.
out="$(bash "$ROOT/scripts/lib/triage.sh" --write --state-dir .uncle/workflow --out "$P/cli.md")"
check_eq "cli prints the path" "$P/cli.md" "$out"
check_contains "cli bundle written" "# Triage bundle" "$P/cli.md"

# --- AC-2: caps ----------------------------------------------------------------

P="$(fresh caps)"
cd "$P"
seq 1 1000 | sed 's/^/logline-/' > .uncle/workflow/logs/implementation.jsonl
head -c 40000 /dev/zero | tr '\0' 'x' > IMPLEMENTATION_NOTES.md
printf '\nAC-1 AC-2\n' >> IMPLEMENTATION_NOTES.md
{
    for i in $(seq 1 100); do printf '| AC-1 | row %s |\n' "$i"; done
} > CHANGE_PLAN.md
write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
check_eq "log tail is 200 lines" 200 "$(grep -c '^logline-' "$B")"
check_contains "log tail marker" "[TRUNCATED: .uncle/workflow/logs/implementation.jsonl has 1000 lines; last 200 shown]" "$B"
check_contains "last log line kept" "logline-1000" "$B"
check_eq "first log line dropped" 0 "$(grep -cx 'logline-1' "$B" || true)"
check_contains "file cap marker" "[TRUNCATED: IMPLEMENTATION_NOTES.md is 40011 bytes; first 16384 shown]" "$B"
check_le "embedded file under cap" "$(awk '/^## IMPLEMENTATION_NOTES.md/{f=1;next} /^## /{f=0} f' "$B" | wc -c | tr -d ' ')" 16600
check_eq "cited rows capped at 60" 60 "$(grep -c '^CHANGE_PLAN.md: | AC-1 |' "$B")"
check_contains "row cap marker" "[TRUNCATED: more than 60 cited rows]" "$B"

# Total cap: six reports each near the file cap add up past 96 KiB.
P="$(fresh total)"
cd "$P"
printf 'x\n' > .uncle/workflow/logs/implementation.jsonl
for f in IMPLEMENTATION_NOTES.md AUTOMATED_TEST_REPORT.md CHANGE_TEST_REPORT.md; do
    head -c 16300 /dev/zero | tr '\0' 'y' > "$f"
done
head -c 16300 /dev/zero | tr '\0' 'z' > .uncle/workflow/green-check.md
printf '\nAC-1\n' >> IMPLEMENTATION_NOTES.md
{ for i in $(seq 1 60); do printf '| AC-1 | %s |\n' "$(head -c 900 /dev/zero | tr '\0' 'r')"; done; } > CHANGE_PLAN.md
write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
check_le "total bundle under 96 KiB" "$(wc -c < "$B" | tr -d ' ')" 98304
check_contains "total cap marker" "[TRUNCATED: bundle was" "$B"

# Performance: a 10 MiB log is tailed, not read.
P="$(fresh perf)"
cd "$P"
head -c 10485760 /dev/zero | tr '\0' '\n' | sed 's/^/line/' > .uncle/workflow/logs/baseline.jsonl 2>/dev/null || \
    yes 'baseline log line' | head -c 10485760 > .uncle/workflow/logs/baseline.jsonl
start=$SECONDS
write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
check_le "10 MiB log bundles in under 2 s" "$((SECONDS - start))" 2

# --- AC-3: cited rows only, exact-id matching ----------------------------------

P="$(fresh cited)"
cd "$P"
printf 'x\n' > .uncle/workflow/logs/test-review.jsonl
printf 'Rows: AC-1, I-2, MC-3 and R-4. Not SAC-1, AC-12x, ZZ-1.\n' > TEST_REVIEW.md
printf '| AC-1 | spec one |\n| AC-12 | spec twelve |\n| I-2 | inv two |\n| ZZ-1 | never |\n' > CHANGE_SPEC.md
printf '| MC-3 | plan mc |\n| R-4 | plan r |\n| S-9 | plan s |\n' > UPDATED_PROJECT_PLAN.md
write_triage .uncle/workflow .uncle/workflow/TRIAGE.md
for want in "| AC-1 | spec one |" "| I-2 | inv two |" "| MC-3 | plan mc |" "| R-4 | plan r |"; do
    check_contains "cited: $want" "$want" "$B"
done
for nope in "| AC-12 | spec twelve |" "| ZZ-1 | never |" "| S-9 | plan s |"; do
    check_not_contains "uncited: $nope" "$nope" "$B"
done

# --- AC-4: the exit filter -------------------------------------------------------

# The trap shape the drivers install: capture $? first, then the hook.
hook_script="$TMP/hook.sh"
cat > "$hook_script" <<EOF
#!/usr/bin/env bash
. "$ROOT/scripts/lib/triage.sh"
STATE_DIR=.uncle/workflow
on_exit() { local rc=\$?; triage_on_exit "\$rc"; }
trap on_exit EXIT
exit "\$1"
EOF

for rc in 0 130 143 137; do
    P="$(fresh "exit$rc")"; cd "$P"
    printf 'x\n' > .uncle/workflow/logs/baseline.jsonl
    bash "$hook_script" "$rc" || true
    COUNT=$((COUNT + 1))
    [[ ! -e .uncle/workflow/TRIAGE.md ]] || fail "exit $rc wrote TRIAGE.md"
done
for rc in 1 42; do
    P="$(fresh "exit$rc")"; cd "$P"
    printf 'x\n' > .uncle/workflow/logs/baseline.jsonl
    status=0; bash "$hook_script" "$rc" || status=$?
    check_eq "exit $rc status preserved" "$rc" "$status"
    check_contains "exit $rc wrote TRIAGE.md" "- exit status: $rc" .uncle/workflow/TRIAGE.md
done

# A stop the operator chose is not a failure.
P="$(fresh human)"; cd "$P"
printf 'human\n' > .uncle/workflow/stop-reason
status=0; bash "$hook_script" 1 || status=$?
check_eq "human stop keeps exit 1" 1 "$status"
COUNT=$((COUNT + 1))
[[ ! -e .uncle/workflow/TRIAGE.md ]] || fail "stop-reason=human wrote TRIAGE.md"

# Any other stop reason is still a failure.
printf 'stage\n' > .uncle/workflow/stop-reason
bash "$hook_script" 1 || true
check_contains "non-human stop-reason still bundles" "- stop reason: stage" .uncle/workflow/TRIAGE.md

# The write cannot change the exit status: an unwritable state dir is one
# stderr line and the same status.
P="$(fresh ro)"; cd "$P"
chmod 555 .uncle/workflow
status=0; err="$(bash "$hook_script" 1 2>&1)" || status=$?
chmod 755 .uncle/workflow
check_eq "unwritable bundle keeps exit 1" 1 "$status"
check_eq "unwritable bundle says so once" "triage: could not write .uncle/workflow/TRIAGE.md" "$err"

# Each real driver, failing before any stage: bundle written, status kept.
P="$(fresh driver-change)"; cd "$P"; git init -q .; git config commit.gpgsign false; git config tag.gpgsign false
status=0
UNCLE_PROJECT_ROOT="$P" bash "$ROOT/scripts/change-workflow.sh" < /dev/null > "$TMP/cw.out" 2>&1 || status=$?
check_eq "change-workflow failure exits 1" 1 "$status"
check_contains "change-workflow failure writes TRIAGE.md" "- exit status: 1" .uncle/workflow/TRIAGE.md

P="$(fresh driver-stagegate)"; cd "$P"; git init -q .; git config commit.gpgsign false; git config tag.gpgsign false
printf 'NOT_A_STATE\n' > .uncle/workflow/state
status=0
UNCLE_PROJECT_ROOT="$P" bash "$ROOT/scripts/stagegate.sh" < /dev/null > "$TMP/sg.out" 2>&1 || status=$?
check_eq "stagegate failure exits 1" 1 "$status"
check_contains "stagegate failure writes TRIAGE.md" "- state: NOT_A_STATE" .uncle/workflow/TRIAGE.md

# A declined gate is exit 0 and writes nothing (stagegate reaches its first gate).
P="$(fresh driver-decline)"; cd "$P"; git init -q .; git config commit.gpgsign false; git config tag.gpgsign false
printf 'WAIT_REQUIREMENTS_APPROVAL\n' > .uncle/workflow/state
printf '# interp\n' > REQUIREMENTS_INTERPRETATION.md
status=0
printf 'n\n' | UNCLE_PROJECT_ROOT="$P" bash "$ROOT/scripts/stagegate.sh" > "$TMP/sg2.out" 2>&1 || status=$?
check_eq "declined gate exits 0" 0 "$status"
COUNT=$((COUNT + 1))
[[ ! -e .uncle/workflow/TRIAGE.md ]] || fail "declined gate wrote TRIAGE.md"

# --- AC-5: the ten CR failures, each with its own evidence in the bundle --------

# fixture <name> <stage> <log text> <report> <report text> [state]
fixture() {
    local name="$1" stage="$2" log="$3" report="$4" text="$5" state="${6:-IMPLEMENT}"
    P="$(fresh "f-$name")"; cd "$P"
    printf '%s\n' "$state" > .uncle/workflow/state
    printf '%s\n' "$log" > ".uncle/workflow/logs/$stage.jsonl"
    [[ -z "$report" ]] || printf '%s\n' "$text" > "$report"
}

fixture F1 adversarial-review 'jq: error (at <stdin>:12): Cannot iterate over null' ADVERSARIAL_REVIEW.md '# review'
write_triage .uncle/workflow "$B"
check_contains "F1 jq parse error" "jq: error (at <stdin>:12): Cannot iterate over null" "$B"

fixture F2 final-audit 'commit 3f2a9c signed with wrong parent; retrying signature (attempt 4)' FINAL_AUDIT.md '# audit'
write_triage .uncle/workflow "$B"
check_contains "F2 wrong-parent commit loop" "signed with wrong parent; retrying signature (attempt 4)" "$B"

fixture F3 baseline 'ConnectionRefusedError: [Errno 61] Connection refused (http://127.0.0.1:11434/v1)' BASELINE_REPORT.md '# baseline'
write_triage .uncle/workflow "$B"
check_contains "F3 self-hosted endpoint refused" "Connection refused (http://127.0.0.1:11434/v1)" "$B"

fixture F4 requirements "early-prerequisites: REQUIREMENTS.md row 'Goal' is empty (EMPTY ROW)" REQUIREMENTS_INTERPRETATION.md '| Goal | EMPTY ROW |' REQUIREMENTS
write_triage .uncle/workflow "$B"
check_contains "F4 empty requirement rows" "row 'Goal' is empty (EMPTY ROW)" "$B"

fixture F5 preflight "PREFLIGHT_REPORT.md: acceptance id 'AC 3' contains whitespace" PREFLIGHT_REPORT.md "| AC 3 | PASS |"
write_triage .uncle/workflow "$B"
check_contains "F5 id with spaces (preflight)" "acceptance id 'AC 3' contains whitespace" "$B"

fixture F6 test-review "TEST_REVIEW.md rejected: row id 'MC 7' has spaces" TEST_REVIEW.md "| MC 7 | COVERAGE |"
write_triage .uncle/workflow "$B"
check_contains "F6 id with spaces (test-review)" "row id 'MC 7' has spaces" "$B"

fixture F7 repair 'Repair limit (3) reached. Inspect VERIFICATION_REPORT.md.' IMPLEMENTATION_NOTES.md '# notes' REPAIR
printf '3\n' > .uncle/workflow/repair-count
printf 'VERIFICATION_REPORT.md\n' > .uncle/workflow/repair-source
printf '| MC-1 | FAIL |\n' > VERIFICATION_REPORT.md
write_triage .uncle/workflow "$B"
check_contains "F7 repair limit text" "Repair limit (3) reached" "$B"
check_contains "F7 repair-count" "- repair-count: 3" "$B"
check_contains "F7 repair-source embedded" "| MC-1 | FAIL |" "$B"

fixture F8 test-review 'defect-injection: 0 of 3 injected defects detected; tolerance 3' TEST_REVIEW.md '| NEGATIVE | FAIL | 0 of 3 injected defects detected |' TEST_REVIEW
write_triage .uncle/workflow "$B"
check_contains "F8 defect injection" "0 of 3 injected defects detected" "$B"

fixture F9 implementation 'Implementation remains incomplete: required delivery is missing.' IMPLEMENTATION_NOTES.md '| AC-4 | BLOCKED | none | live endpoint unavailable |'
printf '| AC-4 | live check |\n' > CHANGE_SPEC.md
write_triage .uncle/workflow "$B"
check_contains "F9 BLOCKED acceptance row" "| AC-4 | BLOCKED | none | live endpoint unavailable |" "$B"
check_contains "F9 cited spec row" "CHANGE_SPEC.md: | AC-4 | live check |" "$B"

fixture F10 execute-checklist 'MC-5 FAIL: expected 200, got 500 from /health' VERIFICATION_REPORT.md '| MC-5 | FAIL | expected 200, got 500 from /health |' EXECUTE_CHECKLIST
printf '| MC-5 | health endpoint |\n' > UPDATED_PROJECT_PLAN.md
write_triage .uncle/workflow "$B"
check_contains "F10 report slice" "expected 200, got 500 from /health" "$B"
check_contains "F10 cited plan row" "UPDATED_PROJECT_PLAN.md: | MC-5 | health endpoint |" "$B"

cd "$ROOT"
if [[ "$FAILED" -ne 0 ]]; then
    echo "triage-bundle-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "triage-bundle-test.sh: $COUNT checks passed"
