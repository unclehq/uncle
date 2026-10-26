#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/lib/plan-scope.sh — the change-impact table and
# implementation sequence readers that make CHANGE_PLAN.md's frozen scope
# addressable by the driver.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/plan-scope.sh"

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

PLAN="$TMP/CHANGE_PLAN.md"
cat > "$PLAN" <<'EOF'
# Change Plan

## 20. Implementation sequence

1. First step, the pure predicate.
2. Second step, the repository.
3. Final step: full gate and reports.

## 21. Scope cuts

1. Not a step; different section.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `app/domain/records.py` | Add a predicate | S1 | Low | `tests/test_domain.py` |
| `app/records/service.py` — `login` | Relax | S2 | High | `tests/test_security.py` |
| `app/static/admin.js`, `admin.html` | Wiring | S3 | Low | manual |
| `app/records/api.py` | Route on `/login` and `/api/admin/users` | S4 | Low | n/a |

## Traceability

| `app/not_in_impact_table.py` | should not be picked up |
EOF

# --- the file list is the union of Component and Test coverage -------------

got="$(plan_scope_files "$PLAN" | tr '\n' ' ')"
check_eq "scope files" \
    "admin.html app/domain/records.py app/records/api.py app/records/service.py app/static/admin.js tests/test_domain.py tests/test_security.py " \
    "$got"

# A symbol in the Component cell is not a file.
COUNT=$((COUNT + 1))
case "$got" in *login*) fail "the symbol 'login' was treated as a file" ;; esac

# A route is not a file.
COUNT=$((COUNT + 1))
case "$got" in *"/api/admin/users"*) fail "a route was treated as a file" ;; esac

# The reader stops at the next heading.
COUNT=$((COUNT + 1))
case "$got" in *not_in_impact_table*) fail "read past the change-impact table" ;; esac

# --- the implementation sequence ------------------------------------------

check_eq "step count" "3" "$(plan_steps "$PLAN" | grep -c .)"
check_eq "first step"  "First step, the pure predicate." "$(plan_steps "$PLAN" | sed -n 1p)"
check_eq "last step"   "Final step: full gate and reports." "$(plan_steps "$PLAN" | sed -n 3p)"

# A numbered list in a different section is not a step.
COUNT=$((COUNT + 1))
if plan_steps "$PLAN" | grep -q 'different section'; then
    fail "read past the implementation sequence"
fi

# --- out-of-scope detection ------------------------------------------------

check_eq "in-scope file is not a deviation" "" \
    "$(plan_out_of_scope "$PLAN" app/domain/records.py)"

check_eq "unplanned file is a deviation" "app/config.py" \
    "$(plan_out_of_scope "$PLAN" app/config.py)"

# A sibling named by basename alone in the plan still matches its real path.
check_eq "basename-only scope entry matches its path" "" \
    "$(plan_out_of_scope "$PLAN" app/static/admin.html)"

# Artifacts the workflow itself writes are never deviations. The list covers
# both pipelines and every stage: once untracked files are examined, a report
# the workflow wrote itself would otherwise read as scope creep.
for artifact in IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md DEFECTS.md \
                .uncle/workflow/change.diff BASELINE_REPORT.md CHANGE_SPEC.md \
                CHANGE_REQUEST.md ADVERSARIAL_REVIEW.md FINAL_AUDIT.md \
                AUTOMATED_TEST_REPORT.md UPDATED_PROJECT_PLAN.md \
                REQUIREMENTS_INTERPRETATION.md; do
    check_eq "workflow artifact '$artifact' is not a deviation" "" \
        "$(plan_out_of_scope "$PLAN" "$artifact")"
done

# A source file that merely looks like one is still a deviation: the list is
# exact paths, not a pattern.
check_eq "a lookalike path is still a deviation" "docs/FINAL_AUDIT.md" \
    "$(plan_out_of_scope "$PLAN" docs/FINAL_AUDIT.md)"

check_eq "mixed set reports only the deviations" "app/config.py migrations/0004.py" \
    "$(plan_out_of_scope "$PLAN" app/domain/records.py app/config.py \
        IMPLEMENTATION_NOTES.md migrations/0004.py | tr '\n' ' ' | sed 's/ $//')"

# --- a plan with no table or sequence degrades quietly ---------------------

echo '# Change Plan' > "$TMP/bare.md"
# An assignment in the real driver runs under errexit and pipefail. Checking
# only its text inside check_eq would hide a failing parser exit status.
bash -e -o pipefail -c '. "$1"; files="$(plan_scope_files "$2")"; test -z "$files"' \
    _ "$ROOT/scripts/lib/plan-scope.sh" "$TMP/bare.md"
