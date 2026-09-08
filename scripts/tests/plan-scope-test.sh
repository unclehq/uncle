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
check_eq "no table: empty scope" "" "$(plan_scope_files "$TMP/bare.md")"
check_eq "no sequence: no steps"  "" "$(plan_steps "$TMP/bare.md")"
check_eq "no table: nothing is out of scope" "" \
    "$(plan_out_of_scope "$TMP/bare.md" app/anything.py || true)"
check_eq "missing file: empty scope" "" "$(plan_scope_files "$TMP/does-not-exist.md")"

if [[ "$FAILED" -ne 0 ]]; then
    echo "plan-scope-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "plan-scope-test.sh: $COUNT checks passed"
