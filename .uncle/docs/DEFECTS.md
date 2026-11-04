# Defects

## MC-102

- **Status:** BLOCKED-SETUP
- **Evidence:** Depends on MC-101, which is not in the checklist. Needs a real scratch GitHub repo, gh auth and a live planner
- **Expected result:** see MANUAL_CHECKLIST.md MC-102
- **Actual result:** Depends on MC-101, which is not in the checklist. Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.

## MC-103

- **Status:** BLOCKED-HUMAN
- **Evidence:** policy-refusal and refused-case tests passed in both attended and unattended modes. Not a live run with a real
- **Expected result:** see MANUAL_CHECKLIST.md MC-103
- **Actual result:** policy-refusal and refused-case tests passed in both attended and unattended modes. Not a live run with a real planner.

## MC-105

- **Status:** BLOCKED-HUMAN
- **Evidence:** Static checks passed. Live slash flow not observed. Needs an attended TUI/terminal session with screen observa
- **Expected result:** see MANUAL_CHECKLIST.md MC-105
- **Actual result:** Static checks passed. Live slash flow not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## DEF-2

- **Status:** BLOCKED-HUMAN
- **Evidence:** Config tests include 1 failure (DEF-2 path) and the TUI/line-menu interaction was not observed. Needs an atten
- **Expected result:** see MANUAL_CHECKLIST.md MC-106
- **Actual result:** Config tests include 1 failure (DEF-2 path) and the TUI/line-menu interaction was not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-107

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow
- **Expected result:** see MANUAL_CHECKLIST.md MC-107
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.

## DEF-1

- **Status:** FAIL
- **Evidence:** Policy test has 3 failures incl. flag-form matching (DEF-1); exact-shape refusals for git branch -D, git -c, p
- **Expected result:** see MANUAL_CHECKLIST.md MC-201
- **Actual result:** Policy test has 3 failures incl. flag-form matching (DEF-1); exact-shape refusals for git branch -D, git -c, push --delete main were not individually observed.

## MC-204

- **Status:** BLOCKED-HUMAN
- **Evidence:** ok: lock-held and ok: decline passed (stubbed). Concurrent real workflow and git status not observed. Needs tw
- **Expected result:** see MANUAL_CHECKLIST.md MC-204
- **Actual result:** ok: lock-held and ok: decline passed (stubbed). Concurrent real workflow and git status not observed. Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.

## DEF-2

- **Status:** BLOCKED-HUMAN
- **Evidence:** Duplicate/floor/invalid config tests ran; TUI not observed. Needs an attended TUI/terminal session with screen
- **Expected result:** see MANUAL_CHECKLIST.md MC-205
- **Actual result:** Duplicate/floor/invalid config tests ran; TUI not observed. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-206

- **Status:** NOT RUN
- **Evidence:** Corrupt/empty fallback tests exist but line-menu view and plan refusal were not run for this check.
- **Expected result:** see MANUAL_CHECKLIST.md MC-206
- **Actual result:** Corrupt/empty fallback tests exist but line-menu view and plan refusal were not run for this check.

## MC-301

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow
- **Expected result:** see MANUAL_CHECKLIST.md MC-301
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.

## MC-304

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to ru
- **Expected result:** see MANUAL_CHECKLIST.md MC-304
- **Actual result:** Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.

## DEF-2

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Expected result:** see MANUAL_CHECKLIST.md MC-305
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-306

- **Status:** BLOCKED-HUMAN
- **Evidence:** ok: configure menu housekeeping entry is last number (line menu). TUI part not observed, and dependency MC-305
- **Expected result:** see MANUAL_CHECKLIST.md MC-306
- **Actual result:** ok: configure menu housekeeping entry is last number (line menu). TUI part not observed, and dependency MC-305 is unrun. Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-401

- **Status:** BLOCKED-HUMAN
- **Evidence:** Existing entry points not exercised live; needs real agent CLIs. Needs a real scratch GitHub repo, gh auth and
- **Expected result:** see MANUAL_CHECKLIST.md MC-401
- **Actual result:** Existing entry points not exercised live; needs real agent CLIs. Needs a real scratch GitHub repo, gh auth and a live planner; not available to the agent. Person: Brian, to run on a scratch repo.

## MC-402

- **Status:** NOT RUN
- **Evidence:** Passed for housekeeping combinations and `unknown flag unchanged`; the three existing-flag combinations and `-
- **Expected result:** see MANUAL_CHECKLIST.md MC-402
- **Actual result:** Passed for housekeeping combinations and `unknown flag unchanged`; the three existing-flag combinations and `--change-requset` typo not observed.

## MC-404

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Expected result:** see MANUAL_CHECKLIST.md MC-404
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-405

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.
- **Expected result:** see MANUAL_CHECKLIST.md MC-405
- **Actual result:** Needs an attended TUI/terminal session with screen observation; not performed. Person: Brian.

## MC-406

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow
- **Expected result:** see MANUAL_CHECKLIST.md MC-406
- **Actual result:** Needs two concurrent terminals running a long workflow; only the stubbed lock-held test (housekeeping-workflow-test.sh, ok: lock-held) was observed, which does not cover this action. Person: Brian.
