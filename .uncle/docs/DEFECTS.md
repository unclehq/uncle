# Defects

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** `which tmux` returned 'tmux not found'. claude is at ~/.local/bin/claude and uncle at /opt/homebrew/bin/uncle. This worker has no interactive terminal to drive the UI or observe it.
- **Expected result:** A claude home-agent child process is alive shortly after startup, before any operator message.
- **Actual result:** Not performed. The check needs an interactive curses session, and tmux is not installed in this worker environment.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** tmux is not installed. No UI session was available.
- **Expected result:** No claude home-agent process exists in either case, and no preload note appears in the home chat history.
- **Actual result:** Not executed. The UI half needs an interactive terminal. The most useful setup action is a human or a pty/tmux-capable runner.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No terminal multiplexer is available. A screen capture and timing cannot be taken from this worker.
- **Expected result:** The early message is answered within about 3 seconds of extra wait, turns do not interleave, and exactly one claude process exists.
- **Actual result:** Not executed, because no interactive UI harness is available. A human could do this.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** tmux is not installed and no interactive session is available.
- **Expected result:** No error, note or history line appears at startup, and sending a message follows the normal path.
- **Actual result:** Not executed. It needs an interactive UI with visual observation.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No interactive session is available to this worker.
- **Expected result:** Drawing and keyboard input stay responsive during startup, with no visible stall.
- **Actual result:** Not executed. It needs a person to observe the live UI.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** tmux is not installed.
- **Expected result:** Exactly one home-agent claude child process is alive before any operator message, and the UI responds to keystrokes.
- **Actual result:** Not executed. There is no interactive curses harness.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** tmux is not installed. No UI session was available.
- **Expected result:** No home-agent claude process starts in either case, and no preload note appears in the home history.
- **Actual result:** Not executed. The UI half cannot be observed here.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No interactive session is available to this worker.
- **Expected result:** The message is answered, begins within about 3 seconds, never interleaves with the preload turn, and one process exists.
- **Actual result:** Not executed. It needs a live UI and human timing.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** tmux is not installed and no UI session is available.
- **Expected result:** No error or note appears from the failed preload, and the message is handled by the lazy start or the normal fallback.
- **Actual result:** Not executed. It needs an interactive UI.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The driver green-check covers automated tests only and cannot establish this human-visible, process-level observation.
- **Expected result:** Neither run leaves any home-agent `claude` child process; --noui shows no curses UI and UNCLE_HOME_AGENT=0 UI starts normally with no preload process.
- **Actual result:** Not observed. No run or `ps` capture was made.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None.
- **Expected result:** UI draws and responds to keys with no perceptible stall during startup, and after quit no home-agent `claude` process remains.
- **Actual result:** Not observed. No responsiveness judgement or post-quit `ps` capture was made.

## MC-306

- **Status:** NOT RUN
- **Evidence:** No worker observation was supplied for this checklist item.
- **Expected result:** Drawing and key input stay responsive with no visible freeze caused by the preload.
- **Actual result:** Not performed.
