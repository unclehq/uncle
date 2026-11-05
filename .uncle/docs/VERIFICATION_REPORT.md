# Verification report

## Findings

### MC-101

- **Action:** Ran the worktree's ./uncle with inherited UNCLE_* env vars cleared. The inherited UNCLE_LIB_DIR pointed at the installed Homebrew copy, which lacks uncle_headless.py. Used three scratch git repos under /tmp, each wrapped in a 20-25s timeout: (a) `uncle --noui --housekeeping </dev/null`, then `uncle --noui --housekeeping "report the current directory name only"`; (b) `uncle --noui --issue 1 </dev/null`, once with no remote and once with a fake github.com origin; (c) `echo 'change text' | uncle --noui --change-request`.
- **Expected result:** Each workflow starts headlessly with plain text output. Change-request text comes from stdin and CHANGE_REQUEST.md is written. Issue run creates its worktree.
- **Actual result:** Change-request: PASS. Plain-text log with no curses, the stdin text was used, .uncle/docs/CHANGE_REQUEST.md contains 'change text', the change-plan agent launched, and the 25s timeout cut the run (exit 124). Housekeeping: bare use with no stdin was refused with 'Error: --housekeeping text cannot be empty' and exit 2. With text it started headlessly, printed plain text with [+hh:mm:ss] stamps, and the agent answered, but the runner ended with 'driver stopped without completing (gate or blocked); exit 3' after the agent's reply. The usage text says exit 0 on completion, so this exit code is unexplained and needs a look. Issue: the headless runner started and printed plain text. It stopped with exit 1 ('No git remote found' and then 'Failed to fetch issue unclehq/nonexistent-zz#1'). The issue-to-worktree path was not exercised because it needs a real GitHub issue with gh or network access, and this stage has network disabled (UNCLE_STAGE_NETWORK=false). No worktree was created.
- **Defects:** None. Two follow-ups: (1) Set up a real GitHub issue reachable by gh or network, or a stub, then rerun the `--issue` part. (2) Confirm whether exit 3 for a completed `--noui --housekeeping` run is intended.

### MC-102

- **Action:** In a scratch git repo (/tmp/mc102), ran the repo's ./uncle for the five refusal cases: `--noui`; `--noui --noinput --application x`; `--noui --attended --application x </dev/null`; `echo t | --noui --attended --change-request`; `--noui --application ''`. Recorded stderr/exit and compared `git worktree list` before and after. The shell had an inherited UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec, which made case 3 fail on a missing homebrew uncle_headless.py. I reran case 3 with UNCLE_RUNTIME_ROOT set to the repo, then reran the others as well.
- **Expected result:** Each prints a reason on stderr and exits 2. No driver starts, no worktree is created, and the run never falls back to unattended mode or the menu.
- **Actual result:** All five cases exited 2 with a reason on stderr. (1) 'Error: --noui needs a startup action ... the menu is never shown'. (2) 'Error: --noui cannot be combined with --noinput'. (3) 'uncle --noui: attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate.' (4) 'uncle: attended mode needs an interactive terminal on stdin, or stdin left free to answer gates ...'. (5) 'Error: --application text cannot be empty'. Stdout was empty in every case. No driver started, no menu appeared, and `git worktree list` was identical before and after. In the rerun, one invocation of case 2 exited 1 ('Unknown argument') because my shell loop passed the arguments as a single quoted string. That was a harness quoting error, not a product result, and the earlier correct invocation of case 2 gave exit 2.
- **Defects:** None

### MC-103

- **Action:** Not performed. Read the checklist row only. The row needs a real interactive terminal and a live attended run (`uncle --noui --attended --application ...`) that reaches a human gate. A person has to type an approval line, and then press Enter on a blank line or Ctrl-D in a second run.
- **Expected result:** The gate prompt prints and one line is read from the terminal. A typed approval is recorded as a human approval. A blank line or EOF counts as not approved and the run exits 3.
- **Actual result:** No live run was executed. This worker has no interactive terminal and cannot supply the human approval keystrokes. Running the full attended driver would also start real agent stages, which the compact worker policy does not allow.
- **Defects:** None. A person must run the attended command in a real terminal, type an approval at the gate once, then repeat with a blank line or Ctrl-D, and record the transcript and exit codes.

### MC-105

