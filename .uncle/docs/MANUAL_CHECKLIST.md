# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In an attended TUI session on a desktop (non-CI, non-SSH, display available) with a minimal Electron fixture project (single `start` script, WORKFLOW_PREVIEW_DESKTOP unset), complete a workflow run and observe the desktop prompt.
- Expected result: Prompt shows framework, the full resolved argv, a warning that project scripts run with user privileges, and defaults to No; no web preview opens.
- Evidence to capture: Screenshot or transcript of the prompt text and absence of a browser window.
- Actual result: 
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: MC-100
- Exact action: At the desktop prompt press `y` with a real minimal Electron app, then observe the history output and the opened window.
- Expected result: A real Electron window opens; history prints framework, command, PID and log path; the pid file and log exist under .uncle/workflow/ with 0600 permissions.
- Evidence to capture: Screenshot of the window, history lines, and `ls -l .uncle/workflow/desktop-app.*` output.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: MC-101
- Exact action: With the Electron app launched from MC-101 still running, quit the TUI (or stop the workflow) and check whether the window and process remain.
- Expected result: The Electron window closes, the process tree is gone, and the pid file is removed.
- Evidence to capture: Observation that the window closed, `ps` output showing no process, and absence of the pid file.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/desktop-launch.json
- Depends on: none
- Exact action: At the desktop prompt on a fresh run, press an unrelated key (e.g. `x`), then press Enter; repeat another run pressing `n` and another pressing Esc.
- Expected result: Unrelated key leaves the prompt open; Enter, n and Esc each decline, launch nothing, and record declined in .uncle/workflow/desktop-launch.json, then the normal completion dialog follows.
- Evidence to capture: Transcript of each key outcome and contents of desktop-launch.json.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/desktop-launch.json
- Depends on: none
- Exact action: Run the workflow on the Electron fixture with WORKFLOW_PREVIEW_DESKTOP=0 and a valid web launch.json present.
- Expected result: No desktop detection output, no .uncle/workflow/desktop-* files, and the web preview behaves exactly as before.
- Evidence to capture: Transcript, directory listing of .uncle/workflow/, and browser observation.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Run the workflow to completion on a plain web project (no Electron or Tauri) with a webpage launch.json, attended.
- Expected result: Behavior is unchanged: the web completion preview opens the browser, and no desktop prompt or desktop files appear.
- Evidence to capture: Screenshot of the browser preview, transcript, and .uncle/workflow/ listing.
- Actual result: 
- Status: NOT RUN

## invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/desktop-launch.json
- Depends on: none
- Exact action: In a disposable Electron fixture project, run the TUI attended to the end of a build, observe the desktop prompt, press unrelated keys, then press Enter; repeat with y, n, Esc, and quit while the prompt is open.
- Expected result: The prompt shows the full resolved argv and a privilege warning, and unrelated keys leave it open. Enter, n, Esc and quit decline and spawn nothing. Only y launches.
- Evidence to capture: Screen capture of the prompt and the history lines for each key, plus the process list showing no spawned app on decline.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/desktop-app.pid
- Depends on: none
- Exact action: Launch a stub that exits 0 (and another that exits non-zero) within the grace period. The stub's output includes ANSI escape sequences. Observe the TUI report.
- Expected result: Both are reported as failed, with the exit code and a log tail. The log tail shows no escape or control characters, and the pid file is removed. Neither is reported as passed.
- Evidence to capture: TUI history text, the pid file's absence, and the test-report files showing no new rows.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: On macOS, build a minimal Electron project (package.json with electron dep and only a start script, main.js opening a window), run the TUI workflow to completion attended, and answer y at the desktop prompt.
- Expected result: The prompt shows the full argv and a privilege warning; after y a real Electron window opens and the TUI prints framework, command, PID and log path.
- Evidence to capture: Screenshot of the prompt and window, the printed PID/log path, and ls -l of .uncle/workflow/desktop-app.pid and desktop-app.log.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: MC-301
- Exact action: With the Electron window from MC-301 still open, quit the TUI (or stop the workflow) and then check whether the window and its PID still exist.
- Expected result: The window closes, the process tree is gone, and desktop-app.pid is removed.
- Evidence to capture: Screenshot or observation that the window closed, ps output for the PID, and the absence of the pid file.
- Actual result: 
- Status: NOT RUN

### MC-306
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On an Electron project whose start script exits immediately (e.g. process.exit(1) in main.js), run attended and answer y.
- Expected result: The TUI reports the launch as failed with the exit code and a log tail free of escape sequences, and the pid file is removed.
- Evidence to capture: Screen capture of the failure message and a listing showing no desktop-app.pid.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch copy of a plain web project (no Electron/Tauri) with a valid .uncle/launch.json webpage entry, complete a build in the attended TUI and observe the completion flow.
- Expected result: The web completion preview starts and opens the browser, and the star/finished dialog appears as before. No desktop prompt, history line, or .uncle/workflow/desktop-* file appears.
- Evidence to capture: Screen capture or transcript of the TUI history and dialog, plus a listing of .uncle/workflow/ showing no desktop-* files.
- Actual result: 
- Status: NOT RUN