check_eq "no table: empty scope" "" "$(plan_scope_files "$TMP/bare.md")"
check_eq "no sequence: no steps"  "" "$(plan_steps "$TMP/bare.md")"
check_eq "no table: nothing is out of scope" "" \
    "$(plan_out_of_scope "$TMP/bare.md" app/anything.py || true)"
check_eq "missing file: empty scope" "" "$(plan_scope_files "$TMP/does-not-exist.md")"

# --- plan_step_owns / plan_step_depends key by position, not by the plan's
# own literal digits --------------------------------------------------------
#
# A real run numbered its first step "0." (a prerequisite "Environment
# check"), which is a step like any other -- not the plan's mistake. Every
# consumer of these two functions identifies a step by its position in the
# list (plan_steps' output order; step_groups.py's grouping loop), so keying
# ownership and dependency edges by the literal "0", "1", "2", ... instead
# shifted every step's declared files one off from the step that actually
# owns them: a worker doing exactly its assigned, correctly-described task
# got checked against a different step's file list and rejected for writing
# what it was told to.
ZERO="$TMP/zero-indexed.md"
cat > "$ZERO" <<'EOF'
# Plan

## Implementation order

0. Environment check — Owns: `preflight.sh` — Depends on: none
1. Scaffold — Owns: `package.json`, `index.html` — Depends on: 0
2. Reducer — Owns: `calc.js`, `calc.test.js` — Depends on: 1
3. Reconcile — Owns: `*` — Depends on: 1, 2
EOF
check_eq "0-indexed: step_steps order unaffected" "Environment check — Owns: \`preflight.sh\` — Depends on: none
Scaffold — Owns: \`package.json\`, \`index.html\` — Depends on: 0
Reducer — Owns: \`calc.js\`, \`calc.test.js\` — Depends on: 1
Reconcile — Owns: \`*\` — Depends on: 1, 2" "$(plan_steps "$ZERO")"
check_eq "0-indexed: position 1 (literal 0) owns preflight.sh" "1	preflight.sh" \
    "$(plan_step_owns "$ZERO" | grep preflight.sh)"
check_eq "0-indexed: position 2 (literal 1, Scaffold) owns package.json+index.html, not Reducer's files" \
    "2	package.json
2	index.html" "$(plan_step_owns "$ZERO" | grep '^2	')"
check_eq "0-indexed: position 3 (literal 2, Reducer) owns calc.js+calc.test.js" \
    "3	calc.js
3	calc.test.js" "$(plan_step_owns "$ZERO" | grep '^3	')"
check_eq "0-indexed: Scaffold (position 2) depends on Environment check (literal 0 -> position 1)" \
    "2	1" "$(plan_step_depends "$ZERO" | grep '^2	')"
check_eq "0-indexed: Reconcile (position 4) depends on positions 2 and 3 (literals 1, 2)" \
    "4	2
4	3" "$(plan_step_depends "$ZERO" | grep '^4	')"

# The document renderer places dependency metadata on a following bullet.
# Those edges must not be lost, or an entirely serial chain becomes one unsafe
# parallel group.
MULTILINE="$TMP/multiline-depends.md"
cat > "$MULTILINE" <<'EOF'
## Implementation order

1. Scaffold — Owns: `package.json`
   - Depends on: none
2. Core — Owns: `src/core.js`
   - Depends on: 1
3. UI — Owns: `src/App.jsx`
   - Depends on: 2
EOF
check_eq "multiline Depends on metadata is extracted" "2	1
3	2" "$(plan_step_depends "$MULTILINE")"

# --- a long Owns: list wraps onto its own lines --------------------------
#
# A real run: a step touching two dozen files listed them one per line, each
# correctly backticked, under a bare "Owns:" on the numbered heading's own
# line. The single-line extraction alone saw zero tokens there and never
# looked further, so a step that declared every file it touched was merged
# as though it had declared none of them -- "wrote files it did not
# declare" for files the plan named explicitly. A neighboring step's prose
# bullet auditing call sites ("- Audit ... `require_file`, `verify_approval`,
# ...", also drawn from a real plan) must not be swept in as though those
# were files too.
WRAP="$TMP/wrapped-owns.md"
cat > "$WRAP" <<'EOF'
# Plan

## Implementation sequence

1. Driver — Owns: `scripts/change-workflow.sh`
   - Audit every occurrence of bare names: `require_file`, `verify_approval`, `run_codex`.
   - Depends on: none

2. All prompt templates — Owns:
   `prompts/adversarial-review.md`,
   `prompts/change/final-audit.md`,
   `prompts/implement.md`

   - Depends on: none
EOF
check_eq "wrapped Owns: step 1 owns only its declared file, not the audit bullet's names" \
    "1	scripts/change-workflow.sh" "$(plan_step_owns "$WRAP" | grep '^1	')"
check_eq "wrapped Owns: step 2 owns every file on its own continuation lines" \
    "2	prompts/adversarial-review.md
2	prompts/change/final-audit.md
2	prompts/implement.md" "$(plan_step_owns "$WRAP" | grep '^2	')"

# An implementation order laid out as a TABLE is read like a numbered list.  A real
# plan used one, no step was seen to own its protected test file, and the plan
# stopped at the approval gate.
TABLE="$TMP/TABLE.md"
cat > "$TABLE" <<'TBL'
## 12. Implementation order

| Step | Description | Owns | Depends on |
|---|---|---|---|
| 1 | Add failing regression tests | `tests/calc.test.js`, `tests/e2e.test.js` | — |
| 2 | Guard division in calc logic | `src/App.jsx` | 1 |
| 3 | Palette and background | `src/App.css` | 1 |
| 4 | Keyboard mapping | `src/App.jsx` | 2 |
| 5 | Build and verify | — | 3, 4 |

## 13. Requirement traceability

| Step | Description | Owns |
|---|---|---|
| 9 | not an implementation step | `elsewhere.js` |
TBL
check_eq "table: ownership is read per step" "1	tests/calc.test.js
1	tests/e2e.test.js
2	src/App.jsx
3	src/App.css
4	src/App.jsx" "$(plan_step_owns "$TABLE")"
check_eq "table: dependencies are read as edges" "2	1
3	1
4	2
5	3
5	4" "$(plan_step_depends "$TABLE")"
check_eq "table: five steps are found" "5" "$(plan_steps "$TABLE" | wc -l | tr -d ' ')"
check_eq "table: a table in another section is not a step" "0" "$(plan_step_owns "$TABLE" | grep -c elsewhere || true)"
check_eq "table: the first step's text is its description" "yes" "$([[ "$(plan_steps "$TABLE" | head -1)" == 'Add failing regression tests Owns:'* ]] && echo yes || echo no)"
LISTPLAN="$TMP/LIST.md"
printf '## Implementation order\n\n1. Core — Owns: `a.js`\n2. UI — Owns: `b.js` — Depends on: 1\n' > "$LISTPLAN"
check_eq "a numbered list is unaffected" "1	a.js
2	b.js" "$(plan_step_owns "$LISTPLAN")"

# Paths written WITHOUT backticks are still ownership.  A planner wrote
# "Owns: tests/calc.test.js, tests/theme.test.js. Depends on: step 1" and the plan was
# rejected for having no owner of its own protected tests.
BARE="$TMP/BARE.md"
cat > "$BARE" <<'BRE'
## 12. Implementation order

1. Config and dependencies. Owns: package.json, package-lock.json, vite.config.mjs
2. Create the tests (red first). Owns: tests/calc.test.js, tests/theme.test.js. Depends on: step 1
3. Change the handler; limited to keys. Owns: src/Calculator.jsx (modify). Depends on: steps 1, 2
4. Verify only. Owns: none (read-only).
5. Reconcile. Owns: *. Depends on: 3
BRE
check_eq "bare paths: ownership is read per step" "1	package.json
1	package-lock.json
1	vite.config.mjs
2	tests/calc.test.js
2	tests/theme.test.js
3	src/Calculator.jsx
5	*" "$(plan_step_owns "$BARE")"
check_eq "bare paths: prose after Owns owns nothing" "0" "$(plan_step_owns "$BARE" | grep -c '^4	' || true)"
check_eq "bare paths: dependencies still read" "2	1
3	1
3	2
5	3" "$(plan_step_depends "$BARE")"

# A step table with ids "S-0".."S-9" and `Owns:` written inline at the end of each
# Description cell (no Owns column) is read too.  A planner wrote exactly that and the
# plan was reported as having no owner for any file.
SNPLAN="$TMP/SN.md"
cat > "$SNPLAN" <<'SNT'
## 12. Implementation order

| Step | Description | Requirements | Depends on | Capability |
|---|---|---|---|---|
| S-0 | Inspect existing files and record the snapshot. Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md` | R-1 | none | CAP-1 |
| S-1 | Scaffold the project. Owns: `package.json`, `playwright.config.js`, `src/main.jsx` | R-1 | S-0 | CAP-1 |
| S-2 | Reducer module. Owns: `src/calc.js` | R-5 | S-1 | CAP-2 |
| S-3 | Browser tests. Owns: `tests/e2e/calc.spec.js` | D-1 | S-1, S-2 | CAP-5 |

