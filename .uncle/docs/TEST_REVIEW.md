## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | PASS | [assertions] CHANGE_TEST_REPORT.md records 21 passing chat-skill tests, including per-clause defect-injection rejections covering AC-1 through AC-5. green-check.md confirms the driver's `bash scripts/run-python-tests.sh -- chat-skill` passed. AC-6 live behavior remains unverified and is not established by these assertions. |
| COVERAGE | YES | BLOCKED-HUMAN | [coverage] CHANGE_TEST_REPORT.md reports 21 passing chat-skill tests covering AC-1 through AC-5, and green-check.md confirms the driver’s targeted command passed. Full Python and shell runs report PREEXISTING failures with no regressions. AC-6 remains unverified pending human release publication and the live hosted check requiring grant #251. |
| INTEGRITY | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | PASS | [oracle] CHANGE_TEST_REPORT.md explicitly reports passing per-clause defect-injection rejections in the 21-test chat-skill suite. green-check.md confirms the driver ran bash scripts/run-python-tests.sh -- chat-skill and recorded PASS, supporting detection of representative defects. |
| ORACLE | YES | PASS | [oracle] CHANGE_PLAN.md independently specifies expected behavior and rejection IDs for clause mutations, description regression, rule ordering, and forbidden preview wording. CHANGE_TEST_REPORT.md reports 21 tests passing, and green-check.md confirms the driver's targeted chat-skill command passed. |
| RESULTS | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
