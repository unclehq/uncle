# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: In a repo with an authenticated claude CLI and UNCLE_HOME_AGENT unset, launch uncle with the curses UI and, before typing anything, run `ps` to list child processes.
- Expected result: A claude home-agent child process is alive shortly after startup, before any operator message.
- Evidence to capture: ps output showing the claude process and its start time relative to the UI launch.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Run `uncle --noui` with a headless action, then separately launch the UI with UNCLE_HOME_AGENT=0, and run `ps` in each case.
- Expected result: No claude home-agent process exists in either case, and no preload-related note appears in the home chat history when the UI is used.
- Evidence to capture: ps output for both runs and a screenshot or transcript of the home page history.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the UI and immediately submit a message while the preload is still running, then submit a second message.
- Expected result: The early message is answered promptly, within about 3 seconds of extra wait and without waiting out the preload. Turns never interleave, both messages are answered in order, and exactly one claude process exists.
- Evidence to capture: Screen capture of both replies with timings, and ps output showing a single claude process.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the UI with claude unavailable, for example PATH without claude or a failing claude binary. Then send a homepage message.
- Expected result: No error, note or history line appears at startup. Sending a message follows the normal path with no preload-caused breakage.
- Evidence to capture: Screen capture of the home page at startup and after the message.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the UI in a repo with a large directory and open issues. Type and navigate on the home page while the preload runs.
- Expected result: Drawing and keyboard input stay responsive during startup, with no visible stall.
- Evidence to capture: Operator observation notes on input responsiveness, and a screen recording or capture if available.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch uncle with the curses UI in a project with claude authenticated and UNCLE_HOME_AGENT unset; before typing anything, run `ps` and list claude processes started by uncle.
- Expected result: Exactly one home-agent claude child process is alive before any operator message (preload spawned it in the background) and the UI is responsive to keystrokes.
- Evidence to capture: ps output showing a single home-agent claude process; note of UI responsiveness during startup.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Run `uncle --noui` with a headless action, and separately launch the UI with UNCLE_HOME_AGENT=0, then run `ps` in each case.
- Expected result: No home-agent claude process is started in either case and no home-history note about preload appears.
- Evidence to capture: ps output for both runs and screenshot or text of the home history in the UNCLE_HOME_AGENT=0 UI.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the UI and immediately (within a second or two) send a homepage message while the preload is still in flight.
- Expected result: The message is answered, begins within about 3 seconds, never interleaves with the preload turn, and only one home-agent process exists afterwards.
- Evidence to capture: Time from submission to first reply text, the reply itself, and ps output showing one claude process.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the UI with the claude binary made unavailable (for example, PATH without claude or a failing runner), wait, then send a homepage message.
- Expected result: No error or note appears from the failed preload and the message is still handled by the lazy start path or the normal fallback.
- Evidence to capture: Screenshot or text of the UI and home history after startup and after the reply.
- Actual result: 
- Status: NOT RUN

## Resources: process lifecycle

### MC-301
- Required for acceptance: YES
- Exclusive resources: tui:session-A
- Depends on: none
- Exact action: Launch uncle with the curses UI in a repo with the claude runner and UNCLE_HOME_AGENT unset, wait about 10 seconds without typing, and list processes with `ps` for a claude child of uncle.
- Expected result: Exactly one claude home-agent child process is alive before any operator message is sent.
- Evidence to capture: ps output showing the single claude child and its parent PID, captured before typing.
- Actual result: 
- Status: NOT RUN

## Resources: opt-outs

### MC-302
- Required for acceptance: YES
- Exclusive resources: tui:session-B
- Depends on: none
- Exact action: Run `uncle --noui` (or UNCLE_NOUI=1) with a headless action, then separately launch the UI with UNCLE_HOME_AGENT=0, and run `ps` for claude children in each case.
- Expected result: No home-agent claude process is started in either case, and the UI with UNCLE_HOME_AGENT=0 shows no preload-related note in the home history.
- Evidence to capture: ps output for both runs and a screenshot or text of the home history.
- Actual result: 
- Status: NOT RUN

## Resources: cleanup on quit

### MC-303
- Required for acceptance: YES
- Exclusive resources: tui:session-A
- Depends on: MC-301
- Exact action: After the preload has started in a UI session, quit uncle normally, wait a few seconds, then run `ps` for any leftover claude processes from that session.
- Expected result: No claude home-agent process remains after quit.
- Evidence to capture: ps output before and after quit.
- Actual result: 
- Status: NOT RUN

## Resources: UI responsiveness

### MC-306
- Required for acceptance: NO
- Exclusive resources: tui:session-E
- Depends on: none
- Exact action: Launch the UI and type and navigate with the keyboard immediately during the first seconds of startup while the preload runs.
- Expected result: Drawing and key input stay responsive with no visible freeze caused by the preload.
- Evidence to capture: Observer notes on responsiveness during startup, with a screenshot.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: terminal:uncle-tui
- Depends on: none
- Exact action: Run `uncle --noui` with a headless action (and separately `UNCLE_HOME_AGENT=0 uncle` UI launch, then quit), then run `ps` in another terminal while each is running.
- Expected result: Neither run leaves any home-agent `claude` child process; --noui shows no curses UI and UNCLE_HOME_AGENT=0 UI starts normally with no preload process.
- Evidence to capture: ps output captured during each run and the terminal output of each launch.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: terminal:uncle-tui
- Depends on: none
- Exact action: Launch `uncle` with the curses UI in a repo using the claude runner, and immediately type into the UI and navigate screens while the preload is starting; then quit with the normal quit command and run `ps`.
- Expected result: UI draws and responds to keys with no perceptible stall during startup, and after quit no home-agent `claude` process remains.
- Evidence to capture: Observation notes on responsiveness and ps output after quit.
- Actual result: 
- Status: NOT RUN
