## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | FAIL | [assertions] .uncle/workflow/green-check.md records both shell and Python driver runs as PREEXISTING failures, so it does not establish passing assertion checks. .uncle/docs/CHANGE_TEST_REPORT.md reports 60 targeted checks and 39 attestation tests passing, but those targeted results do not establish a passing driver run. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md reports 60 helper checks and 39 attestation tests passing, but explicitly leaves full publish-flow coverage and the real FINAL_AUDIT.md verdict format unverified. green-check.md records both regression runners as PREEXISTING failures, with no regressions; it does not establish passing driver verification of the relevant checks. These results do not demonstrate complete coverage of the CHANGE_PLAN.md requirements. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md reports passing targeted tests but no execution against a representative defect or pre-fix implementation. CHANGE_PLAN.md section 16 predicts pre-fix failures; green-check.md provides no observed defect-detection result, and its PREEXISTING failures do not establish that critical tests detect this change's defects. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md defines independent expected behavior in AC-1–AC-4, D-1, and D-2, but the supplied results do not establish that implemented assertions use those independent expectations. CHANGE_TEST_REPORT.md leaves the live audit verdict format unverified, and green-check.md reports only PREEXISTING suite failures, not a passing oracle check. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
