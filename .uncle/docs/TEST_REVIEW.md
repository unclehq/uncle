## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] .uncle/docs/CHANGE_TEST_REPORT.md records the implementation handoff as NOT RUN and provides no assertion-level results for AC-1 through AC-4. .uncle/workflow/green-check.md records both regression runners as PREEXISTING failures, without showing that the required request-count, sanitization, recovery, ID-membership, or exit-status assertions ran and passed. |
| COVERAGE | YES | FAIL | [coverage] .uncle/docs/CHANGE_TEST_REPORT.md records the implementation handoff as NOT RUN and provides no observed coverage for AC-1 through AC-5. .uncle/workflow/green-check.md reports both regression runners as PREEXISTING failures, without demonstrating that the required schema-feedback-retry and review-incomplete-exit checks ran and passed. The reported absence of regressions does not establish the required coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md provides no representative-defect or mutation-test results. The PREEXISTING runner failures in green-check.md do not establish that critical tests failed for a representative defect. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md specifies expected retry counts and ID membership behavior, but contradicts itself on whether ' 1 ' is accepted. CHANGE_TEST_REPORT.md records the handoff as NOT RUN, and green-check.md reports both runners as PREEXISTING without identifying passing oracle checks; independently grounded test expectations are not verified. |
| RESULTS | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
