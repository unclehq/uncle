## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] .uncle/workflow/green-check.md reports FIXED for `bash scripts/run-python-tests.sh -- release-grants`, establishing a successful suite run. However, .uncle/docs/CHANGE_TEST_REPORT.md contains no assertion-level evidence, and no usable source investigation establishes that the suite asserts every mandatory AC-1/AC-2 outcome; assertion adequacy remains unverified. |
| COVERAGE | YES | FAIL | [coverage] .uncle/workflow/green-check.md records the release-grants command as FIXED, but both regression runners failed with PREEXISTING results. .uncle/docs/CHANGE_TEST_REPORT.md contains only a NOT RUN handoff and no evidence establishing coverage of every mandatory AC-1/AC-2 case. The supplied results therefore do not establish complete required coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] green-check.md reports `bash scripts/run-python-tests.sh -- release-grants` FIXED but identifies no representative defect that caused a critical assertion to fail. CHANGE_TEST_REPORT.md contains no defect-injection results; the planned negative cases in CHANGE_PLAN.md are not execution evidence. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md R-1 and AC-1/AC-2 independently specify expected exit codes, streams, and boolean strictness. green-check.md reports the release-grants command FIXED, but CHANGE_TEST_REPORT.md provides no assertion review establishing that executed tests use those independent expectations. |
| RESULTS | YES | PASS | Driver green-check recorded 3 passing verification command(s); see .uncle/workflow/green-check.tsv. |
