# Verification report

## Findings

### MC-100

- **Action:** None performed. The check needs an attended interactive TUI session on a desktop with a display and an Electron fixture project. This non-interactive worker cannot provide that.
- **Expected result:** Prompt shows framework, full resolved argv, a privilege warning, and defaults to No; no web preview opens.
- **Actual result:** Not observed. A person must watch the live TUI prompt and confirm no browser window opens.
- **Defects:** None

### MC-101

- **Action:** None performed. It depends on MC-100, and a real Electron window plus the TUI 'y' keypress need a person at a desktop session.
- **Expected result:** A real Electron window opens; history prints framework, command, PID and log path; the pid file and log exist under .uncle/workflow/ with 0600 permissions.
- **Actual result:** Not observed. A person must press y at the prompt and view the window.
- **Defects:** None

### MC-102

- **Action:** None performed. It depends on MC-101, which was not run, and requires a human to see the Electron window close when the TUI quits.
- **Expected result:** The Electron window closes, the process tree is gone, and the pid file is removed.
- **Actual result:** Not observed, because no Electron app was launched.
- **Defects:** None

### MC-103

- **Action:** Ran narrow prepared probe scripts/tests/tui-desktop-launch-test.py (10 tests) against the TUI desktop prompt; no live attended TUI session was driven.
- **Expected result:** Unrelated key leaves prompt open; Enter, n, Esc decline, launch nothing, record declined in desktop-launch.json, then normal completion dialog.
- **Actual result:** Probe tests test_unrelated_keys_leave_prompt_open, test_decline_keys_record_declined_without_spawn and test_prompt_shows_argv_and_warning_and_enter_declines passed (10/10 OK). Not observed in a real attended terminal run, and the completion dialog following the decline was not separately observed.
- **Defects:** None

### MC-105

- **Action:** Ran probe test_disabled_values_do_nothing_and_web_preview_runs (part of the 10-test run). No live Electron fixture workflow run was performed.
- **Expected result:** With WORKFLOW_PREVIEW_DESKTOP=0: no desktop detection output, no desktop-* files, web preview unchanged.
- **Actual result:** Automated probe test passed. A live run on an Electron fixture with browser observation was not performed here.
- **Defects:** None

### MC-107

- **Action:** Read the MC-107 row from the canonical checklist JSON. Did not run the workflow: it needs an attended, end-to-end TUI run on a separate plain web project, with a real system browser opening.
- **Expected result:** Behavior is unchanged: the web completion preview opens the browser, and no desktop prompt or desktop files appear.
- **Actual result:** Not performed. The check needs a person to run the whole workflow to completion on a plain web project and watch the system browser open. A worker lane cannot do that, and it must not start a nested workflow run.
- **Defects:** None

### MC-200

- **Action:** Ran probes test_prompt_shows_argv_and_warning_and_enter_declines, test_unrelated_keys_leave_prompt_open, test_decline_keys_record_declined_without_spawn, test_y_launches_and_records. No attended TUI screen capture or process list was taken.
- **Expected result:** Prompt shows full argv and privilege warning; unrelated keys leave it open; Enter/n/Esc/quit decline with no spawn; only y launches.
- **Actual result:** All related automated probe tests passed (10/10). Quit-while-open and a human-visible screen capture were not independently observed.
- **Defects:** None

### MC-204

- **Action:** Drove DesktopLaunch (scripts/lib/desktop_launch.py) directly with two stub python processes emitting ANSI CSI/OSC/BEL sequences, one exiting 0 and one exiting 3, grace=3s, in isolated temp roots. Did not drive the full TUI; observed the launcher's failure message/state that the TUI reports.
- **Expected result:** Both reported failed with exit code and log tail; log tail has no escape/control characters; pid file removed; neither reported passed.
- **Actual result:** Exit 0: status=failed, exit_code=0, message 'desktop app exited with code 0 within 3.0s; log tail:\nred boom'. Exit 3: status=failed, exit_code=3, same format with code 3. No control characters in either message; pid file absent in both. Neither passed.
- **Defects:** None

