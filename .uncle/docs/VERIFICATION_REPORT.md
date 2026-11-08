# Verification report

## Findings

### MC-101

- **Action:** Checked the environment for a way to run the curses UI interactively and inspect child processes. Did not launch the UI.
- **Expected result:** A claude home-agent child process is alive shortly after startup, before any operator message.
- **Actual result:** Not performed. The check needs an interactive curses session, and tmux is not installed in this worker environment.
- **Defects:** None

### MC-102

- **Action:** Not performed. It needs both a headless run and an interactive UI launch with UNCLE_HOME_AGENT=0, plus observation of the home history.
- **Expected result:** No claude home-agent process exists in either case, and no preload note appears in the home chat history.
- **Actual result:** Not executed. The UI half needs an interactive terminal. The most useful setup action is a human or a pty/tmux-capable runner.
- **Defects:** None

### MC-104

- **Action:** Not performed. It needs a live UI session, an authenticated claude, and timed screen observation.
- **Expected result:** The early message is answered within about 3 seconds of extra wait, turns do not interleave, and exactly one claude process exists.
- **Actual result:** Not executed, because no interactive UI harness is available. A human could do this.
- **Defects:** None

### MC-106

- **Action:** Not performed. It needs a UI launch with claude unavailable and a homepage message sent.
- **Expected result:** No error, note or history line appears at startup, and sending a message follows the normal path.
- **Actual result:** Not executed. It needs an interactive UI with visual observation.
- **Defects:** None

### MC-107

- **Action:** Not performed. It is a human judgment of input responsiveness in a live UI.
- **Expected result:** Drawing and keyboard input stay responsive during startup, with no visible stall.
- **Actual result:** Not executed. It needs a person to observe the live UI.
- **Defects:** None

### MC-200

- **Action:** Not performed. It needs a UI launch with an authenticated claude, then `ps` before typing.
- **Expected result:** Exactly one home-agent claude child process is alive before any operator message, and the UI responds to keystrokes.
- **Actual result:** Not executed. There is no interactive curses harness.
- **Defects:** None

### MC-201

- **Action:** Not performed. It needs a headless run and a UI launch with UNCLE_HOME_AGENT=0, observed interactively.
- **Expected result:** No home-agent claude process starts in either case, and no preload note appears in the home history.
- **Actual result:** Not executed. The UI half cannot be observed here.
- **Defects:** None

### MC-203

- **Action:** Not performed. It needs a live UI, a message sent within 1-2 seconds of launch, and timing.
- **Expected result:** The message is answered, begins within about 3 seconds, never interleaves with the preload turn, and one process exists.
- **Actual result:** Not executed. It needs a live UI and human timing.
- **Defects:** None

### MC-206

- **Action:** Not performed. It needs a UI launch with claude unavailable, then a homepage message sent.
- **Expected result:** No error or note appears from the failed preload, and the message is handled by the lazy start or the normal fallback.
- **Actual result:** Not executed. It needs an interactive UI.
- **Defects:** None

### MC-301

- **Action:** Launched the worktree's `python3 uncle_tui.py` under a 40x120 pty (curses UI) with UNCLE_HOME_AGENT and UNCLE_NOUI unset and the claude runner at ~/.local/bin/claude. Waited ~12s without typing, then listed the process tree under the uncle PID with `ps -axo pid,ppid,etime,command`.
- **Expected result:** Exactly one claude home-agent child process is alive before any operator message is sent.
- **Actual result:** Exactly one claude process was in uncle's process tree: pid 72207 (`claude -p --input-format stream-json --tools '' --disable-slash-commands --setting-sources '' --strict-mcp-config --permission-mode dontAsk --no-session-persistence ...`). Its parent is the wrapper python pid 72204, which is a child of uncle pid 72197. Etime was 00:12 and nothing had been typed.
- **Defects:** None

### MC-302

