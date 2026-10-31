#!/usr/bin/env bash
set -euo pipefail

# A plan that fails the driver's structural check (a protected path no step owns)
# used to END the run at the approval gate: exit 1, nothing restarts it, and the
# planner was never told what was wrong.  The updated-plan stage is now re-run once
# with the exact error; only a second failure stops for a person.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT + 1)); [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }; }
has() { COUNT=$((COUNT + 1)); grep -qF -- "$2" <<<"$3" || { echo "FAIL: $1 — missing: $2"; FAILED=$((FAILED + 1)); }; }

FUNC="$(ROOT="$ROOT" python3 -B - <<'PY'
import os, re
from pathlib import Path
source = (Path(os.environ["ROOT"]) / "scripts" / "stagegate.sh").read_text()
print(re.search(r"^plan_structure_feedback\(\) \{.*?^}", source, re.M | re.S).group(0))
PY
)"
eval "$FUNC"

cd "$TMP"
export STATE_DIR="$TMP/state"
mkdir -p "$STATE_DIR/documents"
printf '## Verification commands\n\n```sh\nnpm test\n```\n\n## Implementation order\n\n1. Core. Owns: `src/calc.js`\n' > PLAN.md
printf '{"schema":"uncle.artifact/v1","kind":"plan","protected_verification_paths":"tests/calc.test.js\\ntests/debug_test.js\\nsrc/calc.js"}' > "$STATE_DIR/documents/PLAN.json"

out="$(plan_structure_feedback 'a protected verification path with no owning implementation step' PLAN.md)"
has "the error is named" "it has a protected verification path with no owning implementation step" "$out"
has "the unowned paths are listed" '- `tests/calc.test.js`' "$out"
has "every unowned path is listed" '- `tests/debug_test.js`' "$out"
check "an owned path is not listed" no "$([[ "$out" == *'`src/calc.js`'* ]] && echo yes || echo no)"
has "both fixes are offered" "add each path to the \`Owns:\` of the step that creates it" "$out"
has "removal is offered" "remove it from Protected verification paths" "$out"

# The driver runs under errexit and pipefail, where the checker's exit 1 (gaps
# found) ended the run before the retry. A command substitution hides that, so
# call it the way the driver does.
check "feedback survives errexit when gaps exist" survived \
    "$(ROOT="$ROOT" FUNC="$FUNC" bash -c 'set -euo pipefail; eval "$FUNC"; plan_structure_feedback "a protected verification path with no owning implementation step" PLAN.md > feedback.md; echo survived' 2>/dev/null || true)"
has "feedback written under errexit lists the gap" '- `tests/calc.test.js`' "$(cat feedback.md 2>/dev/null)"

has "a missing commands block is explained" 'one fenced block of shell commands' "$(plan_structure_feedback 'no Verification commands block' PLAN.md)"
has "an unknown problem still gets a message" 'return the delivery again in the same shape' "$(plan_structure_feedback 'something else' PLAN.md)"

# The gate retries once, then stops; the feedback reaches the next planner call.
DRIVER="$ROOT/scripts/stagegate.sh"
body="$(python3 - "$DRIVER" <<'PY'
import sys
s = open(sys.argv[1]).read()
branch = s[s.index("        WAIT_UPDATED_PLAN_APPROVAL)"):]
print(branch[:branch.index("review_and_approve")])
PY
)"
has "the gate retries the planner once" 'updated-plan-structure-retried' "$body"
has "the retry returns to UPDATED_PLAN" 'set_state UPDATED_PLAN' "$body"
check "the gate's gap listing cannot end the driver" yes \
    "$(grep -A1 'plan_ownership_gap.py' <<<"$body" | grep -q "sed 's/^/  /' || true" && echo yes || echo no)"
check "the retry is followed by a continue, not an exit" yes \
    "$(python3 - "$DRIVER" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index("set_state UPDATED_PLAN\n                    continue")
print('yes' if i > 0 else 'no')
PY
)"
check "a second failure still stops for a person" yes "$([[ "$body" == *'to approve a plan that the next stage would reject'*'exit 1'* ]] && echo yes || echo no)"
has "the planner prompt receives the feedback" 'updated-plan-structure-feedback.md" >> "$UPDATED_PLAN_PROMPT"' "$(cat "$DRIVER")"


# A plan that runs its tests from under .uncle/ names a path that cannot exist.
STRUCT="$(ROOT="$ROOT" python3 -B - <<'PY'
import os, re
from pathlib import Path
source = (Path(os.environ["ROOT"]) / "scripts" / "stagegate.sh").read_text()
print(re.search(r"^plan_structure_problem\(\) \{.*?^}", source, re.M | re.S).group(0))
PY
)"
(
    . "$ROOT/scripts/lib/green-check.sh"
    eval "$STRUCT"
    repair_parallel_groups() { return 0; }
    verification_paths() { echo tests/a.test.js; }
    problem_for() {
        printf '## Verification commands\n\n```sh\n%s\n```\n' "$1" > "$TMP/P.md"
        plan_structure_problem "$TMP/P.md" || true
    }
    check_sub() { COUNT=$((COUNT + 1)); [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }; echo "$COUNT $FAILED" > "$TMP/counts"; }
    COUNT=0; FAILED=0
    WHY='verification commands that run files under .uncle/'
    check_sub "a config under .uncle/config/ is refused" "$WHY" "$(problem_for 'npx playwright test --config .uncle/config/playwright.config.js')"
    check_sub "tests under .uncle/tests/ are refused" "$WHY" "$(problem_for 'npx vitest run .uncle/tests/calc.test.js')"
    check_sub "a ./ prefix does not hide it" "$WHY" "$(problem_for 'cd app && npx playwright test -c ./.uncle/config/x.js')"
    check_sub "ordinary paths pass" "" "$(problem_for 'npx playwright test --config playwright.config.js')"
    check_sub "driver workflow paths are not refused" "" "$(problem_for 'cat .uncle/workflow/state')"
    check_sub "a name that merely starts with config passes" "" "$(problem_for 'cat .uncle/configuration-notes.txt')"
    check_sub "the planner is told how to fix it" yes "$(plan_structure_feedback "$WHY" "$TMP/P.md" | grep -qF 'nothing can be created under `.uncle/config/`' && echo yes || echo no)"
)
read -r sub_count sub_failed < "$TMP/counts"
COUNT=$((COUNT + sub_count)); FAILED=$((FAILED + sub_failed))

if [[ "$FAILED" -ne 0 ]]; then echo "plan-structure-retry-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "plan-structure-retry-test.sh: $COUNT checks passed"
