## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | BLOCKED-SETUP | [assertions] CHANGE_TEST_REPORT.md marks targeted mocked-publisher tests N/A because the build script is external; the assertions required by CHANGE_PLAN.md for AC-1 through AC-5 have no passing execution evidence. green-check.md reports both regression runners as PREEXISTING failures, which does not verify the required publisher assertions. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_TEST_REPORT.md marks targeted mocked-publisher tests N/A and AC-1 through AC-4 unverified because the build script is external; it provides no executed coverage for AC-5 exhausted retries. green-check.md records both regression runners as PREEXISTING failures, not passing checks. The documentation grep does not establish the behavioral coverage required by CHANGE_PLAN.md. |
| INTEGRITY | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | BLOCKED-SETUP | [oracle] CHANGE_PLAN.md requires the regression test to fail with the original 7200-second request, but CHANGE_TEST_REPORT.md contains no such execution because the external build script is unavailable. The PREEXISTING failures in green-check.md do not demonstrate detection of a representative expiry or retry defect. |
| ORACLE | YES | BLOCKED-SETUP | [oracle] CHANGE_PLAN.md specifies independent expected values for the 3600-second cap and accepted-request expiry, but CHANGE_TEST_REPORT.md reports mocked-publisher tests unavailable because the build script is external. No executed test demonstrates those oracles; green-check.md records only PREEXISTING failures for both regression runners. |
| RESULTS | YES | PASS | Driver green-check recorded 2 passing verification command(s); see .uncle/workflow/green-check.tsv. |
