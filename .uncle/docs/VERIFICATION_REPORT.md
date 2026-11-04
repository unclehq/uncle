# Verification report

## Findings

### MC-102

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-102
- **Actual result:** Depends on MC-101, which is not in the checklist. Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.
- **Defects:** None

### MC-103

- **Action:** Ran housekeeping-workflow-test.sh (stubbed gh/git).
- **Expected result:** see MANUAL_CHECKLIST.md MC-103
- **Actual result:** policy-refusal and refused-case tests passed in both attended and unattended modes. Not a live run with a real planner.
- **Defects:** None

### MC-104

- **Action:** Ran housekeeping-launcher-test.sh and housekeeping-input-test.py.
- **Expected result:** see MANUAL_CHECKLIST.md MC-104
- **Actual result:** Empty and blank stdin refused, mutual exclusion with application/issue refused, did-you-mean suggests --housekeeping, usage lists it (all PASS); input tests 8 OK incl. control characters. Only the mutual-exclusion pair with --application/--issue was observed, not literally `--issue 1`.
- **Defects:** None

### MC-105

- **Action:** Ran tui-housekeeping-test.py (static checks only).
- **Expected result:** see MANUAL_CHECKLIST.md MC-105
- **Actual result:** Static checks passed. Live slash flow not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** None

### MC-106

- **Action:** Ran housekeeping-policy-test.py and launcher test.
- **Expected result:** see MANUAL_CHECKLIST.md MC-106
- **Actual result:** Config tests include 1 failure (DEF-2 path) and the TUI/line-menu interaction was not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** DEF-2

### MC-107

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-107
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.
- **Defects:** None

### MC-200

- **Action:** Ran housekeeping-workflow-test.sh.
- **Expected result:** see MANUAL_CHECKLIST.md MC-200
- **Actual result:** ok: policy-refusal (attended and unattended), ok: mutation-detected; refused plan leaves stub log empty. Disallowed op combined with an allowlisted op was not separately observed.
- **Defects:** None

### MC-201

- **Action:** Ran housekeeping-policy-test.py.
- **Expected result:** see MANUAL_CHECKLIST.md MC-201
- **Actual result:** Policy test has 3 failures incl. flag-form matching (DEF-1); exact-shape refusals for git branch -D, git -c, push --delete main were not individually observed.
- **Defects:** DEF-1

### MC-202

- **Action:** Ran housekeeping-workflow-test.sh.
- **Expected result:** see MANUAL_CHECKLIST.md MC-202
- **Actual result:** ok: mid-run-failure and ok: verify-mismatch passed. Report text and exit code were asserted by the test, not read by me.
- **Defects:** None

### MC-204

- **Action:** Ran housekeeping-workflow-test.sh.
- **Expected result:** see MANUAL_CHECKLIST.md MC-204
- **Actual result:** ok: lock-held and ok: decline passed (stubbed). Concurrent real workflow and git status not observed. Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.
- **Defects:** None

### MC-205

- **Action:** Ran housekeeping-policy-test.py.
- **Expected result:** see MANUAL_CHECKLIST.md MC-205
- **Actual result:** Duplicate/floor/invalid config tests ran; TUI not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** DEF-2

### MC-206

- **Action:** Ran housekeeping-policy-test.py.
- **Expected result:** see MANUAL_CHECKLIST.md MC-206
- **Actual result:** Corrupt/empty fallback tests exist but line-menu view and plan refusal were not run for this check.
- **Defects:** None

### MC-301

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-301
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.
- **Defects:** None

### MC-304

- **Action:** None (stub-covered by MC-200).
- **Expected result:** see MANUAL_CHECKLIST.md MC-304
- **Actual result:** Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.
- **Defects:** None

### MC-305

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-305
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** DEF-2

### MC-306

- **Action:** Ran housekeeping-launcher-test.sh.
- **Expected result:** see MANUAL_CHECKLIST.md MC-306
- **Actual result:** ok: configure menu housekeeping entry is last number (line menu). TUI part not observed, and dependency MC-305 is unrun. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** None

### MC-401

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-401
- **Actual result:** Existing entry points not exercised live; needs real agent CLIs. Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.
- **Defects:** None

### MC-402

- **Action:** Ran housekeeping-launcher-test.sh.
- **Expected result:** see MANUAL_CHECKLIST.md MC-402
- **Actual result:** Passed for housekeeping combinations and `unknown flag unchanged`; the three existing-flag combinations and `--change-requset` typo not observed.
- **Defects:** None

### MC-404

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-404
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** None

### MC-405

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-405
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Defects:** None

### MC-406

- **Action:** None.
- **Expected result:** see MANUAL_CHECKLIST.md MC-406
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-102 | YES | BLOCKED-SETUP | Depends on MC-101, which is not in the checklist. Needs a real scratch GitHub repo, gh auth and a live planner |
| MC-103 | YES | BLOCKED-HUMAN | policy-refusal and refused-case tests passed in both attended and unattended modes. Not a live run with a real |
| MC-104 | YES | PASS | Empty and blank stdin refused, mutual exclusion with application/issue refused, did-you-mean suggests --housek |
| MC-105 | YES | BLOCKED-HUMAN | Static checks passed. Live slash flow not observed. Needs an attended TUI/terminal session with screen observa |
| MC-106 | YES | BLOCKED-HUMAN | Config tests include 1 failure (DEF-2 path) and the TUI/line-menu interaction was not observed. Needs an atten |
| MC-107 | YES | BLOCKED-HUMAN | Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow |
| MC-200 | YES | PASS | ok: policy-refusal (attended and unattended), ok: mutation-detected; refused plan leaves stub log empty. Disal |
| MC-201 | YES | FAIL | Policy test has 3 failures incl. flag-form matching (DEF-1); exact-shape refusals for git branch -D, git -c, p |
| MC-202 | YES | PASS | ok: mid-run-failure and ok: verify-mismatch passed. Report text and exit code were asserted by the test, not r |
| MC-204 | YES | BLOCKED-HUMAN | ok: lock-held and ok: decline passed (stubbed). Concurrent real workflow and git status not observed. Needs tw |
| MC-205 | YES | BLOCKED-HUMAN | Duplicate/floor/invalid config tests ran; TUI not observed. Needs an attended TUI/terminal session with screen |
| MC-206 | YES | NOT RUN | Corrupt/empty fallback tests exist but line-menu view and plan refusal were not run for this check. |
| MC-301 | NO | BLOCKED-HUMAN | Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow |
| MC-304 | NO | BLOCKED-HUMAN | Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to ru |
| MC-305 | NO | BLOCKED-HUMAN | Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian. |
| MC-306 | NO | BLOCKED-HUMAN | ok: configure menu housekeeping entry is last number (line menu). TUI part not observed, and dependency MC-305 |
| MC-401 | YES | BLOCKED-HUMAN | Existing entry points not exercised live; needs real agent CLIs. Needs a real scratch GitHub repo, gh auth and |
| MC-402 | YES | NOT RUN | Passed for housekeeping combinations and `unknown flag unchanged`; the three existing-flag combinations and `- |
| MC-404 | YES | BLOCKED-HUMAN | Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian. |
| MC-405 | YES | BLOCKED-HUMAN | Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian. |
| MC-406 | YES | BLOCKED-HUMAN | Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow |
