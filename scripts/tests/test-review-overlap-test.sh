#!/usr/bin/env bash
# run_test_review_investigate / run_test_review_panel: the plan/source-only
# half of test review starts the moment implementation finishes, concurrently
# with the driver's background verification, instead of the whole stage
# sitting idle waiting for green-check to publish before any review work
# begins. The finalize pass (run_test_review_panel) must still never decide a
# row's status without real results -- it only reuses the early investigation
# text, never a verdict.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected [$2] got [$3]"; fi; }

sed -n '/^run_test_review_investigate() {/,/^run_manual_checklist_panel() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/fns.sh"
grep -q '^run_test_review_investigate() {' "$temp/fns.sh" || { echo 'FATAL: could not extract run_test_review_investigate'; exit 2; }
grep -q '^run_test_review_panel() {' "$temp/fns.sh" || { echo 'FATAL: could not extract run_test_review_panel'; exit 2; }

STATE_DIR="$temp/project/.uncle/workflow"
LOG_DIR="$STATE_DIR/logs"
GREEN_MD="$temp/project/green-check.md"
mkdir -p "$STATE_DIR/documents" "$LOG_DIR" "$temp/project/.uncle/docs"
cd "$temp/project"
printf '# Project plan\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md

upper() { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }

# A call log lets each test assert what ran and in what prompt content,
# without caring about real model behavior.
calls_file="$temp/calls"
: > "$calls_file"
# run_codex_review PROMPT OUTPUT LOG_NAME -- stub: records the call and
# writes a canned response shaped like whichever phase asked for it.
run_codex_review() {
    local prompt="$1" output="$2" log_name="$3"
    printf '%s\t%s\n' "$log_name" "$prompt" >> "$calls_file"
    case "$log_name" in
        *-investigate)
            printf '# Investigation\n\nSource looks correct for %s.\n' "$log_name" > "$output"
            ;;
        *-retry)
            printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"COVERAGE","status":"PASS","evidence":"retry"}]}' > "$output"
            ;;
        *)
            # The finalize pass: a real worker would read results itself;
            # the stub just proves the investigation text reached its prompt.
            local lens="${log_name#test-review-worker-}"
            case "$lens" in
                coverage) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"COVERAGE","status":"PASS","evidence":"e"}]}' > "$output" ;;
                assertions) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"ASSERTIONS","status":"PASS","evidence":"e"}]}' > "$output" ;;
                oracle) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"ORACLE","status":"PASS","evidence":"e"},{"id":"NEGATIVE","status":"PASS","evidence":"e"}]}' > "$output" ;;
            esac
            ;;
    esac
}
# shellcheck disable=SC1090
source "$temp/fns.sh"

# --- phase 1 starts immediately and does not wait on anything -------------
run_test_review_investigate
# run_test_review_investigate itself must not block -- confirmed implicitly
# by it returning here at all with workers still possibly in flight -- but
# this test still needs their result files before asserting on them.
while IFS= read -r bgpid; do [[ -z "$bgpid" ]] || wait "$bgpid" 2>/dev/null || true; done < "$STATE_DIR/test-review-panel/investigate.pids"
check "investigate started all three lenses" "3" "$(grep -c -- '-investigate	' "$calls_file")"
[[ -s "$STATE_DIR/test-review-panel/investigate-coverage.md" ]] || bad "investigate-output" "no investigate-coverage.md written"
[[ -e "$STATE_DIR/test-review-panel/investigate-started" ]] || bad "started-marker" "no investigate-started marker"

# A second call before the panel runs must not relaunch the workers.
run_test_review_investigate
check "a second investigate call is a one-shot no-op" "3" "$(grep -c -- '-investigate	' "$calls_file")"

# A repair that changes source and re-enters TEST_REVIEW must get a fresh
# investigation of the repaired tree, not the stale pre-repair one -- this
# exact gap made a repair cycle look like it never started the overlap at
# all, reported live against calculator4.
mkdir -p src && echo '// a repair touched this file' >> src/engine.js
run_test_review_investigate
check "a changed tree re-investigates instead of reusing the stale marker" "6" "$(grep -c -- '-investigate	' "$calls_file")"

