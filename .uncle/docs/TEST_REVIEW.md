## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] CHANGE_TEST_REPORT.md reports passing preflight-toolchain, toolchain-install, and toolchain-wiring assertions, but leaves driver verification pending. green-check.md records only PREEXISTING results for default regression runners, without explicit full-suite selection or targeted suite results confirming that the driver ran and passed these assertions. |
| COVERAGE | YES | FAIL | [coverage] CHANGE_PLAN.md requires explicit full-suite regression selection and three targeted runner commands, but green-check.md records only default shell and Python runner commands, all PREEXISTING. CHANGE_TEST_REPORT.md reports passing targeted tests, but the driver's results do not establish that the required full-suite and targeted checks ran and passed. Live hosted OCaml verification also remains BLOCKED-SETUP. |
| INTEGRITY | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md records four prompt failures before a correction, but provides no executed representative-defect check for the critical preflight and installer tests. CHANGE_PLAN.md describes an expected before-fix failure; green-check.md does not confirm that check ran and passed. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_PLAN.md D-1 and D-3 independently specify expected package mappings, argv, and timeout behavior, but the supplied results do not establish that test assertions match those requirements. green-check.md records only PREEXISTING regression failures, with no passing oracle validation. |
| RESULTS | YES | PASS | Driver green-check recorded 4 passing verification command(s); see .uncle/workflow/green-check.tsv. |
