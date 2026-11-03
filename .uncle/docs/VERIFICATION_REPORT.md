# Verification report

## Findings

### MC-102

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196)
- **Expected result:** per checklist MC-102
- **Actual result:** Cases n, empty Enter, Ctrl-D (\x04), 'y please', 'maybe', 'yy': nonzero exit, 'unchanged' message, request and .uncle/workflow byte-identical.
- **Defects:** None

### MC-104

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196)
- **Expected result:** per checklist MC-104
- **Actual result:** Flag and env, with/without opt-in, never-written fifo: refusal exit 1 naming UNCLE_REPLACE_CHANGE_REQUEST=1, opt-in 1 replaces; no hang (30s harness timeout, not 10s; elapsed not recorded).
- **Defects:** None

### MC-105

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-105
- **Actual result:** Piped/devnull stdin with values 0/true/empty refuse exit 1 and file kept; value 1 on a pty proceeds with no prompt. Piped 'y' input not consumed (see MC-204).
- **Defects:** None

### MC-106

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-106
- **Actual result:** No prompt for NEW_WORKFLOW, --seed-only, in-flight same-issue resume on a pty. Resume and seed-only leave file untouched. NEW_WORKFLOW (state COMPLETE, same issue 142): exit 0, .uncle/workflow-history created, request reseeded.
- **Defects:** None

### MC-203

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-203
- **Actual result:** Unattended 1 replaces; 0/true/empty refuse exit 1, file kept. Interactive pty value 1: no prompt, replaced, exit 0. Interactive 0/true/empty still prompt (not treated as opt-in).
- **Defects:** None

### MC-204

- **Action:** bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-204
- **Actual result:** printf 'y\ny\n' piped: exit 1, opt-in message, file hash unchanged, workflow stub not run.
- **Defects:** None

### MC-205

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-205
- **Actual result:** No-file, zero-byte, NEW_WORKFLOW, resume, seed-only: no prompt phrase in stderr; file states as expected.
- **Defects:** None

### MC-206

- **Action:** bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-206
- **Actual result:** Whitespace-only prompts (driver). Symlink and directory prompt; decline leaves link, target and dir intact. After 'y' on symlink: CHANGE_REQUEST.md stays a symlink but its target hash CHANGED (write followed the link). Expected target not clobbered. Filed D-1.
- **Defects:** D-1

### MC-301

- **Action:** none
- **Expected result:** per checklist MC-301
- **Actual result:** Depends on MC-300, which is not in the checklist (README: NOT DECLARED). Equivalent action covered by MC-102 PASS but this ID is not asserted.
- **Defects:** None

### MC-303

- **Action:** none
- **Expected result:** per checklist MC-303
- **Actual result:** Depends on MC-302, absent from the checklist. Equivalent covered by MC-203 PASS but this ID is not asserted.
- **Defects:** None

### MC-304

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-304
- **Actual result:** Action equivalent executed (no file, zero-byte, pty): no prompt, request written. Dependency IDs MC-300/302 are undefined in the checklist; noted in Open questions.
- **Defects:** None

### MC-401

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196)
- **Expected result:** per checklist MC-401
- **Actual result:** 'no request: no prompt' and 'no request: written' on a pty.
- **Defects:** None

### MC-402

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196)
- **Expected result:** per checklist MC-402
- **Actual result:** seed_is_current case: no prompt, 'Resuming' printed, request hash unchanged.
- **Defects:** None

### MC-403

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196) + bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-403
- **Actual result:** NEW_WORKFLOW: no prompt, archived (.uncle/workflow-history), reseeded. Seed-only: no prompt, file hash unchanged, workflow not started.
- **Defects:** None

### MC-404

- **Action:** none
- **Expected result:** per checklist MC-404
- **Actual result:** `uncle --change-request` stdin import not executed; not touched by the diff (scripts/from-issue.sh only). Settled by running that command against an existing file.
- **Defects:** None

### MC-405

- **Action:** bash scripts/run-shell-tests.sh (driver, new test: 'passed: 104 failed: 0', output.log:196)
- **Expected result:** per checklist MC-405
- **Actual result:** Existing request with no in-flight state: 'n' exits nonzero, file and workflow unchanged; 'y' replaces and proceeds (driver cases). My live run with a different-issue in-flight origin was refused earlier by the existing origin check, so it did not exercise this guard and is not used.
- **Defects:** None

### MC-406

- **Action:** bash .uncle/workflow/check-scripts/live-extra.sh (scratch repos, fake gh, stub driver; exit nonzero overall due to MC-206 y-case only)
- **Expected result:** per checklist MC-406
- **Actual result:** Stdin fifo, /dev/null: exit 1 naming UNCLE_REPLACE_CHANGE_REQUEST=1, file kept; opt-in 1 replaces exit 0; --unattended without opt-in refuses.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-102 | YES | PASS | see finding |
| MC-104 | YES | PASS | see finding |
| MC-105 | YES | PASS | see finding |
| MC-106 | YES | PASS | see finding |
| MC-203 | YES | PASS | see finding |
| MC-204 | YES | PASS | see finding |
| MC-205 | YES | PASS | see finding |
| MC-206 | YES | FAIL | D-1 symlink target clobbered |
| MC-301 | YES | NOT RUN | see finding |
| MC-303 | YES | NOT RUN | see finding |
| MC-304 | YES | PASS | see finding |
| MC-401 | YES | PASS | see finding |
| MC-402 | YES | PASS | see finding |
| MC-403 | YES | PASS | see finding |
| MC-404 | YES | NOT RUN | see finding |
| MC-405 | YES | PASS | see finding |
| MC-406 | YES | PASS | see finding |
