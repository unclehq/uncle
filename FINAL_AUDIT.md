# Final audit

## Findings

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|---|---|---|---|---|---|---|
| FA-1 | Critical | REQUIREMENTS.md:7-40 specifies a static retro calculator; change.diff modifies the Uncle launcher and upgrade scripts; final-audit-panel scope packet S-1 | Stated product scope is not delivered | Authorized requirements must govern delivery | Obtain authoritative scope supersession or deliver the calculator requirements | YES |
| FA-2 | High | CHANGE_TEST_REPORT.md:7 claims PASS for AC-1–9 and AC-11–15; green-check command and result records are empty | Upgrade acceptance claims | PASS requires recorded execution evidence | Capture command, exit status, and assertion output for the claimed suite | YES |
| FA-3 | High | VERIFICATION_REPORT.md:25-29 claims MC-1 PASS; no raw execution record exists | Unit acceptance evidence | PASS requires recorded execution evidence | Capture `bash scripts/tests/upgrade-test.sh` execution evidence | YES |
| FA-4 | High | VERIFICATION_REPORT.md:32-36 claims MC-4 PASS; CHANGE_TEST_REPORT.md:8,14,28 records exit 2 before assertions | Install-safety regression | Existing install safety must pass under AC-10 | Run install-safety test where process inspection is permitted and record assertion results | YES |
| FA-5 | High | CHANGE_TEST_REPORT.md:16 reports only shell-menu-startup-test.sh; :17 leaves `bash scripts/run-shell-tests.sh` DRIVER PENDING; green-check records empty | Broader shell regressions | Startup changes must not regress existing shell behavior | Run and record `bash scripts/run-shell-tests.sh` | YES |
| FA-6 | Medium | VERIFICATION_REPORT.md:75-79 claims MC-11 PASS but states no subtest exists; no captured manual evidence is present | Checksum-mismatch rejection | Failed verification must prevent installation | Add assertion or capture reproducible execution evidence | NO |
| FA-7 | Medium | DEFECTS.md:D-1 and VERIFICATION_REPORT.md:97-100 identify permanent stale-lock suppression; no waiver exists | Recovery after interrupted upgrade | Upgrade check remains available after crash | Implement stale-lock recovery or classify it as an authorized follow-up; it is not an AC-1–12 failure without provenance | NO |
| FA-8 | Medium | MANUAL_CHECKLIST.md:3-35 prescribes `bats` for Bash scripts; DEFECTS.md:D-2 confirms the commands are invalid | Checklist execution | Checklist commands must be executable | Correct MC-1 and MC-4 commands to `bash` and record results | NO |
| FA-9 | Medium | delivery-summary.tsv:2-13 marks AC-1–12 INCOMPLETE; no waiver directory or implementation-completion record exists | Delivery status | Incomplete rows cannot be represented as verified delivery | Reconcile delivery summary with recorded verification or explicitly waive scoped acceptance | YES |

NOT READY