# --- phase 2 reuses the investigation and never re-investigates ------------
: > "$calls_file"
run_test_review_panel
check "finalize launched exactly one call per lens (no fresh investigate)" "0" "$(grep -c -- '-investigate	' "$calls_file")"
check "finalize ran coverage, assertions, oracle" "3" "$(grep -cE 'test-review-worker-(coverage|assertions|oracle)	' "$calls_file")"
coverage_prompt="$(grep 'test-review-worker-coverage	' "$calls_file" | cut -f2)"
check "the finalize prompt carries the earlier investigation forward" "yes" \
    "$(grep -q 'Source looks correct for test-review-worker-coverage-investigate' "$coverage_prompt" && echo yes || echo no)"
[[ -s "$STATE_DIR/documents/TEST_REVIEW.json" ]] || bad "canonical-written" "no canonical TEST_REVIEW.json"
check "the merged packet carries the PASS status from the finalize pass" "PASS" \
    "$(python3 -c "import json; print([r['status'] for r in json.load(open('$STATE_DIR/documents/TEST_REVIEW.json'))['rows'] if r['id']=='COVERAGE'][0])")"

# --- a malformed investigation must not reach the finalize prompt ---------
# calculator4, 2026-10-29: the assertions investigate worker ignored the
# "plain prose, not JSON" instruction and returned a JSON-wrapped,
# self-contradicting blob. Pasted into the finalize prompt, it confused the
# worker into answering with the wrong row id (COVERAGE instead of
# ASSERTIONS), which test_review_packets.py correctly rejected -- but the
# retry hit the same confusion, permanently losing the ASSERTIONS row.
rm -rf "$STATE_DIR/test-review-panel"
: > "$calls_file"
run_codex_review() {
    local prompt="$1" output="$2" log_name="$3"
    printf '%s\t%s\n' "$log_name" "$prompt" >> "$calls_file"
    case "$log_name" in
        *-investigate)
            # Malformed: JSON-wrapped, no leading Markdown heading.
            printf '{"report":"could not inspect source; no tool access"}' > "$output"
            ;;
        *)
            printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"ASSERTIONS","status":"PASS","evidence":"e"}]}' > "$output"
            ;;
    esac
}
run_test_review_panel
assertions_prompt="$(grep 'test-review-worker-assertions	' "$calls_file" | cut -f2)"
check "a malformed investigation is never pasted into the finalize prompt" "no" \
    "$(grep -q 'could not inspect source' "$assertions_prompt" && echo yes || echo no)"
check "the finalize prompt instead says no usable investigation" "yes" \
    "$(grep -q 'No usable investigation' "$assertions_prompt" && echo yes || echo no)"
check "the finalize prompt restates the exact required id" "yes" \
    "$(grep -q 'Use exactly this id, \"ASSERTIONS\"' "$assertions_prompt" && echo yes || echo no)"

# --- resume safety net: panel called with no prior investigate ------------
run_codex_review() {
    local prompt="$1" output="$2" log_name="$3"
    printf '%s\t%s\n' "$log_name" "$prompt" >> "$calls_file"
    case "$log_name" in
        *-investigate) printf '# Investigation\n\nSource looks correct for %s.\n' "$log_name" > "$output" ;;
        *coverage*) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"COVERAGE","status":"PASS","evidence":"e"}]}' > "$output" ;;
        *assertions*) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"ASSERTIONS","status":"PASS","evidence":"e"}]}' > "$output" ;;
        *oracle*) printf '{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"ORACLE","status":"PASS","evidence":"e"},{"id":"NEGATIVE","status":"PASS","evidence":"e"}]}' > "$output" ;;
    esac
}
rm -rf "$STATE_DIR/test-review-panel"
: > "$calls_file"
run_test_review_panel
check "a resumed run still gets an investigation (not skipped)" "3" "$(grep -c -- '-investigate	' "$calls_file")"
check "...then still finalizes all three lenses" "3" "$(grep -cE 'test-review-worker-(coverage|assertions|oracle)	' "$calls_file")"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "test-review-overlap-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "test-review-overlap-test.sh: $PASS checks passed"
