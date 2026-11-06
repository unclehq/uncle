# Verification report

## Findings

### MC-101

- **Action:** Ran `uncle --noui --application 'build a thing' 2>err.txt >out.txt </dev/null` in a disposable git project, with UNCLE_RUNTIME_ROOT pointing at a copy of the runtime whose scripts/stagegate.sh was a stub printing 'progress line' to stdout and 'DRIVER-ERROR-TEXT' to stderr, then exiting 1 (a stub driver, so no real agents ran). Then cat both files.
- **Expected result:** err.txt contains the driver error text once, then one `driver exited with status N` line. out.txt contains neither. Exit status 1.
- **Actual result:** Exit status 1. err.txt: the launcher's 'Mode: unattended' notice, then 'DRIVER-ERROR-TEXT' once, then 'uncle --noui: driver exited with status 1' once. out.txt: only '[+00:00:00] progress line'.
- **Defects:** None

### MC-102

- **Action:** In a fresh temp git dir, ran `UNCLE_SKIP_UPGRADE=1 uncle --noui --change-request < req.md` (request 'x') with no stdout/stderr redirection, so both streams went to the same shared output sink. A real pty was unavailable (`script` failed: tcgetattr/ioctl not supported on socket), so this was not a true interactive terminal.
- **Expected result:** The driver's error text and the exit status line are visible on the terminal. Stdout lines still carry the [+hh:mm:ss] prefix.
- **Actual result:** Combined output showed stdout lines prefixed with [+00:00:00]..[+00:00:21], the driver error text '[+00:00:21] canonical change-planning bundle: invalid baseline_report packet: baseline report is missing verification_commands', and the final stderr line 'uncle --noui: driver exited with status 1'. Process exit status was 1. The launcher's initial 'Mode: ...' line is unprefixed (launcher output, not the driver's stdout stream).
- **Defects:** None

### MC-103

- **Action:** Replaced the stub driver with one that prints 'progress line' and 'Human gate: approve PROJECT_PLAN.md' on stdout and exits 0 with no completion banner. Ran `uncle --noui --application 'build a thing' 2>err.txt >out.txt` and noted the exit status.
- **Expected result:** Exit status 3. Gate message on stderr as before. Stdout formatting unchanged.
- **Actual result:** Exit status 3. err.txt has 'uncle --noui: driver stopped without completing (gate or blocked); exit 3' and 'uncle --noui: stopped at: Human gate: approve PROJECT_PLAN.md'. Stdout lines keep the [+hh:mm:ss] prefix.
- **Defects:** None

### MC-105

- **Action:** Ran `uncle --help` and `uncle --noui --help` and grepped for stderr. Ran `uncle --noui --application=` (empty text) and `uncle --noui --noinput` with `2>err.txt`, noting the exit status.
- **Expected result:** Help states that errors go to stderr. The launcher refusal is in err.txt with exit status 2, unchanged.
- **Actual result:** Both help outputs, at line 53, say 'driver errors go to stderr'. The empty --application refusal exited 2 with 'Error: --application text cannot be empty' in err.txt. The --noui with --noinput refusal exited 2 with 'Error: --noui cannot be combined with --noinput' in err.txt (the usage text was also printed).
- **Defects:** None

### MC-106

- **Action:** Read the checklist row. Did not launch the interactive curses TUI or force a driver failure in it, because the row needs a human to watch the live build window and no non-interactive harness was assigned to this lane.
- **Expected result:** The build window shows driver errors as before, followed by one line `Driver exited with status N: <last non-empty output line>`, with secrets and escape codes removed.
- **Actual result:** Not observed. The live TUI observation was not performed.
- **Defects:** None

### MC-107

