# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/{no-housekeeping,home-agent-session,tui-home-agent,home-actions,supervisor-chat,chat,startup-text-input,run-duties,headless-run}-test.py | PASS | all nine exit 0 (targeted tests) | AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9 |
| bash scripts/tests/{launcher-removed-flag,launcher-stdin-text,launcher-noui,driver-marker,mode-resolution}-test.sh (UNCLE_* env unset) | PASS | all five exit 0 | AC-1, AC-2 |
| baseline comparison: same suites in a pristine HEAD worktree | PASS | attestation-statement, audit-findings, auto-boundary, early-branch, github-issues, home-chat, pr-originless, project-plan-speed, startup-action, step-groups, supervisor, triage-chat, updated-plan-edits, updated-plan-ops fail identically at HEAD and in this tree | AC-10 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns the full regression run. | AC-10 |
| formatter / linter / type checker | N/A | No configured formatter, linter or type checker for this repository. | None stated |
| integration, frontend build, migration, rollback, performance, security checks | N/A | Not applicable; shell and unit suites above are the integration coverage. | None stated |

## Coverage gaps

- No live claude run of the home agent; tool execution and approval restart are covered with synthetic stream results only.
- Planned defect-injection runs (swapped precedence, ignored marker, mutated delegate) were not executed here.
- Pre-existing failing suites listed above were not repaired.

## Next action

Driver runs the verification commands; reviewer should confirm the failing suites match the baseline.
