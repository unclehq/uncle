## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | FAIL | [assertions] CHANGE_TEST_REPORT.md explicitly reports missing AC-3 end-to-end assertions and AC-4/AC-5 coverage limited to wording greps rather than driving completion. These omit the required T-2 handoff.json, artifact-based completion, and failure-path behavioral assertions. green-check.md records only PREEXISTING failures and no regressions; it does not establish that the missing assertions ran and passed. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md explicitly reports that AC-3 has no end-to-end test and AC-4/AC-5 are covered only by wording greps rather than completion execution, leaving required T-2 coverage incomplete. green-check.md records all driver runner executions as PREEXISTING failures; its no-regressions finding does not establish that the missing acceptance checks ran and passed. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_PLAN.md requires T-2a to fail before the fix and T-1(a) to reject a naive implementation. Neither CHANGE_TEST_REPORT.md nor green-check.md records execution demonstrating those representative defects are caught; PREEXISTING suite failures do not establish this. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md specifies contract-based expected values, but CHANGE_TEST_REPORT.md provides no verification that implemented test oracles are independently grounded. It explicitly reports missing AC-3 execution and wording-only AC-4/AC-5 checks; green-check.md reports PREEXISTING failures without oracle-validation evidence. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