### MC-301

- **Action:** Read the checklist row. No live action performed: it requires an attended TUI workflow run to completion, a y answer at the desktop prompt, a real Electron install, and a human-visible window screenshot.
- **Expected result:** The prompt shows the full argv and a privilege warning; after y a real Electron window opens and the TUI prints framework, command, PID and log path.
- **Actual result:** Not executed. The check needs a person to attend the TUI and observe a real GUI window on macOS, which this non-interactive worker cannot do.
- **Defects:** None

### MC-302

- **Action:** Read the checklist row. Not executed: it depends on the Electron window from MC-301, which was never opened.
- **Expected result:** The window closes, the process tree is gone, and desktop-app.pid is removed.
- **Actual result:** Not executed. The prerequisite window from MC-301 does not exist. A human must quit the TUI and observe the window and PID.
- **Defects:** None

### MC-306

- **Action:** Did not drive the attended TUI y-dialog. Ran scripts/lib/desktop_launch.py DesktopLaunch (the engine the TUI uses) directly against a temp project whose main.js prints ANSI-colored text then calls process.exit(1), with grace=3s.
- **Expected result:** Launch reported failed with the exit code and a log tail free of escape sequences; pid file removed.
- **Actual result:** status=failed, exit_code=1, message 'desktop app exited with code 1 within 3.0s; log tail:\nboom starting'. No ESC characters in message or log_tail. .uncle/workflow listing afterwards: desktop-app.log, desktop-launch.json (no desktop-app.pid).
- **Defects:** None

### MC-401

- **Action:** Read the checklist row. It requires an attended interactive TUI build completion on a scratch plain-web project, with a human observing the browser opening and the star/finished dialog. I did not run it, because this unattended worker has no interactive TUI session or visible browser.
- **Expected result:** The web completion preview starts and opens the browser, and the star/finished dialog appears as before. No desktop prompt, history line, or .uncle/workflow/desktop-* file appears.
- **Actual result:** Not performed. The check needs a person watching an attended TUI session and the system browser.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | BLOCKED-HUMAN | None. Automated coverage of prompt logic is in the driver green-check, which this check does not substitute for. |
| MC-101 | YES | BLOCKED-HUMAN | None. |
| MC-102 | YES | BLOCKED-HUMAN | None. |
| MC-103 | YES | BLOCKED-HUMAN | python3 scripts/tests/tui-desktop-launch-test.py -> 'Ran 10 tests in 0.139s OK'. Driver green-check rows are PREEXISTING (no regressions). |
| MC-105 | YES | BLOCKED-HUMAN | Probe output: 10 tests OK. |
| MC-107 | YES | BLOCKED-HUMAN | None captured. No screenshot, transcript or .uncle/workflow listing was produced for this check. |
| MC-200 | YES | BLOCKED-HUMAN | Probe output: 'Ran 10 tests OK'. |
| MC-204 | YES | PASS | Script output: '0 failed 0 ... pid exists False ctrl False' and '3 failed 3 ... pid exists False ctrl False'. Not observed: the TUI history rendering and test-report files; those were not examined, so coverage is launcher-level only. |
| MC-301 | YES | BLOCKED-HUMAN | None. No window, screenshot, PID or log was observed. |
| MC-302 | YES | BLOCKED-HUMAN | None. No window or PID was observed. |
| MC-306 | YES | PASS | Console output of the python run: 'failed 1 ...', 'esc False', ['desktop-app.log','desktop-launch.json']. Not observed: the TUI's own rendering of the message (no screen capture); the TUI path is only covered by the driver green-check's tui-desktop-launch-test, which I did not re-run or verify. |
| MC-401 | YES | BLOCKED-HUMAN | None. No live observation was made. Driver green-check results were not cited as a substitute for the attended observation. |
