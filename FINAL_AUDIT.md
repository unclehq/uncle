Based on my review of the audit evidence, change diff, and supporting documents, I will now produce the final audit:

## Findings

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|---|---|---|---|---|---|---|
| FA-1 | CRITICAL | DEFECTS.md D-001:17-25; change.diff line 100; VERIFICATION_REPORT.md MC-5 through MC-12 (7 BLOCKED-SETUP, 2 FAIL) | B-1, B-2, B-3, B-5, B-7, B-8 | I-1, I-5, I-6 | uncle:166 — replace `${UNCLE_ARGS[*]}` with `${UNCLE_ARGS[*]:-}` to prevent unbound variable error on Bash 3.2 when UNCLE_ARGS is empty | YES |
| FA-2 | MEDIUM | CHANGE_PLAN.md §258-270 specifies `scripts/tests/startup-action-test.py` should be created; change.diff contains no new test files; DEFECTS.md D-002:73-81 documents missing coverage | B-1, B-2 | (none explicit) | Create `scripts/tests/startup-action-test.py` with tests for `_handle_startup_action()` dispatch, `create_app` and `github_issue` actions, `--unattended` propagation, and error handling as specified in CHANGE_PLAN.md | YES |

NOT READY