## Decisions

| ID | Decision | Owns |
|---|---|---|
| DEC-1 | not a step | `elsewhere.js` |
SNT
check_eq "S-n table: inline Owns is read per step" ".uncle/docs/IMPLEMENTATION_NOTES.md
package.json
playwright.config.js
src/main.jsx
src/calc.js
tests/e2e/calc.spec.js" "$(plan_step_owns "$SNPLAN" | cut -f2)"
check_eq "S-n table: steps are numbered by position" "1 2 2 2 3 4" "$(plan_step_owns "$SNPLAN" | cut -f1 | tr '\n' ' ' | sed 's/ $//')"
check_eq "S-n table: S-ids in Depends on become edges" "2	1
3	2
4	2
4	3" "$(plan_step_depends "$SNPLAN")"
check_eq "S-n table: a table in another section is not a step" "0" "$(plan_step_owns "$SNPLAN" | grep -c elsewhere || true)"
check_eq "S-n table: four steps are found" "4" "$(plan_steps "$SNPLAN" | wc -l | tr -d ' ')"

# A table whose path column is called "Paths" (no Owns column), with each step's full
# ownership written as a prose line under it ("S1 Owns: `a`, `b`. Depends on: S0.").  A
# planner wrote exactly this; the table said "explicit list below" for step S1 and the plan
# was rejected for having no owner of its own protected files.
PATHS="$TMP/PATHS.md"
cat > "$PATHS" <<'PTH'
## 12. Implementation order

