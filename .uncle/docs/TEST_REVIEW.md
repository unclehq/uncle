## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] CHANGE_TEST_REPORT.md records the implementation handoff as NOT RUN and provides no assertion-level results. green-check.md marks both regression runners PREEXISTING failures, without identifying relevant assertions that ran and passed; assertion verification remains unestablished. |
| COVERAGE | YES | FAIL | [coverage] .uncle/docs/CHANGE_TEST_REPORT.md records the implementation handoff as NOT RUN and provides no behavior-specific test evidence. .uncle/workflow/green-check.md marks both regression runners PREEXISTING, indicating failures rather than passing coverage. Neither report demonstrates that the plan-required `bash scripts/run-python-tests.sh -- no-footprint` ran and passed or establishes coverage for AC-1 through AC-8. |
| INTEGRITY | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires leak-injection and staged-artifact negative tests, but CHANGE_TEST_REPORT.md records no execution evidence. green-check.md reports only PREEXISTING runner failures and does not demonstrate that a critical test failed for a representative injected defect. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md records the implementation handoff as NOT RUN and supplies no evidence that test expectations were independently grounded. green-check.md marks both regression runners PREEXISTING, without check-specific results establishing oracle validity. |
| RESULTS | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
