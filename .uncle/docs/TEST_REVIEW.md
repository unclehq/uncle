## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] green-check.md reports gitignore-post-push as FIXED, but provides no assertion-level evidence for the required absence, byte-preservation, call-site execution, and rollback checks. CHANGE_TEST_REPORT.md contains only a NOT RUN implementation handoff and explicitly leaves all changed behavior requiring review; no usable assertion review was supplied. |
| COVERAGE | YES | FAIL | [coverage] .uncle/workflow/green-check.md records gitignore-post-push as FIXED, but both required regression runners failed with PREEXISTING results. .uncle/docs/CHANGE_TEST_REPORT.md contains only a NOT RUN handoff and explicitly leaves all changed behavior as a coverage gap. These results do not establish the approved plan's complete requirement coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] green-check.md marks `bash scripts/run-python-tests.sh -- gitignore-post-push` FIXED, establishing a suite-level improvement. Neither report identifies a representative defect and the critical assertion that failed against it, so the required negative-test evidence is not established. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md specifies independent pre-invocation byte snapshots and absence checks for AC-1. However, CHANGE_TEST_REPORT.md contains no executed oracle review, and green-check.md reports suite outcomes without establishing that the implemented expected values are independently grounded. |
| RESULTS | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
