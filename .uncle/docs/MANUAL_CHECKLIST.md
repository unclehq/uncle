# Manual checklist

### MC-103
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui` with the chat runner made unavailable (e.g. PATH without the runner CLI), type a free-form line, then `/help`, then `/quit`.
- Expected result: One-line error for the failed chat line, the session survives and `/help` still answers, `/quit` exits cleanly.
- Actual result: 
- Status: NOT RUN

### MC-107
- Exclusive resources: project-build-state
- Depends on: none
- Exact action: Start a build in a session, then type `/quit` (answer `n`, then repeat answering `y`); afterwards run `ps` to look for leftover driver or runner processes; also send SIGTERM to a session mid-chat.
- Expected result: Declining keeps the build running; confirming stops it first and exits; SIGTERM exits 143; no child processes remain.
- Actual result: 
- Status: NOT RUN

### MC-108
- Exclusive resources: project-build-state
- Depends on: none
- Exact action: With an existing brief, enter a natural-language create-app request and answer `maybe`, then repeat answering `yes`; also run `/mode unattended` and check `/mode` output.
- Expected result: Junk declines replacement; `yes` archives the old brief under .uncle/brief-history and proceeds; `/mode` reflects the new mode for later builds.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start an attended build in a pty session until a gate prompt appears. Type `yes` once, and in another run send EOF at the gate. Also pipe extra lines during a build.
- Expected result: Exactly one typed line is consumed per gate and recorded as human (I-5); EOF at a gate declines/stops and never approves; later piped lines run as normal prompts in order after the build; model output never answers a gate.
- Evidence to capture: Transcript plus the build's gate attestation record for each run.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Pipe sessions with a line of exactly 1048576 bytes, one of 1048577 bytes followed by a normal line, and `/quit`; also pipe a model-style/ESC-laden reply scenario if a fake runner is available.
- Expected result: The over-long line yields exactly one 'line too long' error on stderr, its remainder is not run, the next line runs, exit code is 2 if last event; no raw escape bytes in output.
- Evidence to capture: Separate stdout and stderr captures, and exit code.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui --noinput` and then `uncle --noui --bogus-arg` in a scratch project; note stderr and exit code of each.
- Expected result: `--noui --noinput` prints its existing error and exits 2; bare `--noui` with an unrecognized argument keeps its current error and exit code, and neither starts the REPL.
- Evidence to capture: Terminal transcript with stderr text and `echo $?` for both commands.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a one-shot form (`uncle --noui --application <small fixture brief>` with a fake or available runner, unattended) and watch it to completion.
- Expected result: A single headless run prints plain progress with no REPL banner or `uncle> ` prompt, then exits with the usual code (0 on success, 1/2/3 on failure/refusal/gate stop).
- Evidence to capture: Captured stdout/stderr and exit code; confirm no banner or prompt text appears.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui --attended` with stdin redirected from a non-tty (e.g. `echo | uncle --noui --attended --application <brief>`) and observe.
- Expected result: The existing refusal message is printed and the exit code is 2, unchanged from before.
- Evidence to capture: Stderr text and exit code.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the normal curses TUI (`uncle` without --noui) in a pty, open the home chat, type `build issue 1` style request and a slash command such as /help, then quit.
- Expected result: TUI renders normally with curses, home chat replies, and the issue request is still recognized as before; no import or startup errors appear.
- Evidence to capture: Screenshot or terminal capture of the TUI home screen and chat response.
- Actual result: 
- Status: NOT RUN
