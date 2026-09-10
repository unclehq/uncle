# CHANGE_SPEC.md

Omitted sections: Performance requirements (no change); Security requirements (no change); Migration requirements (none); Prototype-isolation requirements (not a prototype).

## 1. Change type

Bug Fix

## 2. Problem statement

`scripts/tests/document-budget-test.sh` fails because its standalone reviewer fixture omits `repair-acceptance.py`, a runtime dependency of `finish_review_budget` (`scripts/lib/gates.sh:399`). This fails the Windows CI regression runner (`.github/workflows/installers.yml:66`) and reproduces on Darwin/Bash 3.2 (BASELINE_REPORT.md §11).

## 3. Current behavior

`document-budget-test.sh:163` copies `gates.sh`, `compact-review.py`, and the reviewer scripts into a standalone directory, but not `repair-acceptance.py`. The reviewer scripts exit before the budget check, so `grep` for `Document budget exceeded:` at `document-budget-test.sh:191` fails.

## 4. Desired behavior

The standalone fixture includes every dependency `finish_review_budget` needs to reach the budget check when `WORKFLOW_REVIEW_COMPACT=0`. The `document-budget` suite passes and Windows CI reports zero failures for it.

## 5. Acceptance criteria

- `bash scripts/tests/document-budget-test.sh` exits 0 (BASELINE_REPORT.md §9 T-2).
- Windows Git Bash runner (`installers.yml:88`) reports `PASS: document-budget`.
- No budget policy, overflow handling, or reviewer contract changes.

## 6. Observable behavior table

| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | `bash scripts/tests/document-budget-test.sh` | FAIL at `document-budget-test.sh:191` | PASS | BASELINE_REPORT.md §9 T-2 |
| B-2 | PRESERVE | Advisory overflow | Continues with remark; preserves document | Same | `document-budget-test.sh:47-58` |
| B-3 | PRESERVE | Enforced overflow | Blocks with `Document budget exceeded:` | Same | `document-budget-test.sh:188-191` |
| B-4 | PRESERVE | Windows regression runner executes `document-budget` | Counts failures; currently fails CI | Zero failures for this suite | `installers.yml:73-99` |

## 7. Invariant table

| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Artifact-specific override precedes global override, then defaults | All document-budget consumers | `scripts/lib/gates.sh:255`, `:274-275` | `document-budget-test.sh:33-71` |
| I-2 | EXISTING | Saved budget increases scoped to source fingerprint | `.uncle/workflow/document-budgets` | `scripts/lib/gates.sh:244-251` | `document-budget-test.sh:113-116` |
| I-3 | EXISTING | UTF-8 byte count; final unterminated line counted | `check_document_budget` | `scripts/lib/gates.sh:344-345` | `document-budget-test.sh:9-13` |
| I-4 | NEW | Standalone reviewer fixture includes all dependencies reachable by `finish_review_budget` | `document-budget-test.sh` standalone directory | Test setup | `document-budget-test.sh:188-191` |

## 8. Compatibility requirements

No user-visible interface, schema, or policy changes. Existing `WORKFLOW_DOC_*` overrides remain effective.

## 9. Error and failure behavior

If the fixture remains incomplete, `document-budget-test.sh` fails at line 191 and Windows CI reports the suite as failed. No new failure modes are introduced.

## 13. Rollback expectations

Revert the fixture change. The suite returns to the current failing state.

## 15. Explicit non-goals

- Change `scripts/lib/gates.sh` budget logic or limits.
- Change reviewer contracts in `codex-review-plan.sh` or `codex-create-checklist.sh`.
- Add new regression suites or features.
- Modify `.github/workflows/installers.yml` runner structure.

## 16. Assumptions and unresolved questions

- ASSUMPTION: The fix is confined to the test fixture; `scripts/lib/gates.sh` dependencies are unchanged.
- UNRESOLVED: Whether the failure reproduces identically on native Windows Git Bash; BASELINE_REPORT.md §11 marks Windows equivalence pending CI.
