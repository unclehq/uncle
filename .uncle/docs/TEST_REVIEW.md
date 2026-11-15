## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] CHANGE_TEST_REPORT.md reports 55 shell assertions and 16 Python tests passing, but these are not the driver's final results. green-check.md records both regression runners as PREEXISTING failures without identifying whether the relevant assertion checks ran and passed; the supplied evidence therefore cannot establish PASS for ASSERTIONS. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md reports 55 integration assertions and 16 unit tests passing, but does not establish execution of CHANGE_PLAN.md §16's required 101-page pagination, cross-path parity, and defect-injection cases. green-check.md records both regression runners as PREEXISTING failures, without individual suite results establishing that the required checks ran and passed. The driver's no-regressions conclusion does not establish complete required coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires defect-injection cases for overbroad noise filtering, incorrect maintainer classification, and IDs assigned after noise filtering. Neither CHANGE_TEST_REPORT.md nor green-check.md provides evidence that tests rejected these representative defects; successful injection-comment handling does not demonstrate defect detection. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires independently specified ordering, association mapping, and cross-path parity expectations, but CHANGE_TEST_REPORT.md reports only aggregate suite results without establishing oracle independence. green-check.md records PREEXISTING failures and provides no specific passing oracle check. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