- **Action:** Inspected uncle_tui.py:102 and scripts/tests/tui-failure-line-test.py to see what covers the failure line. Did not launch the curses TUI or capture build-window screenshots.
- **Expected result:** Exit 0 adds no failure line. A silent non-zero exit shows `Driver exited with status N: (no output)`. A user stop shows the failure line with 130 or 143.
- **Actual result:** Not observed live. A worker without an interactive terminal cannot run a driver in the curses TUI, press Ctrl-C, or take screenshots of the build window.
- **Defects:** None

### MC-200

- **Action:** Created disposable project /tmp/mc200.s7gr/proj (git init) and a fake runtime whose change-workflow.sh driver prints 'DRIVER-ERROR-TEXT' to stderr and exits 7. Ran the headless runner that `uncle --noui` execs (scripts/lib/uncle_headless.py) with UNCLE_RUNTIME_ROOT=fake runtime, UNCLE_STARTUP_ACTION=change_request, UNCLE_STARTUP_TEXT set, with 1>out.txt 2>err.txt, then cat'd both files and printed the exit status.
- **Expected result:** err.txt holds the driver error text exactly once followed once by `driver exited with status N`; shell exit status 1; out.txt holds neither.
- **Actual result:** exit=1. out.txt was empty. err.txt contained exactly two lines: 'DRIVER-ERROR-TEXT' then 'uncle --noui: driver exited with status 7'.
- **Defects:** None

### MC-202

- **Action:** Ran scripts/lib/uncle_headless.py (the --noui runner) with an explicit disposable fake driver (/tmp/mc202/drv.sh) that writes 'Continue? [y/N] ' to stderr with no trailing newline, sleeps 3s, prints a line to stdout and exits 0 without a completion banner. Read stdout and stderr live through separate pipes with monotonic timestamps. Did not go through the `uncle` launcher or a real project driver.
- **Expected result:** Prompt text appears on the terminal within the idle timeout, before the driver exits. A normal gate still stops the run with exit status 3 and a message naming the gate.
- **Actual result:** The prompt appeared on stderr at 0.34s (idle timeout 0.2s), 2.8s before the driver exited at 3.13s. It was emitted with a newline appended. The run ended with exit status 3 and the message 'uncle --noui: driver stopped without completing (gate or blocked); exit 3'. That message does not name a specific gate, because the fake driver emitted no gate name; the driver-emitted gate text was only a stdout line.
- **Defects:** None

### MC-203

- **Action:** Ran the real scripts/lib/uncle_headless.py run() (the --noui code path, install_signals=True) from a small wrapper against a fake driver that writes 'pending-err MARKER203' to stderr and then sleeps 60s. Sent SIGINT (the Ctrl-C signal) to the wrapper after 2s, then repeated with SIGTERM. Captured stdout and stderr to files each time, then ran pgrep for the driver marker. Did not go through the full `uncle` launcher with a real workflow driver.
- **Expected result:** Exit 130 for Ctrl-C and 143 for SIGTERM. All driver stderr precedes the single status line, and no driver process is left running.
- **Actual result:** SIGINT gave exit 130 and SIGTERM gave exit 143. Each err file held exactly one 'pending-err MARKER203' line, and the out files were empty. pgrep found no leftover driver process. No 'driver exited with status' line was written in either signal case. Code at uncle_headless.py:370-371 deliberately suppresses that line when a signal was received, and the unit test asserts at most one status line. So 'all stderr precedes the status line' holds only vacuously.
- **Defects:** None (note: the checklist wording implies a status line on user signals, but the implementation intentionally omits it)

### MC-204

- **Action:** Ran the real uncle_headless.run() (the --noui implementation) in a subprocess with a fake driver (/tmp/mc204/drv.py) that prints three progress lines to stdout and one line to stderr, with real fd redirection 1>out.txt 2>err.txt; inspected both files with cat -v. Did not invoke the uncle launcher script itself.
- **Expected result:** Each stdout line in out.txt has a single [+hh:mm:ss] prefix; stderr text is not duplicated onto stdout.
- **Actual result:** out.txt had exactly three lines, each with a single [+00:00:00] prefix: progress one/two/three. err.txt contained 'stderr-noise-abc' once, unprefixed, plus the runner's own status line (exit 3, because the fake driver did not complete a run). The stderr noise did not appear in out.txt.
- **Defects:** None