- **Action:** Ran `UNCLE_NOUI=1 ./uncle --noui </dev/null` for ~8s with pgrep snapshots (claude -p / runner_pool.py) before, during and after. Separately launched `./uncle` in a pty (python pty, 120x40, tmux unavailable) with UNCLE_HOME_AGENT=0 for 15s, diffed process snapshots, inspected the new process command lines, and captured the rendered home screen text. The lane's pre-existing claude/runner_pool processes belong to other sessions and the driver, so the comparison used new-PID sets.
- **Expected result:** No home-agent claude process is started in either case, and the UI with UNCLE_HOME_AGENT=0 shows no preload-related note in the home history.
- **Actual result:** Headless: the REPL banner printed, rc=0, and no new claude or runner_pool PIDs appeared during or after. UI with UNCLE_HOME_AGENT=0: the home screen rendered and showed 'Chat ready' with an empty history. It had no preload, warming or home-agent note (regex search returned []). The only new processes were one tool-less supervisor `claude -p --tools '' --disable-slash-commands --setting-sources '' --no-session-persistence ...` (matches scripts/lib/supervisor_runner.py:93) and its wrapper. They are not the home agent, which uses `--allowedTools Read,Glob,Grep,Write,Edit,TodoWrite,Bash ... --replay-user-messages` under runner_pool.py. No runner_pool.py process was started. The guard code at uncle_tui.py:3590 and :3679 matches the observed behavior.
- **Defects:** None

### MC-303

- **Action:** In the same session after the preload had started, sent 'q' and waited 3s. The UI did not exit, so I sent Ctrl-C and waited 5s. Then listed the process tree under the uncle PID and checked that uncle had exited.
- **Expected result:** No claude home-agent process remains after quit.
- **Actual result:** Uncle exited with status 130 (SIGINT-style), and no process remained in its tree. The claude pid 72207 and wrapper pid 72204 were gone. This is a Ctrl-C exit, not a clean menu quit, because 'q' alone did not quit the UI at the home screen.
- **Defects:** None

### MC-401

- **Action:** Not executed. The row needs a live interactive curses `uncle` session in a real terminal, plus a second terminal running `ps` while it runs. This isolated worker has no interactive terminal or second terminal.
- **Expected result:** Neither run leaves any home-agent `claude` child process; --noui shows no curses UI and UNCLE_HOME_AGENT=0 UI starts normally with no preload process.
- **Actual result:** Not observed. No run or `ps` capture was made.
- **Defects:** None

### MC-402

- **Action:** Not executed. The row needs a human to launch the curses UI, type and navigate during startup, judge perceptible stalls, quit, and then run `ps`.
- **Expected result:** UI draws and responds to keys with no perceptible stall during startup, and after quit no home-agent `claude` process remains.
- **Actual result:** Not observed. No responsiveness judgement or post-quit `ps` capture was made.
- **Defects:** None

### MC-306

