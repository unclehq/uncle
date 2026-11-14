# Change spec — Issue 272

Omitted sections: Migration (none); Prototype isolation (not a prototype); Security (no new surface); Performance (O(text) parse)

## 1. Change type
Bug fix.

## 2. Problem statement
New-app builds whose interpretation lacks `R-n`/`D-n` ids count 0 requirements/criteria, so they can never be `small` and run the full large process.

## 3. Current behavior
See baseline B-2.

## 4. Desired behavior
Requirement and done-criteria counts work from structure (bullets / table rows) when ids are absent. A small hello-world app on the self-hosted path classes `small`. A zero count from a present interpretation is logged as unknown.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| OB-1 | MODIFY | Interpretation with 4 plain bullets under required_functionality and 4 data rows under definition_of_done, 4-step/6-file plan, no risk | requirements=0, criteria=0, not small | counts (4,4); class small | new test |
| OB-2 | PRESERVE | Interpretation with `R-n`/`D-n` ids | counted by id | same counts as before | existing + new test |
| OB-3 | ADD | Interpretation present but a count is 0 | silent | one diagnostic line stating counts are unknown; class not small | new test |
| OB-4 | PRESERVE | No interpretation | (0,0), plan size decides | same | existing |
| OB-5 | PRESERVE | Risk hit / family=change / large thresholds | unchanged | unchanged | existing review-skip suite |
| OB-6 | PRESERVE | Id-less interpretation exceeding limits (e.g. 7 bullets) | n/a | not small | new test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | Risk hits class `risky` | classing | deterministic_class | existing |
| INV-2 | EXISTING | Small needs 0<req<=6, 0<done<=8, steps<=12, files<=30 | app family | app_is_small | new test (OB-6) |
| INV-3 | NEW | Header and separator table rows are never counted as done criteria | counting | interpretation_counts | new test |
| INV-4 | EXISTING | family=change counts unaffected | change family | features | existing |
No RELAXED or REMOVED invariants.

## 7. Compatibility
`change-class.json` schema unchanged; id-bearing interpretations count as before.

## 8. Error and failure behavior
Missing/invalid interpretation: counts (0,0) as today. Empty-count with interpretation present: log, remain non-small.

## 12. Rollback
Revert the change to `scripts/lib/change_class.py`; no persisted-state migration.

## 14. Explicit non-goals
- Changing how `large` counts test/scaffold files or steps (request item 3): deferred, separate decision with wider class impact.
- Changing the investigation prompt or requirements fast path.
- Issue #245 time/spend limits.

## 15. Assumptions
Investigation sections are Markdown with bullets and a pipe table; id-bearing ids take precedence when present.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | An app interpretation with 4 plain bullets in required_functionality and a 4-row id-less definition_of_done table, with a 4-step, <=15-file plan and no risk hits, classes as small via deterministic_class. | New unit test in scripts/tests/review-skip-test.py; run `bash scripts/run-python-tests.sh -- review-skip`. |
| AC-2 | interpretation_counts returns (4,4) for that interpretation, not counting the table header or separator rows, and returns the same counts as before for R-n/D-n id interpretations. | Unit tests for id-less and id-bearing inputs. |
| AC-3 | An id-less interpretation with more than 6 bullets (or more than 8 done rows) is not classed small. | Unit test. |
| AC-4 | When an interpretation exists but a count is 0, a diagnostic line is logged and the build is not classed small; with no interpretation behavior is unchanged. | Unit test capturing stderr; existing review-skip suite. |
| AC-5 | Existing shell and python suites show no new regressions versus baseline. | Driver verification commands. |