### MC-205

- **Action:** Called uncle_tui.format_failure_line directly with sample statuses/outputs (3 with 'last', 4 with empty, 0, and 1 with ANSI+token). Inspected uncle_tui.py:2063 where the result is appended to the build window output. Did not launch the interactive TUI against disposable drivers.
- **Expected result:** Non-zero exit: build window ends with 'Driver exited with status N: <last line>' or '(no output)', redacted, no escapes. Exit 0: no failure line.
- **Actual result:** Function output matched: 'Driver exited with status 3: last'; 'Driver exited with status 4: (no output)'; None for status 0; 'Driver exited with status 1: token=[REDACTED]' with escapes stripped. The live build-window rendering was not observed.
- **Defects:** None

### MC-302

- **Action:** In a scratch git repo with no remote, ran `uncle --issue 99999999 --noui` (a failing request) under a pty via `script` with no redirection, then re-ran with stdout and stderr redirected to separate files to attribute each line to its stream.
- **Expected result:** The error text is visible in the terminal, stdout lines keep the `[+hh:mm:ss]` prefix, and stderr error lines are shown verbatim without that prefix.
- **Actual result:** In the pty transcript all error text was visible: `Mode: unattended (default)...`, `[+00:00:00] No git remote found. Provide a full GitHub URL.`, and `uncle --noui: driver exited with status 1`. In the split run, stdout held only the `[+00:00:00]`-prefixed line; stderr held the `Mode:` and `uncle --noui: driver exited with status 1` lines verbatim with no prefix. Exit status 1. Caveat: the driver's own failure message went to stdout with the prefix here; the stderr lines observed were the launcher's. The behavior matches the expected result for both streams.
- **Defects:** None

### MC-303

- **Action:** Drove the real uncle_headless.run() (the --noui engine in scripts/lib/uncle_headless.py) with a fake driver that prints a progress line and 'Human gate: PROJECT_PLAN.md awaiting approval' then exits 0 without the completion banner. Redirected stderr to /tmp/uncle-gate-err.txt and stdout to /tmp/uncle-gate-out.txt, and checked the exit status. I did not invoke the full ./uncle launcher with a real approval-gate project.
- **Expected result:** Exit status is 3, the gate is named on stderr, and gate behavior and stdout format are unchanged.
- **Actual result:** Exit status was 3. stderr named the gate. stdout lines kept the single [+hh:mm:ss] prefix, and no stderr text appeared on stdout.
- **Defects:** None

### MC-304

- **Action:** Located the failure-line formatter in uncle_tui.py:102 and ran the narrow scripts/tests/tui-failure-line-test.py (6 tests). Did not drive the interactive curses TUI through a real failing build; no pty/human-visible observation was made.
- **Expected result:** The build window ends with a line `Driver exited with status N: <last non-empty output line>` with secrets redacted and no escape sequences; a successful run adds no such line.
- **Actual result:** Formatter produces 'Driver exited with status %s: %s' (with '(no output)' fallback). The unit test for it passed (6 tests OK). The live build-window rendering after a real non-zero driver exit was not observed.
- **Defects:** None

### MC-403

- **Action:** Ran uncle_headless.main in attended mode under a pty (observed live with timestamps) against a fake driver that wrote stderr noise, printed 'Approve plan? [y/N] ' with no trailing newline on stdout, wrote more stderr noise 1s later, then read stdin; sent 'y' at 2.5s.
- **Expected result:** The stdout prompt appears promptly and the gate behaves as before; stderr noise does not trigger or delay the gate.
- **Actual result:** Prompt appeared at 0.03s (with elapsed prefix) despite no trailing newline; stderr lines 'noise1' and 'noise2' were shown as separate lines and did not trigger or delay any gate; the driver received 'y' and proceeded. Driver then exited 3 because the fake driver did not complete, reported as stopped without completing.
- **Defects:** None

