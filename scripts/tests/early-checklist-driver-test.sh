#!/usr/bin/env bash
# The checklist is written beside the test review without the review as an input, and is kept only when the review passes.
set -o pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
not() { ! "$@"; }
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^(early_checklist_start|early_checklist_join|early_checklist_usable|run_manual_checklist_panel)\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"
check "functions extracted" test "$(grep -c '^[a-z_]*() {' "$TMP/fn.sh")" == 4

mkdir -p "$TMP/p/.uncle/workflow/documents" "$TMP/p/.uncle/workflow/logs" "$TMP/p/prompts/change"
cd "$TMP/p"
. "$TMP/fn.sh"
ROOT_REAL="$ROOT"; ROOT="$TMP/root"; mkdir -p "$ROOT/prompts/change" "$ROOT/scripts/lib"
echo "worker prompt" > "$ROOT/prompts/change/manual-checklist-review-worker.md"
STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs
run_codex_review() { cp "$1" "$STATE_DIR/prompt-$3.md"; return 1; }
sleep() { :; }

# early: no TEST_REVIEW.json input; normal: has it
WORKFLOW_MANUAL_CHECKLIST_PANEL=1 UNCLE_CHECKLIST_EARLY=1 run_manual_checklist_panel > /dev/null 2>&1
cat "$STATE_DIR/prompt-manual-checklist-review-worker-coverage.md" | tail -8 >&2
check "early workers are not given the test review" not grep -q 'documents/TEST_REVIEW.json' "$STATE_DIR/prompt-manual-checklist-review-worker-coverage.md"
check "early workers are told why" grep -q 'not an input' "$STATE_DIR/prompt-manual-checklist-review-worker-coverage.md"
WORKFLOW_MANUAL_CHECKLIST_PANEL=1 run_manual_checklist_panel > /dev/null 2>&1
check "normal workers get the test review" grep -q 'documents/TEST_REVIEW.json' "$STATE_DIR/prompt-manual-checklist-review-worker-coverage.md"

# usable only with the marker, a checklist and a passing review
acceptance_json_result=PASS
mkdir -p "$ROOT/scripts/lib"
printf '#!/usr/bin/env python3\nimport os\nprint(os.environ.get("FAKE_RESULT","PASS"))\n' > "$ROOT/scripts/lib/acceptance_json.py"
echo '{}' > "$STATE_DIR/documents/MANUAL_CHECKLIST.json"; echo '{}' > "$STATE_DIR/documents/TEST_REVIEW.json"
check "no marker: not usable" not early_checklist_usable
: > "$STATE_DIR/checklist-early.ok"
FAKE_RESULT=PASS check "marker and pass: usable" early_checklist_usable
FAKE_RESULT=FAIL check "review with findings: not usable" not early_checklist_usable

# start/join: runs, marks success, and is off by switch
run_manual_checklist_panel() { echo "UNCLE_CHECKLIST_EARLY=$UNCLE_CHECKLIST_EARLY" > "$STATE_DIR/early-ran"; }
rm -f "$STATE_DIR/checklist-early.ok"
WORKFLOW_EARLY_CHECKLIST=0 early_checklist_start; early_checklist_join
check "switch off: nothing runs" test ! -e "$STATE_DIR/early-ran"
early_checklist_start; early_checklist_join
check "start runs the panel in early mode" grep -q 'UNCLE_CHECKLIST_EARLY=1' "$STATE_DIR/early-ran"
check "success leaves the marker" test -e "$STATE_DIR/checklist-early.ok"
UNATTENDED=0
green_regressions() { echo 2; }
GREEN_CHECK=1; GREEN_CLASS="$STATE_DIR/class.tsv"; echo x > "$GREEN_CLASS"
rm -f "$STATE_DIR/early-ran"
early_checklist_start; early_checklist_join
check "failing driver check: nothing runs" test ! -e "$STATE_DIR/early-ran"
UNATTENDED=1
rm -f "$STATE_DIR/early-ran"
early_checklist_start; early_checklist_join
check "unattended: a failing driver check does not stop it" test -e "$STATE_DIR/early-ran"
: > "$STATE_DIR/checklist-early.ok"
FAKE_RESULT=FAIL check "unattended: kept even when the review has findings" early_checklist_usable
UNATTENDED=0
green_regressions() { echo 0; }
run_manual_checklist_panel() { return 1; }
early_checklist_start; early_checklist_join
check "failure leaves no marker" test ! -e "$STATE_DIR/checklist-early.ok"

[[ "$fails" == 0 ]] && echo OK
exit "$fails"
