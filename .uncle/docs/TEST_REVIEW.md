## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | PASS | [assertions] .uncle/docs/CHANGE_TEST_REPORT.md records 39 passing tests in scripts/tests/review-skip-test.py for AC-1 through AC-4. The driver's final .uncle/workflow/green-check.md independently records PASS for bash scripts/run-python-tests.sh -- review-skip on both executions. |
| COVERAGE | YES | FAIL | [coverage] .uncle/docs/CHANGE_TEST_REPORT.md reports 39 passing review-skip tests for AC-1–AC-4, and .uncle/workflow/green-check.md confirms the targeted command passed. Both full regression commands required for AC-5 failed with PREEXISTING status; the driver reports no regressions, but those relevant checks did not pass. The report also identifies missing nested/indented-bullet coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires the AC-1 regression test to fail before the fix. CHANGE_TEST_REPORT.md and green-check.md record passing review-skip runs but no execution against the original defect or a representative mutation; PREEXISTING full-suite failures do not establish this evidence. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md specifies independent expectations for structural counts, per-section ID precedence, and diagnostic cardinality. green-check.md confirms review-skip passed, but the supplied evidence contains no test assertions or completed investigation establishing that actual expected values use those independent expectations. |
| RESULTS | YES | PASS | Driver green-check recorded 6 passing verification command(s); see .uncle/workflow/green-check.tsv. |
