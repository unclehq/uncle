## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | BLOCKED-SETUP | [assertions] CHANGE_TEST_REPORT.md reports the targeted mocked-publisher/clock tests NOT RUN because build-with-uncle/scripts/build.py is absent, leaving AC-1 through AC-4 assertions unverified. green-check.md reports only PREEXISTING regression failures; it provides no passing execution of the required assertions. |
| COVERAGE | YES | BLOCKED-SETUP | [coverage] CHANGE_TEST_REPORT.md records AC-1–AC-4 as unimplemented and unverified because build-with-uncle/scripts/build.py is absent; targeted mocked-publisher/clock tests were NOT RUN. green-check.md reports only PREEXISTING failures for the shell and Python runners, with no regressions, and provides no passing requirement-specific coverage. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | BLOCKED-SETUP | [oracle] CHANGE_PLAN.md specifies a fail-before/pass-after 1-minute-link/70-minute-build regression and renewal-failure and refused-request cases. CHANGE_TEST_REPORT.md records these targeted tests as NOT RUN because the target build.py is absent. green-check.md's PREEXISTING failures provide no evidence that critical tests detect a representative preview-renewal defect. |
| ORACLE | YES | BLOCKED-SETUP | [oracle] CHANGE_PLAN.md grounds expected values in INV-1's 3600-second cap and INV-2's 55-minute validity requirement after successful renewal. CHANGE_TEST_REPORT.md records targeted mocked-publisher/clock tests as NOT RUN because build-with-uncle/scripts/build.py is absent, so executable oracle validation is unavailable. green-check.md reports only PREEXISTING regression failures. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
