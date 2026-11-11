## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] `.uncle/workflow/green-check.md` records headless-preview as FIXED and both full runners as PREEXISTING failures. However, `.uncle/docs/CHANGE_TEST_REPORT.md` contains no assertion review or requirement-level results, and no usable earlier investigation establishes that assertions cover the mandatory plan cases. Assertion adequacy remains unverified. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md records a missing test handoff and unresolved coverage gaps for all changed behavior. green-check.md reports headless-preview as FIXED, but both full regression runners failed with PREEXISTING results. These results do not establish that all required coverage checks ran and passed. |
| INTEGRITY | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] Neither CHANGE_TEST_REPORT.md nor green-check.md records critical tests failing against an identified representative defect. The headless-preview FIXED classification alone does not establish which defect caused the earlier failure or whether the intended assertions detected it. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md defines expected timing, framing, deduplication, and launch rendering, but the supplied results do not establish that test assertions independently encode those expectations. green-check.md reports headless-preview as FIXED; CHANGE_TEST_REPORT.md contains no oracle-review evidence. |
| RESULTS | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
