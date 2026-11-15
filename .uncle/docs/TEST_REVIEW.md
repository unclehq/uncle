## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | FAIL | [assertions] CHANGE_TEST_REPORT.md reports 28 passing OSS tests but explicitly states gate-stop coverage uses unit tests and an ordering check rather than an end-to-end workflow run. CHANGE_PLAN.md AC-7 requires a behavioral workflow assertion with approval withheld, reasons listed, no stage advancement, and no silent default selection; the reported checks do not establish this requirement. green-check.md confirms the OSS suite ran successfully but supplies no evidence that the missing behavioral assertion ran. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md reports 28 passing OSS tests but explicitly lacks the end-to-end gate-stop test required by CHANGE_PLAN.md for AC-7/AR-011; unit tests and an ordering check do not satisfy that behavioral requirement. green-check.md confirms the targeted OSS suite passed and no regressions, but provides no evidence that the missing workflow-level check ran. |
| INTEGRITY | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] Neither CHANGE_TEST_REPORT.md nor green-check.md documents a representative defect being introduced and detected by critical tests. The FIXED OSS results and PREEXISTING regression failures do not establish that negative-control verification occurred. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md reports 28 passing OSS tests but provides no assessment that their expected values are independently grounded. green-check.md records command outcomes without oracle-validation evidence. |
| RESULTS | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