- **Action:** Inspected scripts/tests/headless-run-test.py to see which signal behaviours automated tests already cover. Did not start a live `uncle --noui` run: it needs an interactive terminal for Ctrl+C and a real agent-backed driver.
- **Expected result:** The runner exits 130 for SIGINT and 143 for SIGTERM. The driver process group is stopped, with an immediate kill on a second signal, and no orphan processes remain. The run state is resumable.
- **Actual result:** Not performed live. The checklist requires a human to press Ctrl+C in a real terminal and to observe the process list and a resume attempt on a long-running run. This worker has no interactive terminal and was told not to rerun the driver's automated tests. headless-run-test.py contains simulated-signal tests: exit 143 on SIGTERM, 130 on SIGINT, and a SIGTERM-ignoring driver being killed on a second signal. These are not live observations of the real command and do not show orphan-process or resume behaviour. The test file is evidence of what exists, not a PASS.
- **Defects:** None

### MC-106

- **Action:** In a scratch git project, ran `uncle --application x` with UNCLE_NOUI=1, 0, empty, and true, with a stub python3 first on PATH (and UNCLE_SKIP_UPGRADE=1) that reports which script the launcher dispatches to, so no real build or agent started. Ran `uncle --help` and read the full text.
- **Expected result:** Only UNCLE_NOUI=1 runs headless. 0, empty and true start the normal TUI path silently. --help documents --noui, UNCLE_NOUI, the exit codes, the attended requirement, and how --noui differs from --noinput.
- **Actual result:** UNCLE_NOUI=1 dispatched to uncle_headless.py. UNCLE_NOUI=0, empty and true each dispatched to uncle_tui.py, with no warning or error output beyond the normal unattended-mode banner. --help includes: '--noui (or UNCLE_NOUI=1) runs a startup action headlessly', that it requires one of --application/--issue/--change-request/--housekeeping (otherwise exit 2), that it cannot be combined with --noinput, that 'Unlike --noinput (the TUI's no-keyboard mode, which still draws the curses UI), --noui never starts the UI', 'Attended needs a tty on stdin', and 'Exit codes: 0 completed; 1 driver failed; 2 refused before start; 3 stopped at a gate or needs a signed commit; 130/143 interrupted by SIGINT/SIGTERM'. The stub did not exercise the real TUI, so only the dispatch decision was observed, not the UI itself.
- **Defects:** None

### MC-201

