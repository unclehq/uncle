## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] CHANGE_TEST_REPORT.md reports 24 passing tests and a repair-guard mutation caught by two tests, but does not establish that the two test-shape adaptations preserve existing assertions as R-3 requires. green-check.md records both driver suites as PREEXISTING failures; its no-regressions finding does not verify assertion preservation. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md reports 24 targeted tests passing for AC-1, AC-2, AC-4, AC-5, and AC-6, plus selected AC-3 regression checks. The driver's green-check.md records both required full runners as PREEXISTING failures, with no regressions; it does not establish successful execution of the relevant coverage checks. Under the required driver-results rule, COVERAGE cannot pass. |
| INTEGRITY | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | PASS | [oracle] CHANGE_TEST_REPORT.md records that removing the relaxed clause from the bounded-writer guard caused two tests to fail, demonstrating sensitivity to a representative AC-5 defect. The intact targeted suite passed all 24 tests; green-check.md reports no regressions. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires literal expected dictionaries for AC-2, but CHANGE_TEST_REPORT.md does not establish that executed assertions use independently grounded expected values. green-check.md reports only PREEXISTING suite failures and cannot verify this requirement. |
| RESULTS | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