| Step | Title | Paths | Reqs | Depends |
|---|---|---|---|---|
| S0 | Baseline | none (writes outside repo) | R-1 | none |
| S1 | Scaffold | explicit list below | R-1 | S0 |
| S2 | Reducer and tests | `src/calc.js`, `tests/unit/calc.test.js` | R-1 | S1 |
| S3 | Config and e2e | `playwright.config.js` | D-1 | S2 |

S0 Owns: a copy of the existing `index.html` stored outside the repo. Depends on: none.
S1 Owns: `package.json`, `package-lock.json`, `vite.config.js`. Depends on: S0. Dependencies pinned to exact versions; port 4173 is owned by the dev script.
S3 Owns: `playwright.config.js`, `tests/e2e/calc.spec.js` (incl. T-E2E-8..10). Depends on: S2.

## 13. Requirement traceability
PTH
check_eq "Paths column + prose: a step's prose Owns is read even when its cell says 'explicit list below'" "yes" \
    "$([[ "$(plan_step_owns "$PATHS")" == *'2	package.json'* && "$(plan_step_owns "$PATHS")" == *'2	vite.config.js'* ]] && echo yes || echo no)"
check_eq "Paths column + prose: the table cell paths are owned too" "yes" \
    "$([[ "$(plan_step_owns "$PATHS")" == *'3	tests/unit/calc.test.js'* ]] && echo yes || echo no)"
check_eq "Paths column + prose: the prose adds files the cell omitted" "yes" \
    "$([[ "$(plan_step_owns "$PATHS")" == *'4	tests/e2e/calc.spec.js'* ]] && echo yes || echo no)"
check_eq "Paths column + prose: a path named twice is listed once" "1" "$(plan_step_owns "$PATHS" | grep -c '^4	playwright.config.js$')"
check_eq "Paths column + prose: dependencies stop at the end of the sentence" "2	1
3	2
4	3" "$(plan_step_depends "$PATHS")"
check_eq "Paths column + prose: four steps, the prose lines are not extra steps" "4" "$(plan_steps "$PATHS" | wc -l | tr -d ' ')"
PROSE="$TMP/PROSE.md"
printf '## Implementation order\n\nS1 Owns: `a.js`, `b.js`. Depends on: none.\nS2 Owns: `c.js`. Depends on: S1.\n' > "$PROSE"
check_eq "prose-only steps become steps" "1	a.js
1	b.js
2	c.js" "$(plan_step_owns "$PROSE")"
check_eq "prose-only steps keep their dependencies" "2	1" "$(plan_step_depends "$PROSE")"
BULLETS="$TMP/BULLETS.md"
printf '## 12. Implementation order\n\n- S-0: Backup. Owns: `.uncle/backup/a`. Depends on: none.\n- S-1: Scaffold. Owns: `package.json`, `vite.config.js`. Depends on: S-0.\n- S-2: Core. Owns: `src/calc.js`. Depends on: S-1.\nS-2 imports calc.js, hence depends on S-1.\n\n## 13. Next\n' > "$BULLETS"
check_eq "bulleted S-N steps are read as steps" "1	.uncle/backup/a
2	package.json
2	vite.config.js
3	src/calc.js" "$(plan_step_owns "$BULLETS")"
check_eq "bulleted S-N steps keep their dependencies (none for S-0)" "2	1
3	2" "$(plan_step_depends "$BULLETS")"
check_eq "bulleted steps: prose after them is not a step" "3" "$(plan_steps "$BULLETS" | wc -l | tr -d ' ')"

if [[ "$FAILED" -ne 0 ]]; then
    echo "plan-scope-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "plan-scope-test.sh: $COUNT checks passed"