- **Action:** Ran the worktree launcher as `uncle --noui --application "tiny app" </dev/null` in disposable empty dirs (UNCLE_RUNTIME_ROOT pointed at the worktree, inherited UNCLE_* worker env scrubbed after the first attempt was contaminated by it). Also tried `--attended` with stdin closed.
- **Expected result:** The run never reads stdin, records nothing as human-approved, names the gate on stderr and exits 3.
- **Actual result:** Exit 3 was not produced. Default (unattended) run with stdin closed completed the whole build, exit 0, verdict READY_WITH_NON_BLOCKING_ISSUES; gates were delegated to the agent and approval files were written (.uncle/workflow/approvals/*.approved-by), so no gate stop occurred. `--attended` with closed stdin was refused up front: exit 2, 'attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate'. A first run inheriting the outer worker env exited 1 (artifact delivery path collision) and is invalid. The exit-3 gate-stop path needs a setup where an unattended gate is deliberately left unmet; I could not arrange one with a real agent. Unit coverage of exit 3 exists in scripts/tests/headless-run-test.py (test_gate_named_on_stderr) but was not run by me. I did not verify the contents of the approved-by files, so I did not confirm who recorded the approvals.
- **Defects:** None. Setup needed: a fixture or stub agent that leaves the first human gate unapproved (as headless-run-test.py does), so the exit-3 path can be exercised live with stdin closed.

### MC-202

- **Action:** Read the checklist row only. Did not run the attended flow: it requires a person at a real terminal to type an approval line at a gate, then press Ctrl+D or Enter on a blank line at a later gate.
- **Expected result:** The typed approval is recorded as a human approval; EOF or a blank answer is treated as not approved and the run stops with exit 3.
- **Actual result:** Not performed. A human approval is the thing under test, and an agent-typed approval would not count as one.
- **Defects:** None. Waiting on the operator to run `uncle --noui --attended --application "tiny app"` in a real terminal, type an approval at the first gate, then rerun and press Ctrl+D or Enter on a blank line, and record the exit statuses and attestation entries.

### MC-203

- **Action:** Ran ./uncle (repo copy) with stdin </dev/null for each refusal case, capturing exit status and stderr, and compared `git status --porcelain` and `git worktree list` before and after. Cases: `--noui`; `--noui --noinput --issue 1`; `--noui --attended --issue 1`; `--attended --housekeeping`; `echo text | --noui --attended --change-request` (run in a fresh empty git repo, since the project already had CHANGE_REQUEST.md).
- **Expected result:** Each case prints a reason on stderr, exits 2, starts no driver and writes no state.
- **Actual result:** Case 1 (`--noui`): exit 2, 'needs a startup action', no state. Case 2 (`--noui --noinput --issue 1`): exit 2, 'cannot be combined with --noinput'. Case 5 (change-request with piped text): exit 2, 'attended mode needs an interactive terminal on stdin...', and the fresh repo had no files or worktrees created. Case 3 (`--noui --attended --issue 1 </dev/null`): NOT refused. It printed 'Mode: attended. Each approval gate waits for your decision.', started the driver and exited 1 on a missing /opt/homebrew/opt/uncle/libexec/scripts/lib/uncle_headless.py. Expected exit 2 with a refusal. Case 4 (`--attended --housekeeping`, no --noui): exit 1, not 2. The stderr says attended mode needs an interactive terminal; it does not say --attended requires --noui. No git status or worktree changes in the project. The `--noui --attended --issue` run failed because the launcher resolved to the Homebrew-installed libexec, which lacks the new headless module. Even so, the refusal was not issued before the driver started.
- **Defects:** Proposed: `--noui --attended --issue 1 </dev/null` starts a driver instead of exiting 2, and `--attended --housekeeping` exits 1 instead of 2. Not yet in DEFECTS.md.

### MC-204

- **Action:** Drove scripts/lib/uncle_headless.py run() (the engine behind uncle --noui --housekeeping) with a fake driver (python that spawns a child `sleep 301` and sleeps). A real housekeeping agent was not launched, to avoid cost and side effects. Ran three cases and listed processes with ps before and after: (1) SIGTERM once, (2) SIGINT once, (3) driver ignoring SIGTERM, with a second SIGTERM sent 1s after the first and a 3s grace period.
- **Expected result:** Exit 143 for SIGTERM and 130 for SIGINT; no driver child processes remain; a second signal kills the group immediately; the run can be resumed.
- **Actual result:** SIGTERM gave exit 143 and SIGINT gave exit 130. Before the signal, ps showed 2 processes (driver and child); afterward it showed 0 in every case. With the SIGTERM-ignoring driver, the second signal ended the run with exit 143 within about 1s, before the 3s grace period would have expired, and no processes remained. Not verified: resumability of the run after the signal, and the real `uncle --noui --housekeeping` launcher path, which was exercised only through the fake driver.
- **Defects:** None (exit codes and process cleanup passed; the resume clause and real-launcher path were not executed, so the row is not marked PASS)

### MC-206

- **Action:** Ran the worktree `uncle --housekeeping x` launcher with UNCLE_NOUI=1, 0, empty and true, using a stub python3 first on PATH so it printed the entry point it would exec instead of starting a real TUI or agents (non-tty, stdin from /dev/null). Then ran scripts/lib/uncle_headless.py with UNCLE_STARTUP_ACTION=housekeeping and UNCLE_STARTUP_TEXT_FILE pointing at a symlink, in an empty scratch dir.
- **Expected result:** Only exactly `1` gives plain headless output; other values silently start the normal TUI; an untrusted symlinked text file is refused with exit 2 and no driver starts.
- **Actual result:** UNCLE_NOUI=1 exec'd uncle_headless.py with NOUI=1. UNCLE_NOUI=0, empty and true all exec'd uncle_tui.py with no error or warning. The symlinked text file was refused with 'uncle --noui: cannot read startup text file: untrusted text file', exit 2, and the scratch dir stayed empty. Caveats: the curses UI was not observed on a real tty (the dispatch was observed through the stub, not the screen). The launcher resolved its ROOT to the installed copy /opt/homebrew/opt/uncle/libexec rather than the worktree, though that copy has the same --noui dispatch. The symlink check ran the headless module directly, not through the launcher's --noui flag.
- **Defects:** None

### MC-303

- **Action:** Read the checklist row only. Did not run `uncle --noui --attended` because it needs a real interactive terminal with a human typing at the gate prompt, and a full run would start real agent stages.
- **Expected result:** The gate prompt is printed and the typed answer is read from the terminal and recorded as a human approval. A blank or EOF answer is treated as not approved and the run stops with exit code 3.
- **Actual result:** Not performed. The check needs a human at a real terminal to type an answer and then press Enter or Ctrl+D. No transcript, exit codes or gate state were captured.
- **Defects:** None

### MC-304

- **Action:** In fresh empty git repos (with inherited UNCLE_* driver env vars unset for the final runs), ran: (1) uncle --noui --attended --application x </dev/null; (2) uncle --noui; (3) uncle --noui --noinput --application x; (4) echo hi | uncle --noui --attended --change-request. Captured stderr, exit codes, and directory listings before/after.
- **Expected result:** Each prints a reason on stderr, exits 2, and starts no driver or state.
- **Actual result:** Cases 2, 3, 4 each printed a reason on stderr and exited 2 (case 2: '--noui needs a startup action...'; case 3: '--noui cannot be combined with --noinput'; case 4: 'attended mode needs an interactive terminal on stdin...'), with directory unchanged. Case 1 exited 2 with stderr 'uncle --noui: attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate.', but it first printed 'Mode: attended...' on stdout and left a new .uncle/docs/REQUIREMENTS.md in the previously empty repo, so state was created before rejection, contradicting 'starts no state'. (Run without unsetting inherited driver env, case 1 instead tried to exec a nonexistent /opt/homebrew/opt/uncle/libexec/scripts/lib/uncle_headless.py - environment contamination, not counted.)
- **Defects:** New: uncle --noui --attended --application x with non-tty stdin writes .uncle/docs/REQUIREMENTS.md before the stdin check rejects (exit 2)

### MC-401

- **Action:** In a scratch git project, ran `uncle --application "tiny demo"` (no --noui) under a real pty (python pty.fork), waited ~12s, sent 'q' then Ctrl+C, and captured the terminal output.
- **Expected result:** The curses TUI starts as before, runs unattended by default, and no headless/plain-text runner output appears.
- **Actual result:** Startup printed 'Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.' then entered the curses alternate screen (\x1b[?1049h) with STAGE/TOTALS panes, 'Talk to uncle while he builds' input, 'mode(auto)' status, and an UNATTENDED RUN banner. About 290 escape sequences were captured, and no headless plain-text runner output appeared. The process exited with status 0 after the quit keys, and the scratch dir received REQUIREMENTS.md and .uncle state.
- **Defects:** None

### MC-402

- **Action:** Ran `./uncle --noui --noinput --application x </dev/null` capturing stdout/stderr and exit code. Inspected uncle lines 232-239 and 473-482 for the `--noinput --application` TUI path. Did NOT run `uncle --noinput --application "tiny demo"`, because it would start a real agent-driven build (cost, side effects) in this worktree.
- **Expected result:** First command still runs the TUI path in no-keyboard mode, unchanged. Second is refused with a stderr message and exit 2, and nothing is started.
- **Actual result:** Second half observed: exit code 2, stdout empty, stderr 'Error: --noui cannot be combined with --noinput' followed by usage; nothing started. First half not executed live. Code inspection shows `--noinput` without `--noui` still goes to `uncle_run_tui python3 uncle_tui.py --noinput` (uncle:482).
- **Defects:** None

### MC-403

- **Action:** Ran the uncle launcher from an empty scratch dir (/tmp/mc403) with stdin piped from `printf 'q\n'` and stdout redirected to a file (no tty), with UNCLE_NOUI unset, =0, = (empty), and =true; also ran UNCLE_NOUI=0 with stdin from /dev/null (EOF). Captured stdout and exit codes.
- **Expected result:** Line-based menu appears in every case; UNCLE_NOUI values other than exactly 1 are silently ignored (no headless run, no error).
- **Actual result:** In all five invocations (unset, 0, empty, true, EOF) the line menu printed: '1) New application, 2) From GitHub issue, 3) Change request, 4) Configure stages, q) Quit' followed by 'Choose [1-4/q]:'. Exit code 0 each time. No headless run output and no error text.
- **Defects:** None

### MC-404

- **Action:** In a fresh temp git project containing CHANGE_REQUEST.md ('orig'), ran `uncle --change-request` with request text piped on stdin, once with --noui and once without (non-interactive shell, not a real TTY).
- **Expected result:** Both refuse the existing CHANGE_REQUEST.md without overwriting it; non-noui keeps prior behavior; --noui exits non-zero without starting a driver.
- **Actual result:** Both printed 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.' --noui exited 2; non-noui exited 1. CHANGE_REQUEST.md still contained 'orig' after both runs; no .uncle or driver artifacts were created (only .git, CHANGE_REQUEST.md and the output logs). Caveat: executed with piped stdin rather than an interactive real terminal, so TUI rendering was not observed; the refusal path is identical text.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | BLOCKED-SETUP | Scratch dirs /tmp/mc101b-* and /tmp/mc101c-* with out.txt in each. Exit codes: change-request 124 (timeout after a successful start), housekeeping empty 2, housekeeping with text 3, issue 1. `git worktree list` showed only the main worktree in each scratch repo. The change-request scratch repo has .uncle/docs/CHANGE_REQUEST.md containing 'change text'. |
| MC-102 | YES | PASS | Per-case exit=2 and the stderr messages above. The `diff` of `git worktree list` output reported 'worktrees unchanged'. Case 3 first showed exit 2 from the wrong homebrew runtime root (environmental, not counted). The rerun against the repo runtime printed the real refusal at exit 2. |
| MC-103 | YES | BLOCKED-HUMAN | None collected. Prepared PTY tests (scripts/tests/pty_helper.py, headless-run-test.py) may cover the gate-read logic through the driver green-check. They were not read or cited as covering this row, and they do not replace the real-terminal observation the row asks for. |
| MC-105 | YES | BLOCKED-HUMAN | scripts/tests/headless-run-test.py lines 69-93 and 246-305 (exit-code mapping, SIGTERM-ignored driver killed, double SIGINT gives 130). No live transcript, ps listing or resume attempt was captured. |
| MC-106 | YES | PASS | Stub output: 'STUB python3 uncle_headless.py NOUI=1'; 'STUB python3 uncle_tui.py NOUI=0'; 'STUB python3 uncle_tui.py NOUI='; 'STUB python3 uncle_tui.py NOUI=true'. uncle line 411 tests UNCLE_NOUI == 1 exactly. `./uncle --help` output read directly. |
| MC-201 | YES | BLOCKED-SETUP | rc.txt exit=0 in /var/folders/.../tmp.ifAzTVWamP; exit=2 attended refusal message on stderr in tmp.u32LWztcHG; exit=1 contaminated run in tmp.vhVuOiVyC0; exit=2 in tmp.y8VByDihch (stale installed runtime lacking uncle_headless.py). Default launcher mode text: 'Mode: unattended (default). Approval gates are delegated to the agent'. |
| MC-202 | YES | BLOCKED-HUMAN | No commands run for this check. The row's evidence (terminal transcript, exit statuses, gate attestation entries) needs a human-driven session. |
| MC-203 | YES | FAIL | Observed exits: A=2, B=2 (case 2), case 3 stdout 'Mode: attended...' followed by a Python 'can't open file .../uncle_headless.py' error, case 4 exit=1. git status --porcelain was identical before and after. The new-repo case 5 listing was empty apart from .git. |
| MC-204 | YES | NOT RUN | Shell loop output: term exit=143 after=0; int exit=130 after=0; ign exit=143 (second-signal elapsed 0s by `date +%s`) after=0. Scripts at /tmp/mc204/w.py. The first pass used an invalid `sleep` argument; the second pass with `sleep 301` confirmed 2 processes before and 0 after. |
| MC-206 | YES | PASS | Stub output: 'STUB python3 .../scripts/lib/uncle_headless.py NOUI=1' for 1; '.../uncle_tui.py NOUI=0', 'NOUI=' and 'NOUI=true' for the rest, all rc=0. Symlink run: rc=2, empty scratch dir. Source: uncle:411 (exact == 1 comparison) and scripts/lib/uncle_headless.py:340 (islink refusal). The driver green-check covers scripts/tests/launcher-noui-test.sh. |
| MC-303 | YES | BLOCKED-HUMAN | The checklist row requires typed human input at a gate in a real terminal. No live run was made. The driver green-check was not cited because it was not read, so no automated PTY coverage is claimed. |
| MC-304 | YES | FAIL | Case 1 clean-env: exit=2; find . -path ./.git -prune -o -print listed ./.uncle, ./.uncle/docs, ./.uncle/docs/REQUIREMENTS.md. Cases 2-4: exit=2, directory listing identical before/after (UNCHANGED). |
| MC-401 | YES | PASS | pty transcript from /tmp/mc401.py: 5204 bytes captured, 'exit 0 0', alt-screen enter sequence present, 'Mode: unattended (default)' line present. |
| MC-402 | YES | NOT RUN | rc=2; /tmp/e402.txt begins 'Error: --noui cannot be combined with --noinput'; /tmp/o402.txt empty. Source: uncle:238-239, uncle:481-482. scripts/tests/launcher-noui-test.sh:16 asserts the same exit 2. |
| MC-403 | YES | PASS | Captured /tmp/mc403/out_UNSET.txt, out_0.txt, out_EMPTY.txt, out_true.txt, out_eof.txt; each shows identical menu and 'exit=0'. |
| MC-404 | YES | PASS | noui exit=2, tui exit=1, cat CHANGE_REQUEST.md -> orig, ls -A -> .git CHANGE_REQUEST.md o1 o2 |