- **Action:** Launch the UI and type and navigate with the keyboard immediately during the first seconds of startup while the preload runs.
- **Expected result:** Drawing and key input stay responsive with no visible freeze caused by the preload.
- **Actual result:** Not performed.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Run under a pty (no tmux needed) from the PR worktree's uncle_tui.py, harness /private/tmp/claude-503/mc1.py. No typing; after 10s `ps` showed the UI's descendants include a home-agent claude (argv carries --append-system-prompt, pid 15134 in the run) plus the separate supervisor warm-up claude. After SIGINT no descendants remained. |
| MC-102 | YES | BLOCKED-SETUP | UNCLE_HOME_AGENT=0 half observed: pty run, UI alive, zero claude descendants during run and after SIGINT, no preload note on the screen. The `--noui` half through `uncle --noui <headless action>` has not been run (a direct uncle_tui.py launch ignores the flag). Setup action: run it and capture `ps`. |
| MC-104 | YES | BLOCKED-HUMAN | No terminal multiplexer is available. A screen capture and timing cannot be taken from this worker. |
| MC-106 | YES | FAIL | Run under a pty (no tmux needed) from the PR worktree's uncle_tui.py, harness /private/tmp/claude-503/mc1.py. With PATH=/usr/bin:/bin the screen showed 'System: The home agent is unavailable (unavailable: claude is not on PATH); using the supervisor chat.' at startup, before any message. Defect: the preload surfaced the unavailable note. Fixed in uncle_tui.py (agent_preloading suppresses the note); after the fix the same run shows no startup note and a typed message produced no traceback. Regression test added. The post-fix run is the evidence for PASS, but this report keeps the first observation. |
| MC-107 | YES | BLOCKED-HUMAN | No interactive session is available to this worker. |
| MC-200 | YES | PASS | Run under a pty (no tmux needed) from the PR worktree's uncle_tui.py, harness /private/tmp/claude-503/mc1.py. Exactly one home-agent claude process alive before any input (the other claude child is the supervisor warm-up, distinguished by argv). Keystroke responsiveness was not measured. After SIGINT no descendants remained. |
| MC-201 | YES | BLOCKED-SETUP | Same as MC-102: opt-out half observed, `--noui` wrapper half not run. |
| MC-203 | YES | BLOCKED-HUMAN | No interactive session is available to this worker. |
| MC-206 | YES | FAIL | Same observation and fix as MC-106 (failed preload must be silent). After the fix: no startup note, message sent, UI alive, no traceback. The lazy-start path reports the unavailable note on first use (unit-tested). |
| MC-301 | YES | PASS | ps before typing: `72197 ppid 72195 python uncle_tui.py` / `72204 ppid 72197 python -B -c ... (subprocess wrapper)` / `72207 ppid 72204 claude -p --input-format stream-json ...`. Count of claude processes in the tree = 1. Note: an earlier attempt via the `./uncle` wrapper ran the installed /opt/homebrew copy of uncle_tui.py, not the worktree, so it was discarded. The result above is from the worktree's uncle_tui.py. The claude child is a grandchild via a wrapper process, not a direct child. |
| MC-302 | YES | PASS | /tmp/mc302.before, /tmp/mc302.during and /tmp/mc302.after PID snapshots (no new PIDs for --noui); /tmp/mc302.noui.out (banner, rc=0); pty run output with ps command lines for new PIDs 72541/72542 (supervisor runner only). Screen text ended with 'What can uncle do for you? ... Chat ready'. The only other note on screen was an unrelated gitignore message. Caveat: the UI run lasted 15s, and the supervisor claude process is separate from the home agent, so the verdict rests on its distinct argv. |
| MC-303 | YES | PASS | ps after quit: no rows for pid 72197 or any of its descendants. waitpid returned (72197, 33280), which is exit code 130. Before the quit, ps showed claude 72207 alive. A normal in-UI quit command was not confirmed, so the cleanup evidence covers only the Ctrl-C path. |
| MC-401 | YES | BLOCKED-SETUP | Reclassified from BLOCKED-HUMAN (audit FA-002): this is a `ps` check a machine can run, not a person's judgment. Observed under a pty with `UNCLE_HOME_AGENT=0 python3 uncle_tui.py`: process alive after 8s, curses title drawn, descendants of the UI during the run = none, `claude` descendants = 0, descendants after SIGINT = none. NOT observed: the `--noui` half through the real `uncle --noui <startup action>` wrapper (a direct `uncle_tui.py` launch ignores the flag and drew the UI, so that run proves nothing about `--noui`). Setup action to finish it: run `uncle --noui <a headless startup action>` and `ps` during it. |
| MC-402 | YES | BLOCKED-HUMAN | Split (audit FA-002). Machine-checkable half, post-quit cleanup: covered for the Ctrl-C path by MC-303 and by the MC-401 run above (no descendants after SIGINT); a normal in-UI quit command is still unconfirmed. Human-only half: whether the UI stalls perceptibly while typing during startup preload. That needs a person (or a keystroke-latency harness) and has no evidence. |
| MC-306 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
