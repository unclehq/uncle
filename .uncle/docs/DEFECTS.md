# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. Automated coverage of prompt logic is in the driver green-check, which this check does not substitute for.
- **Expected result:** Prompt shows framework, full resolved argv, a privilege warning, and defaults to No; no web preview opens.
- **Actual result:** Not observed. A person must watch the live TUI prompt and confirm no browser window opens.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None.
- **Expected result:** A real Electron window opens; history prints framework, command, PID and log path; the pid file and log exist under .uncle/workflow/ with 0600 permissions.
- **Actual result:** Not observed. A person must press y at the prompt and view the window.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None.
- **Expected result:** The Electron window closes, the process tree is gone, and the pid file is removed.
- **Actual result:** Not observed, because no Electron app was launched.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** python3 scripts/tests/tui-desktop-launch-test.py -> 'Ran 10 tests in 0.139s OK'. Driver green-check rows are PREEXISTING (no regressions).
- **Expected result:** Unrelated key leaves prompt open; Enter, n, Esc decline, launch nothing, record declined in desktop-launch.json, then normal completion dialog.
- **Actual result:** Probe tests test_unrelated_keys_leave_prompt_open, test_decline_keys_record_declined_without_spawn and test_prompt_shows_argv_and_warning_and_enter_declines passed (10/10 OK). Not observed in a real attended terminal run, and the completion dialog following the decline was not separately observed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Probe output: 10 tests OK.
- **Expected result:** With WORKFLOW_PREVIEW_DESKTOP=0: no desktop detection output, no desktop-* files, web preview unchanged.
- **Actual result:** Automated probe test passed. A live run on an Electron fixture with browser observation was not performed here.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None captured. No screenshot, transcript or .uncle/workflow listing was produced for this check.
- **Expected result:** Behavior is unchanged: the web completion preview opens the browser, and no desktop prompt or desktop files appear.
- **Actual result:** Not performed. The check needs a person to run the whole workflow to completion on a plain web project and watch the system browser open. A worker lane cannot do that, and it must not start a nested workflow run.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Probe output: 'Ran 10 tests OK'.
- **Expected result:** Prompt shows full argv and privilege warning; unrelated keys leave it open; Enter/n/Esc/quit decline with no spawn; only y launches.
- **Actual result:** All related automated probe tests passed (10/10). Quit-while-open and a human-visible screen capture were not independently observed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No window, screenshot, PID or log was observed.
- **Expected result:** The prompt shows the full argv and a privilege warning; after y a real Electron window opens and the TUI prints framework, command, PID and log path.
- **Actual result:** Not executed. The check needs a person to attend the TUI and observe a real GUI window on macOS, which this non-interactive worker cannot do.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No window or PID was observed.
- **Expected result:** The window closes, the process tree is gone, and desktop-app.pid is removed.
- **Actual result:** Not executed. The prerequisite window from MC-301 does not exist. A human must quit the TUI and observe the window and PID.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No live observation was made. Driver green-check results were not cited as a substitute for the attended observation.
- **Expected result:** The web completion preview starts and opens the browser, and the star/finished dialog appears as before. No desktop prompt, history line, or .uncle/workflow/desktop-* file appears.
- **Actual result:** Not performed. The check needs a person watching an attended TUI session and the system browser.