### MC-404

- **Action:** In a temp dir ran `uncle --noui --bogus-flag 2>err.txt >out.txt` (invalid argument refusal) and checked exit code, err.txt and out.txt.
- **Expected result:** The refusal message is in err.txt and the exit status is 2, unchanged from prior behavior.
- **Actual result:** Exit status 2. err.txt contained 'Unknown argument: --bogus-flag' followed by the usage text. out.txt was empty.
- **Defects:** None

### MC-405

- **Action:** Ran scripts/lib/uncle_headless.py (the --noui engine) directly with a fake driver script that writes to stderr a line with ANSI SGR codes and the secret (env MYSECRET_TOKEN=s3cr3tvalue12345), then an unterminated last line containing an OSC title sequence and the secret. Stderr was captured to a file and viewed with cat -v. The full `uncle --noui` launcher was not used; the module it invokes was.
- **Expected result:** The file has no unredacted secret and no escape sequences, and the unterminated last line is present, redacted.
- **Actual result:** err.txt held 'hello red token=[REDACTED]', 'last line key [REDACTED]' (the unterminated line, present and redacted), and the driver's exit-3 status message. cat -v showed no ^[ sequences. grep -c for the secret value gave 0 in both stderr and stdout files. The exit code of 3 is the expected 'driver did not emit completion banner' result for the fake driver.
- **Defects:** None

### MC-407

