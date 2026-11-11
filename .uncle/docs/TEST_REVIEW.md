## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | PASS | [assertions] .uncle/workflow/green-check.md records the driver's headless-preview checks as FIXED and chat-skill checks as PASS, with no regressions. .uncle/docs/CHANGE_TEST_REPORT.md records 27 headless-preview tests and 30 headless-preview-open tests passing, covering AC-1 through AC-4, and chat-skill passing for AC-5. Hosted manual checks remain unexecuted and are not included in this assertion result. |
| COVERAGE | YES | BLOCKED-HUMAN | [coverage] CHANGE_TEST_REPORT.md records passing targeted preview tests but leaves hosted checks MC-100, MC-102, and MC-300 unrun because they require a real hosted environment. green-check.md confirms FIXED headless-preview checks, PASS chat-skill checks, and only PREEXISTING full-suite failures, with no regressions. Coverage remains incomplete pending the hosted manual checks. |
| INTEGRITY | YES | PASS | Driver green-check recorded 8 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires critical hosted no-start tests to fail against pre-change code and chat-skill checks to reject defective variants. green-check.md reports suite-level FIXED/PASS results but does not identify representative-defect failures for these critical checks; CHANGE_TEST_REPORT.md supplies no such results either. |
| ORACLE | YES | PASS | [oracle] CHANGE_PLAN.md grounds expected hosted suppression, local labels, and HTTPS-only relay in requirements R-1, R-2, and R-3, independently of implementation output. green-check.md records the headless-preview checks as FIXED and chat-skill checks as PASS. |
| RESULTS | YES | PASS | Driver green-check recorded 8 passing verification command(s); see .uncle/workflow/green-check.tsv. |
