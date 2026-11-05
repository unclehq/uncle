# Verification report

## Findings

### MC-101

- **Action:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean.
- **Expected result:** per checklist MC-101
- **Actual result:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean.
- **Defects:** None

### MC-102

- **Action:** Needs interactive TUI typing and menu inspection by a person; not performed. Person: operator, at a real terminal with a logged-in runner.
- **Expected result:** per checklist MC-102
- **Actual result:** Needs interactive TUI typing and menu inspection by a person; not performed. Person: operator, at a real terminal with a logged-in runner.
- **Defects:** None

### MC-104

- **Action:** Needs interactive TUI and claude agent; also depends on MC-103, which is not in the checklist (grouping NOT DECLARED). Not performed.
- **Expected result:** per checklist MC-104
- **Actual result:** Needs interactive TUI and claude agent; also depends on MC-103, which is not in the checklist (grouping NOT DECLARED). Not performed.
- **Defects:** D-1

### MC-105

- **Action:** Needs a person to decline a live tool approval prompt in the TUI. Not performed.
- **Expected result:** per checklist MC-105
- **Actual result:** Needs a person to decline a live tool approval prompt in the TUI. Not performed.
- **Defects:** None

### MC-107

- **Action:** Only `uncle --noui` without an action was observed (exit 2, 'needs a startup action'). No full noui/unattended run, no TUI start with legacy config; not executed here (costly live agent runs).
- **Expected result:** per checklist MC-107
- **Actual result:** Only `uncle --noui` without an action was observed (exit 2, 'needs a startup action'). No full noui/unattended run, no TUI start with legacy config; not executed here (costly live agent runs).
- **Defects:** None

### MC-200

- **Action:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean. Output captured.
- **Expected result:** per checklist MC-200
- **Actual result:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean. Output captured.
- **Defects:** None

### MC-201

- **Action:** Needs interactive TUI with a logged-in claude runner. Not performed.
- **Expected result:** per checklist MC-201
- **Actual result:** Needs interactive TUI with a logged-in claude runner. Not performed.
- **Defects:** None

### MC-202

- **Action:** Needs live approval prompt interaction. Not performed.
- **Expected result:** per checklist MC-202
- **Actual result:** Needs live approval prompt interaction. Not performed.
- **Defects:** None

### MC-206

- **Action:** Not executed: requires live agent runs in noui and unattended modes. Code-level coverage: driver python suite includes no-housekeeping-test and headless-run-test, but driver results.tsv shows exit 1 for the suite commands (pre-existing failures per green-check.md) so they are not citable as a pass.
- **Expected result:** per checklist MC-206
- **Actual result:** Not executed: requires live agent runs in noui and unattended modes. Code-level coverage: driver python suite includes no-housekeeping-test and headless-run-test, but driver results.tsv shows exit 1 for the suite commands (pre-existing failures per green-check.md) so they are not citable as a pass.
- **Defects:** None

### MC-301

- **Action:** Needs interactive TUI and live claude agent. Not performed.
- **Expected result:** per checklist MC-301
- **Actual result:** Needs interactive TUI and live claude agent. Not performed.
- **Defects:** None

### MC-302

- **Action:** Needs live approval prompts. Not performed; depends on MC-301.
- **Expected result:** per checklist MC-302
- **Actual result:** Needs live approval prompts. Not performed; depends on MC-301.
- **Defects:** None

### MC-303

- **Action:** Needs live TUI confirmation prompts. Not performed; depends on MC-301.
- **Expected result:** per checklist MC-303
- **Actual result:** Needs live TUI confirmation prompts. Not performed; depends on MC-301.
- **Defects:** None

### MC-305

- **Action:** Flag part observed: `uncle --housekeeping` exit 1 as unknown argument, usage free of housekeeping. TUI slash commands and Configure menus need a person; not performed.
- **Expected result:** per checklist MC-305
- **Actual result:** Flag part observed: `uncle --housekeeping` exit 1 as unknown argument, usage free of housekeeping. TUI slash commands and Configure menus need a person; not performed.
- **Defects:** None

### MC-401

- **Action:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean. Misspelled flag still gives suggestion and non-zero exit.
- **Expected result:** per checklist MC-401
- **Actual result:** Ran `uncle <flag> </dev/null` in /tmp/mc: --housekeeping exit 1, --housekeeping=x exit 1, --bogus-flag exit 1, --aplication exit 1 (did-you-mean --application); `uncle --help | grep -ci housekeep` = 0. Only mention is the echoed 'Unknown argument: --housekeeping' (user's own input), not usage/did-you-mean. Misspelled flag still gives suggestion and non-zero exit.
- **Defects:** None

### MC-402

- **Action:** Needs interactive TUI and menu inspection. Not performed.
- **Expected result:** per checklist MC-402
- **Actual result:** Needs interactive TUI and menu inspection. Not performed.
- **Defects:** None

### MC-406

- **Action:** Not executed: only the no-action `--noui` refusal (exit 2) was observed; no unattended run or piped --application run performed.
- **Expected result:** per checklist MC-406
- **Actual result:** Not executed: only the no-action `--noui` refusal (exit 2) was observed; no unattended run or piped --application run performed.
- **Defects:** None

### MC-407

- **Action:** Not executed (optional, Required NO); needs TUI launch with legacy config.
- **Expected result:** per checklist MC-407
- **Actual result:** Not executed (optional, Required NO); needs TUI launch with legacy config.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | see Findings |
| MC-102 | YES | BLOCKED-HUMAN | see Findings |
| MC-104 | YES | BLOCKED-HUMAN | see Findings |
| MC-105 | YES | BLOCKED-HUMAN | see Findings |
| MC-107 | YES | NOT RUN | see Findings |
| MC-200 | YES | PASS | see Findings |
| MC-201 | YES | BLOCKED-HUMAN | see Findings |
| MC-202 | YES | BLOCKED-HUMAN | see Findings |
| MC-206 | YES | NOT RUN | see Findings |
| MC-301 | YES | BLOCKED-HUMAN | see Findings |
| MC-302 | YES | BLOCKED-HUMAN | see Findings |
| MC-303 | YES | BLOCKED-HUMAN | see Findings |
| MC-305 | YES | BLOCKED-HUMAN | see Findings |
| MC-401 | YES | PASS | see Findings |
| MC-402 | YES | BLOCKED-HUMAN | see Findings |
| MC-406 | YES | NOT RUN | see Findings |
| MC-407 | NO | NOT RUN | see Findings |