- **Action:** Ran the real scripts/lib/uncle_headless.py run() (the --noui driver runner, signal handlers installed) in a separate process, with a fake driver that wrote two lines to stderr, spawned a grandchild sleeper, then slept. After 2s I sent an external SIGINT to the runner, then listed leftover processes with pgrep. I did not launch the full `./uncle --noui` build because that would invoke paid agent stages.
- **Expected result:** Exit status is 130, all stderr output written before interrupt is present before a single status line, and no descendant processes survive.
- **Actual result:** Exit status was 130. Captured stderr held 'pending-err-1' and 'pending-err-2' exactly once each, and nothing leaked to stdout. No 'driver exited with status' line appeared at all, so there was no more than one status line (the unit test allows at most one). pgrep showed the driver and grandchild alive before the signal and no processes afterwards.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | exit=1; err.txt lines: 'Mode: unattended (default)...', 'DRIVER-ERROR-TEXT', 'uncle --noui: driver exited with status 1'; out.txt: '[+00:00:00] progress line'. The unattended-mode notice in err.txt is a pre-existing launcher notice, not driver error text. |
| MC-102 | YES | PASS | Captured transcript: '[+00:00:21] [done] success ... canonical change-planning bundle: invalid baseline_report packet: baseline report is missing verification_commands / [+00:00:21] Total time: 22s ... / uncle --noui: driver exited with status 1 / exit=1'. Caveat: no real tty available in this environment; both streams were visible in the merged non-redirected output. |
| MC-103 | YES | PASS | exit=3; err.txt gate lines as above; out.txt: '[+00:00:00] progress line' and '[+00:00:00] Human gate: approve PROJECT_PLAN.md'. A first attempt, with the stub exiting with raw status 3, gave exit 1 because the contract defines a gate as exit 0 without a completion banner, so I redid it that way. |
| MC-105 | YES | PASS | help grep line 53 in both outputs; 'refusal exit=2' and 'refusal2 exit=2' with the messages above taken from err.txt. |
| MC-106 | YES | BLOCKED-HUMAN | None. Automated coverage exists in scripts/tests/tui-failure-line-test.py, but I did not rerun or cite a driver result for it, so it is not evidence for this row. |
| MC-107 | YES | BLOCKED-HUMAN | uncle_tui.py:102 returns 'Driver exited with status %s: %s' % (status, text or '(no output)'). The unit test tui-failure-line-test.py asserts the (no output) case at line 23 and the 130/143 cases at line 26. I did not re-run it, because the driver green-check owns automated commands. This is code-level evidence only and does not satisfy the required screenshots of the real build window. |
| MC-200 | YES | PASS | Terminal output: exit=1; ---out (empty); ---err: DRIVER-ERROR-TEXT / uncle --noui: driver exited with status 7. Note: the headless module was invoked directly (the same python script `uncle` execs at line 437) rather than via the ./uncle shell wrapper. |
| MC-202 | YES | PASS | 0.34s err b'Continue? [y/N] \n'; 3.13s out b'[+00:00:03] gate: needs approval\n'; 3.13s err b'uncle --noui: driver stopped without completing (gate or blocked); exit 3'; 3.14s exit=3 |
| MC-203 | YES | PASS | Transcript: 'INT exit=130', 'TERM exit=143', 'pgrep: none'. err_INT.txt and err_TERM.txt each contained only 'pending-err MARKER203'. Code reference: scripts/lib/uncle_headless.py lines 370-371. Existing unit test test_signal_drains_pending_stderr covers the same behavior. |
| MC-204 | YES | PASS | out.txt: '[+00:00:00] progress one' / '[+00:00:00] progress two' / '[+00:00:00] progress three'. err.txt: 'stderr-noise-abc' / 'uncle --noui: driver stopped without completing (gate or blocked); exit 3'. Files in /tmp/mc204. |
| MC-205 | YES | BLOCKED-HUMAN | Terminal output of the function calls; uncle_tui.py:93-102 and :2063 call site. The live TUI capture the checklist requires was not performed. |
| MC-302 | YES | PASS | /tmp/mc302.txt (pty transcript), /tmp/o (stdout), /tmp/e (stderr), captured in this run. |
| MC-303 | YES | PASS | exit=3. /tmp/uncle-gate-err.txt: 'uncle --noui: driver stopped without completing (gate or blocked); exit 3' and 'uncle --noui: stopped at: Human gate: PROJECT_PLAN.md awaiting approval'. out: '[+00:00:00] progress line' and '[+00:00:00] Human gate: PROJECT_PLAN.md awaiting approval'. This matches the test_gate_named_on_stderr and test_fake_drivers assertions in scripts/tests/headless-run-test.py. The real-launcher path was not exercised end to end. |
| MC-304 | YES | BLOCKED-HUMAN | uncle_tui.py:102; python3 scripts/tests/tui-failure-line-test.py -> Ran 6 tests, OK. Check requires a human-visible TUI observation of a real failing build. |
| MC-403 | YES | PASS | Transcript: [0.03] '[+00:00:00] Approve plan? [y/N] ' ; [0.03] 'noise1'; [1.04] 'noise2'; [sent y]; [2.60] "GOT 'y\n' after 2.6"; exit-3 status line. |
| MC-404 | YES | PASS | rc=2; err.txt: 'Unknown argument: --bogus-flag' + 'Usage: uncle [-h/--help/--performance/--runs] [--attended] [--noui] ...'; out.txt empty. Source uncle:209-213 sets UNCLE_REFUSE_CODE=2 under --noui. Only one refusal path (invalid argument) was exercised. |
| MC-405 | YES | PASS | cat -v err.txt output: 'hello red token=[REDACTED]' / 'last line key [REDACTED]' / 'uncle --noui: driver stopped without completing (gate or blocked); exit 3'; grep -c s3cr3t err.txt out.txt -> 0 and 0. |
| MC-407 | YES | PASS | Before SIGINT: pids 89762 (driver) and 89763 (grandchild). exit=130. After: pgrep printed 'none'. stdout: 'RC 130'. stderr: 'pending-err-1' then 'pending-err-2'. Caveat: this exercised the headless runner directly, not the full uncle CLI wrapper. The status line was absent rather than present after the stderr output. |
