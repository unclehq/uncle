# Implementation notes

### Files changed

- `scripts/from-issue.sh` — Add confirm_replace_change_request guard (prompt on tty, refuse on unattended/non-tty unless UNCLE_REPLACE_CHANGE_REQUEST=1); skipped for UNCLE_NEW_WORKFLOW=1 fresh starts via FRESH_START; decline message says the file is left unchanged; 1; S1-S6, V1, V2
- `scripts/tests/change-request-exists-prompt-test.sh` — New pty-driven end-to-end test (104 checks); scrubs inherited UNCLE_* env and drains the pty master so the child exits; 2; AC-1..AC-5
- `scripts/README.md` — Document the prompt and UNCLE_REPLACE_CHANGE_REQUEST=1; 3; AC-4

### Unresolved concerns

- Full shell and Python suites are run by the driver, not here (AC-6).

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | scripts/from-issue.sh confirm_replace_change_request: y/yes any case proceeds and replaces | bash scripts/tests/change-request-exists-prompt-test.sh: 104 ok, 0 FAIL, exit 0 |
| AC-2 | IMPLEMENTED | scripts/from-issue.sh: any other answer/empty/EOF exits 1 before write; message says unchanged | same test; decline cases check byte-identical file and .uncle/workflow, stub not run |
| AC-3 | IMPLEMENTED | guard returns early when file absent or zero-byte | same test no-file/empty cases; issue-document-test.sh exit 0 |
| AC-4 | IMPLEMENTED | scripts/from-issue.sh unattended/non-tty refusal naming UNCLE_REPLACE_CHANGE_REQUEST=1; scripts/README.md | same test: fifo never-written stdin, flag and env, opt-in exactly 1, README grep |
| AC-5 | IMPLEMENTED | guard skipped for seed_is_current and FRESH_START (UNCLE_NEW_WORKFLOW=1) | same test; worktree-auto-seed-test.sh exit 0 |
| AC-6 | IMPLEMENTED | No change to other suites; driver runs full block | Targeted related suites pass here; full suites pending in driver green-check |
