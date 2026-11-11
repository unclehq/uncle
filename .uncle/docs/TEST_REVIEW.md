## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | FAIL | [assertions] CHANGE_TEST_REPORT.md explicitly reports no assertion on stagegate.sh's RERUN_RESULT.json prompt text, leaving the planned AC-8/AR-014 audit-input assertion unverified. green-check.md records only PREEXISTING failures for the driver's shell and Python runners, so it does not establish that the relevant assertions ran and passed. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md reports passing targeted tests but identifies missing AC-3 integration coverage, no assertion on the stagegate.sh RERUN_RESULT.json prompt, and no end-to-end parallel green_run test. The driver's green-check.md records both regression runners as PREEXISTING failures, so it establishes no regressions but does not establish passing full-suite coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md reports passing targeted suites but no representative defect injection or evidence that critical assertions failed when the implementation was defective. The PREEXISTING failures in green-check.md do not demonstrate that sensitivity. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md specifies expected behavior, but CHANGE_TEST_REPORT.md does not establish that test expected values were independently derived. green-check.md records only PREEXISTING failures for both regression runners, with no passing oracle validation. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
