# Verification report

## Findings

### MC-103

- **Action:** Ran `./uncle --noui` from the worktree (UNCLE_RUNTIME_ROOT set to worktree, env cleared, PATH = python3 dir + /usr/bin:/bin so no claude/codex CLI) piping 'hello there', '/help', '/quit' on stdin.
- **Expected result:** One-line error for the failed chat line, session survives and /help still answers, /quit exits cleanly.
- **Actual result:** Chat line produced one line: 'uncle --noui: chat failed: [Errno 2] No such file or directory: 'claude''. Session continued; /help printed the help text and command list; /quit exited with rc=0.
- **Defects:** None

### MC-107

- **Action:** Read the checklist row and inspected scripts/tests/repl-pty-test.py and repl-session-test.py for coverage. No live interactive session or real build was started.
- **Expected result:** Declining keeps the build running; confirming stops it first and exits; SIGTERM exits 143; no child processes remain.
- **Actual result:** Not performed live. A real build needs a real agent runner and an interactive PTY, and the worker contract forbids rerunning driver tests. The existing automated tests appear to cover parts of this row: repl-session-test.py asserts SIGTERM mid-build exits 143 and leaves no child, and repl-pty-test.py asserts /quit during a build exits 130. I did not find a decline-then-confirm /quit sequence in the grep output.
- **Defects:** None

### MC-108

- **Action:** Read the checklist row and inspected scripts/tests/repl-session-test.py for coverage. No live session was started.
- **Expected result:** Junk declines replacement; yes archives the old brief under .uncle/brief-history and proceeds; /mode reflects the new mode for later builds.
- **Actual result:** Not performed live. The grep found /mode and /mode attended checks in repl-session-test.py. It found no 'maybe' answer and no brief-history assertion, so the brief-replacement confirmation path was not shown as covered.
- **Defects:** None

### MC-203

- **Action:** Ran uncle_repl.py --attended in a real pty with a fake from-issue.sh driver that prints a human gate and does `read -r`. Run A: typed `yes` at the gate. Run B: sent Ctrl-D (EOF) at the gate. Run C: piped stdin `/mode unattended`, `build issue 2`, `/mode`, `/help`, `/quit` to check that later piped lines run in order after the build.
- **Expected result:** One typed line consumed per gate and recorded as human; EOF at a gate declines/stops and never approves; later piped lines run as normal prompts in order after the build; model output never answers a gate.
- **Actual result:** A: the driver received exactly `yes` (answer file = yes), the build completed, exit 0. B: Ctrl-D made the driver's read fail, so it declined ('EOF at gate: declined'); the REPL reported 'driver exited with status 3', no answer was written, and nothing was approved. C: the piped `/mode`, `/help` and `/quit` lines ran in order after the build completed, exit 0. Not observed: (1) the real build gate attestation record showing the answer recorded as human (the fake driver writes none; the existing pty test only confirms UNCLE_ATTENDED_STDIN=1 is set); (2) model output attempting to answer a gate (no real or fake model runner was exercised). Piping into an attended build is refused by design (exit 2, 'needs an interactive terminal').
- **Defects:** None. Setup needed: a real attended build run with the real driver (to inspect the gate attestation record) and a model runner that emits gate-like text (to confirm it cannot answer a gate).

### MC-207

- **Action:** With UNCLE_RUNTIME_ROOT overridden to this worktree (the ambient value pointed at a Homebrew install that lacks uncle_repl.py), piped four sessions into `uncle --noui` in a scratch git repo, with stdout and stderr captured separately. (1) A line of exactly 1048576 bytes then /quit. (2) A 1048577-byte line then /help. (3) A 1048577-byte line alone. (4) A 1048577-byte line, /help, /quit. I did not run the fake-runner ESC-laden reply scenario because no fake runner was set up.
- **Expected result:** The over-long line yields exactly one 'line too long' error on stderr. Its remainder is not run and the next line runs. Exit code is 2 if the error is the last event. No raw escape bytes in output.
- **Actual result:** The exactly-1048576-byte line was accepted and sent to the real chat runner. That runner failed with 'Chat runner reported an error: success', which is an environmental runner error, and the session exited 0. For each 1048577-byte line, stderr held exactly one line, 'uncle --noui: line too long (limit 1048576 bytes); discarded'. The following /help ran normally (help text on stdout), so the remainder was not run as a prompt. Exit was 2 in all three over-long sessions, including the one where the error was the last event. ESC byte count was 0 in all stdout and stderr captures. The ESC-laden model-reply scenario was not exercised.
- **Defects:** None (the ESC-laden fake-runner sub-scenario was conditional on a fake runner being available and was not run)

### MC-401

- **Action:** In a scratch git repo with stdin from /dev/null, ran `uncle --noui --noinput` and `uncle --noui --bogus-arg`, capturing stderr and exit code. Also ran the HEAD version of the launcher with `--noui --bogus-arg` for comparison.
- **Expected result:** `--noui --noinput` prints its existing error and exits 2; `--noui` with an unrecognized argument keeps its current error and exit code; neither starts the REPL.
- **Actual result:** `--noui --noinput`: stderr 'Error: --noui cannot be combined with --noinput' followed by usage, rc=2. `--noui --bogus-arg`: stderr 'Unknown argument: --bogus-arg' followed by usage, rc=2. Both returned immediately with no REPL. The HEAD launcher printed the identical 'Unknown argument' message and usage; its exit code was not captured because of a pipe, so the exit-code match with HEAD is not directly observed.
- **Defects:** None

### MC-402

- **Action:** In a scratch git repo, with a fake failing `claude`/`codex` runner first on PATH, ran `uncle --noui --application 'tiny hello app' </dev/null` unattended, capturing stdout, stderr and exit code, then grepped both for the 'uncle> ' prompt.
- **Expected result:** A single headless run prints plain progress with no REPL banner or `uncle> ` prompt, then exits with the usual code (0 on success, 1/2/3 on failure/refusal/gate stop).
- **Actual result:** Stdout carried plain timestamped progress lines ('[+00:00:00] UNATTENDED RUN...', 'Current workflow state: DERIVE_BRIEF', 'Launching agent (claude): requirements'). Stderr had the 'Mode: unattended' notice and 'uncle --noui: driver exited with status 1'. No REPL banner appeared, and 'uncle> ' matched 0 times on stdout and stderr. Exit code was 1, which is the failure code, because the fake runner failed. Only the failure path was exercised, since no real runner was available. The success exit code 0 was not observed.
- **Defects:** None

### MC-403

- **Action:** Ran `echo | ./uncle --noui --attended --application "test brief"` with non-tty stdin; captured stderr and exit code.
- **Expected result:** The existing refusal message is printed and the exit code is 2, unchanged from before.
- **Actual result:** Exit code 2. Stderr: 'Mode: attended. Each approval gate waits for your decision.' then 'uncle --noui: attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate.' No stdout.
- **Defects:** None

### MC-404

- **Action:** Launched ./uncle (no --noui) in a 120x40 pty via python pty.fork, waited for the home screen, typed 'build issue 1' + Enter, then '/help' + Enter, then Esc/q/Ctrl-C. Captured the pty output.
- **Expected result:** TUI renders normally with curses, home chat replies, and the issue request is still recognized as before; no import or startup errors appear.
- **Actual result:** Curses TUI home screen rendered (menu: New application / From GitHub issue / Change request / Resume / Configure / Quit, logo, chat prompt 'Describe an app or a change…', status 'claude-sonnet-5-5 (low) · Chat ready'). 'build issue 1' was recognized as an issue request: the TUI switched to an 'uncle issue #1' build view, printed 'Preparing worktree', created a worktree and branch, 'Wrote CHANGE_REQUEST.md', 'Starting the change workflow from this issue', and listed the stage panel. No import or startup errors appeared in the capture. The '/help' slash command output was not observed separately: the build view had taken over the screen, and the capture shows no /help-specific reply. A free-form home-chat reply was also not observed, because the first input launched a build. Side effect: this live run created a real sibling worktree (uncle-issue-165-issue-1) and branch uncle/help. I killed the process and removed both afterwards; git worktree list showed them gone.
- **Defects:** None logged. The check is only partly covered: the curses home screen and issue-request recognition were verified, but the /help slash command and a home-chat reply were not observed. Rerun with '/help' typed before the issue request, or with a stubbed issue launcher, to cover them.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-103 | YES | PASS | Captured output: banner; 'uncle --noui: chat failed: [Errno 2] No such file or directory: 'claude''; 'Type a message to chat, or a request such as 'build issue 12'.'; 'Commands: /help /mode ... /quit'; exit code 0. Note: the inherited env UNCLE_RUNTIME_ROOT pointed to a missing homebrew libexec, so it was overridden to the worktree for this run (setup artifact, not a product defect). Run was piped stdin, not a PTY. |
| MC-107 | YES | NOT RUN | grep of scripts/tests/repl-session-test.py lines 131-165 and scripts/tests/repl-pty-test.py lines 89-134. I did not execute these tests and did not read their results from the green-check. |
| MC-108 | YES | NOT RUN | grep of scripts/tests/repl-session-test.py lines 100-120. Nothing was executed. |
| MC-203 | YES | BLOCKED-SETUP | Temporary scripts /tmp/mc203/t.py and /tmp/mc203/u.py. Transcript A: 'Human gate: approve? [y/N]' then 'got:[yes]' then 'Workflow complete.'. Transcript B: '^D' then 'EOF at gate: declined' then 'uncle --noui: driver exited with status 3'. Run C output: 'mode: unattended', 'building', 'Workflow complete.', 'mode: unattended', help text, exit 0. |
| MC-207 | YES | PASS | in1: exit 0, stderr 'chat failed: Chat runner reported an error: success'. in2: exit 2, stderr 61 bytes, one 'line too long' line, stdout shows the /help output. in3: exit 2, one 'line too long' error. in4: exit 2. `grep -c` for \x1b returned 0 on every stdout and stderr file. |
| MC-401 | YES | PASS | Terminal capture: '--noinput rc=2 / Error: --noui cannot be combined with --noinput / Usage: uncle ...'; '--bogus-arg rc=2 / Unknown argument: --bogus-arg / Usage: uncle ...'; old launcher: 'Unknown argument: --bogus-arg / Usage: uncle ...'. |
| MC-402 | YES | PASS | EXIT 1; grep -c 'uncle> ' returned 0 for both the stdout and stderr captures; the stdout excerpt above is from the run. |
| MC-403 | YES | PASS | exit=2; stderr as quoted above (captured in /tmp/e403). Did not compare against pre-change source text; the refusal message is clear and the exit code matches. |
| MC-404 | YES | FAIL | Captured pty stream (~11.7KB) showing the curses home screen, then 'issue #1 User: build issue 1', 'Preparing worktree (new branch 'uncle/help')', 'Created worktree ... on branch uncle/help', 'Wrote .uncle/docs/CHANGE_REQUEST.md', 'Starting the change workflow from this issue'. No Traceback or ImportError text. |
