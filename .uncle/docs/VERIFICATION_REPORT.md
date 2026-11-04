# Verification report

## Findings

### MC-103

- **Action:** Ran ./uncle --application and ./uncle --housekeeping with no value, with stdin attached to a pseudo-terminal that never supplied input (python pty, 10s timeout) and also under `script` (pty). Timed each. Note: a pty harness, not a human-operated terminal.
- **Expected result:** Each exits non-zero immediately without waiting for input, with a message naming the option, both forms (TEXT or piped stdin), and the substring `empty input`.
- **Actual result:** Both exited with code 1 in about 0.01s without blocking. Messages: 'Error: --application requires TEXT or piped stdin (empty input)' and 'Error: --housekeeping requires TEXT or piped stdin (empty input)'.
- **Defects:** None

### MC-104

- **Action:** Piped four invalid stdins (NUL byte, invalid UTF-8 bytes, whitespace only, 1048577 bytes of 'a') into ./uncle --application from the worktree, each with a fresh empty private TMPDIR, and listed TMPDIR after each run. The first attempt used the ambient UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec, which runs an older installed helper; the final run set UNCLE_RUNTIME_ROOT to the worktree so the code under test ran.
- **Expected result:** Each input is refused with an error naming the reason, exit non-zero, nothing starts, and no temp files remain.
- **Actual result:** With the worktree runtime: NUL gave 'Error: --application input contains NUL or control characters', invalid UTF-8 gave 'Error: --application input is not valid UTF-8', whitespace-only gave 'Error: --application text cannot be empty', and 1048577 bytes gave 'Error: --application input exceeds 1048576 bytes'. All four exited 1 and TMPDIR held 0 entries after each. In the first attempt, which used the installed older helper, all four gave only a generic usage error, exit 1, and 0 temp files; that is an environment mismatch, not a defect in the worktree code.
- **Defects:** None

### MC-108

- **Action:** Ran `./uncle --application --housekeeping < brief.md` and `./uncle --issue 1 --application < brief.md`. Then ran `uncle --change-request < request.md` in a fresh scratch git project with no TTY, under a 20s timeout.
- **Expected result:** The mixed options exit 1 with the mutually exclusive error before reading stdin. `--change-request` behaves as before, writing CHANGE_REQUEST.md and starting the change workflow.
- **Actual result:** Part 1 passed. Both mixed-option runs printed 'Error: --application, --issue, --change-request and --housekeeping are mutually exclusive' and exited 1. Part 2 could not be observed. The change-request run reached the curses TUI, which failed with 'cbreak() returned ERR' because this worker has no TTY. It printed 'Error: TUI failed to start with startup action', and the wrapping command then hung and was backgrounded. I did not confirm that CHANGE_REQUEST.md was written or that the change workflow started. My cleanup command was denied by the permission classifier. The scratch-project check also appeared to run the Homebrew-installed libexec/uncle_tui.py (/opt/homebrew/opt/uncle), not the worktree copy.
- **Defects:** None. Setup needed: run the --change-request check in a real interactive terminal (a TTY) against the worktree build, then confirm CHANGE_REQUEST.md is written and the change workflow starts.

### MC-200

- **Action:** Ran ./uncle --application and ./uncle --housekeeping (no value) under a pty (stdin is a TTY) with a 10s timeout.
- **Expected result:** Each exits non-zero promptly without waiting, with message naming the option and both forms and containing 'empty input'.
- **Actual result:** Both exited 1 within ~0s. Messages: 'Error: --application requires TEXT or piped stdin (empty input)' and 'Error: --housekeeping requires TEXT or piped stdin (empty input)'.
- **Defects:** None

### MC-201

- **Action:** Ran the real ./uncle launcher in a scratch git dir with UNCLE_RUNTIME_ROOT unset. A stand-in python3 replaced uncle_tui.py, so no real build or housekeeping workflow ran and no real TUI was shown. The stand-in printed UNCLE_STARTUP_ACTION, UNCLE_UNATTENDED and the startup text file. Ran four invocations: `printf 'line one\n\nline three\n' | uncle X --unattended` and `uncle --unattended X < brief.md`, for X = --application and --housekeeping. Also ran scripts/tests/launcher-stdin-text-test.sh.
- **Expected result:** Each run starts the matching workflow with the piped text, --unattended applied, and --unattended never used as the text.
- **Actual result:** All four runs gave the expected result. --application gave action=create_app and --housekeeping gave action=housekeeping. All four had unattended=1. The startup text file held the piped text exactly: 'line one', blank line, 'line three' for the printf runs, and 'brief text', blank line, 'more' for the brief.md runs. The text never contained '--unattended'. launcher-stdin-text-test.sh printed 'all launcher stdin text checks passed'. Two observations: (1) The first attempt failed because the ambient env var UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec made the launcher use an older installed helper, which printed an old usage error. This is an environment artifact, not a defect in this change. (2) Not verified: a real interactive TUI screenshot, since the real TUI would launch a costly agent workflow.
- **Defects:** None

### MC-202

- **Action:** In a scratch dir with a private TMPDIR, piped oversized (1048577 bytes), NUL-containing, invalid UTF-8 and whitespace-only input into the worktree's `uncle --application` and `uncle --housekeeping` (UNCLE_RUNTIME_ROOT set to the worktree, because the ambient value pointed at the older Homebrew install), then listed the private TMPDIR. An earlier run through the ambient Homebrew runtime hit its stale helper and printed a usage error; that run is not counted.
- **Expected result:** Every case exits 1 with an `Error: --OPT ...` message naming the cause, nothing starts, and no temp files are left behind.
- **Actual result:** All 8 cases exited 1. Messages: `Error: --OPT input exceeds 1048576 bytes`, `Error: --OPT input contains NUL or control characters`, `Error: --OPT input is not valid UTF-8`, `Error: --OPT text cannot be empty`, for both --application and --housekeeping. No workflow started. The private TMPDIR was empty afterwards.
- **Defects:** None

### MC-205

- **Action:** Ran the worktree launcher (bash uncle, UNCLE_RUNTIME_ROOT overridden to the worktree because the shell env pointed at /opt/homebrew/opt/uncle/libexec) with a stub python3 that prints the TUI env contract. For both --application and --housekeeping I ran: `--OPT=--my-brief < /dev/null`, `--OPT "-h" < /dev/null`, `printf 'x\r\n' |` and `printf 'x\n\n' |`. I also ran scripts/tests/launcher-stdin-text-test.sh narrowly. The real TUI was not observed, because a stub stood in for it.
- **Expected result:** `--OPT=--my-brief` delivers `--my-brief` as the text. `-h` is taken as a value, not as help. CRLF input yields `x`, and double-newline input yields `x` followed by a single newline.
- **Actual result:** For both options, `--OPT=--my-brief` gave text=[--my-brief] and `-h` gave text=[-h]. Both exited 0 and showed no help. `x\r\n` gave file content `x`. `x\n\n` gave `x\n`. The action was create_app for --application and housekeeping for --housekeeping. The launcher stdin test script printed 'all launcher stdin text checks passed'.
- **Defects:** None

### MC-206

- **Action:** Ran `./uncle --help` and read the text. Ran scripts/lib/change_request_stdin.py (the helper `uncle --change-request` calls) directly in a scratch dir with piped stdin, then again after creating CHANGE_REQUEST.md there. I did not launch the full `uncle --change-request` change workflow, because that would start agent runs.
- **Expected result:** Help documents the stdin form, the value-wins rule and --OPT=VALUE. --change-request starts normally and refuses to overwrite an existing CHANGE_REQUEST.md.
- **Actual result:** Help documents the stdin form: `uncle --change-request [--unattended] < request.md`, with a paragraph on stdin limits. It documents --OPT=TEXT: 'text beginning with -- must use the --OPT=TEXT form'. The value-wins rule is only implied by '(or piped stdin when TEXT is omitted)'. No sentence says an explicit value wins over stdin. With the helper, piped stdin was accepted (rc=0) and a temp dir path was returned. With an existing CHANGE_REQUEST.md the helper exited rc=1 with 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.', and the file was unchanged. The end-to-end `uncle --change-request` start was not observed.
- **Defects:** None. The check is only partly executed: the end-to-end start was not run, and the help text has no explicit value-wins statement, which a human should judge.

### MC-304

- **Action:** Ran ./uncle --application --bogus and ./uncle --application "" with piped input (a brief file), then repeated each followed by `cat` to see whether the pipe was left unread. For --application=--my-text, ran the real launcher with </dev/null (no tty, so the TUI crashed in curses cbreak after argument parsing), and separately sourced the parse_text_option function from ./uncle to read the parsed text.
- **Expected result:** --application=--my-text starts with text `--my-text`; --bogus exits 1 with `Unknown argument` without reading stdin; empty value refused with `text cannot be empty` and the pipe left unread.
- **Actual result:** --bogus: printed `Unknown argument: --bogus`, exit 1, and stdin was left intact (`cat` afterwards printed `hello`). Empty value: printed `Error: --application text cannot be empty`, exit 1, pipe unread (`cat` printed `hello`). --application=--my-text: the launcher got past argument parsing and started the TUI. The TUI itself failed only because there was no tty. parse_text_option set UNCLE_STARTUP_TEXT=[--my-text], shift=1, no pending stdin. The real launcher resolved to the Homebrew-installed uncle_tui.py, not the worktree copy. The text reaching the TUI was therefore not observed end to end.
- **Defects:** None

### MC-402

- **Action:** In a scratch git project (/tmp/mc402.Uun0) ran: (1) `echo 'request text' | uncle --change-request` with no CHANGE_REQUEST.md; (2) `uncle --change-request` on a pty with stdin a terminal; (3) `echo other | uncle --change-request` with an existing CHANGE_REQUEST.md containing 'x'. Also ran scripts/lib/change_request_stdin.py directly with piped text.
- **Expected result:** Run 1 writes CHANGE_REQUEST.md and starts the change workflow. Run 2 is refused immediately with the existing stdin message. Run 3 refuses to overwrite and names CHANGE_REQUEST.md.
- **Actual result:** Run 2 PASS: printed 'Error: --change-request reads the change request from stdin; pipe or redirect it in'. Run 3 PASS: printed 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.' and the file still contained 'x'. Run 1 NOT confirmed: the stdin validator accepted the text (exit 0, wrote a private temp file), but the TUI that writes CHANGE_REQUEST.md and starts the workflow crashed with curses cbreak() ERR because this worker has no interactive terminal. No CHANGE_REQUEST.md was created and the workflow was not observed to start.
- **Defects:** None. Setup action: run `echo 'request text' | uncle --change-request` in a scratch project from a real interactive terminal (TUI needs a tty) and confirm CHANGE_REQUEST.md is written and the workflow starts.

### MC-403

- **Action:** Ran `./uncle --housekeeping "tidy branches"` under a pty (script) with stdin at /dev/null and captured the output for 15s; then ran `./uncle --housekeeping` on a real pty (python pty.fork, so stdin is a terminal, no pipe) and observed output, elapsed time and exit status.
- **Expected result:** Value form proceeds to housekeeping planning with that text. Bare terminal form exits non-zero at once, never waits for input, and the message contains `empty input`.
- **Actual result:** Value form launched the Uncle TUI (supervisor and stage panes, input prompt), i.e. it proceeded past argument parsing into the build/planning UI; the output did not show the text 'tidy branches' itself, so the text hand-off was not directly observed. Bare pty form printed 'Error: --housekeeping requires TEXT or piped stdin (empty input)', exited with status 1 after 0.01s with no wait for input.
- **Defects:** None

### MC-404

- **Action:** Ran ./uncle with `--application x --housekeeping y`, `--issue 1 --application x`, and (stdin piped) `--change-request --housekeeping`, each in an empty temp working dir with an empty TMPDIR, and observed output, exit code, and leftover files.
- **Expected result:** Each exits 1 with the mutually-exclusive error, starts nothing, and leaves no temp files.
- **Actual result:** All three exited 1 with 'Error: --application, --issue, --change-request and --housekeeping are mutually exclusive'. Nothing started. The temp TMPDIR and the working dir were both empty afterward.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-103 | YES | PASS | pty run: '--application 1 0.01 Error: --application requires TEXT or piped stdin (empty input)'; '--housekeeping 1 0.01 Error: --housekeeping requires TEXT or piped stdin (empty input)'. script run: exit=1, 0.00s total for each. |
| MC-104 | YES | PASS | Terminal output and exit codes (rc=1) captured per case; temp dir entry count 0 after each case. Worktree helper scripts/lib/housekeeping_input.py supports --label and the messages above. |
| MC-108 | YES | BLOCKED-SETUP | Terminal output: exit=1 for both mixed-option runs with the mutual-exclusion error. The --change-request run printed a curses traceback (cbreak() returned ERR) and 'Error: TUI failed to start with startup action'. The Python traceback paths point to /opt/homebrew/opt/uncle/libexec/uncle_tui.py. The scratch project is under /tmp/scratch*. The background task id is bpc5r2syf. |
| MC-200 | YES | PASS | pty transcript: exit 1, elapsed 0s for each command; no timeout hit. |
| MC-201 | YES | PASS | Stand-in transcript: '== --application A: action=create_app unattended=1 / line one$ / $ / line three'; '== --application B: ... brief text$ / $ / more'; '== --housekeeping A: action=housekeeping unattended=1 ...'; '== --housekeeping B: action=housekeeping unattended=1 ...'. Test script output: 'all launcher stdin text checks passed'. |
| MC-202 | YES | PASS | Terminal transcript from the run. Exit code 1 for each of the 8 cases, and `ls -A $TMPDIR` printed nothing. Note: the ambient UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec is a stale install, so running the worktree launcher without overriding it uses the old helper. |
| MC-205 | YES | PASS | The stub transcript showed text=[--my-brief] action=create_app, text=[-h], file od output `x` and `x \n`, and the same for housekeeping, all with rc=0. Note: with the ambient UNCLE_RUNTIME_ROOT pointing at the older Homebrew install, the launcher printed an old-usage error from housekeeping_input.py and the test script failed. That is an environment mismatch, not a worktree defect, and it disappeared once the root was set to the worktree. |
| MC-206 | YES | NOT RUN | Help lines 4, 22-36 of `./uncle --help`. Helper rc=0 and rc=1 transcripts with the file content still 'exists'. Code in uncle lines 183-199 reads stdin through the helper and then sets the change_request startup action. |
| MC-304 | YES | PASS | Terminal outputs above. The launcher's `Unknown argument` and `cannot be empty` messages were observed directly. The `--my-text` parse result came from the extracted function (uncle lines 127-155). |
| MC-402 | YES | BLOCKED-SETUP | Run 1 output: _curses.error: cbreak() returned ERR from uncle_tui.py; ls showed no CHANGE_REQUEST.md. Run 2 and 3 messages as quoted above. Under `script`, stdin became the pty so the pipe was lost, which gave the run-2 message instead of exercising run 1. A real terminal is needed for run 1. |
| MC-403 | YES | PASS | Bare: stdout 'Error: --housekeeping requires TEXT or piped stdin (empty input)', elapsed 0.01, exit code 1. Value: TUI escape-sequence screen with the stage panes rendered, no error message. Source: uncle read_stdin_option checks [[ -t 0 ]] and exits 1 with that message. |
| MC-404 | YES | PASS | Exit codes 1/1/1; identical error message on each; `ls -A` of TMPDIR and cwd printed nothing. A first attempt in zsh passed the flags as one unsplit argument and hit 'Unknown argument'. That was a mistake in my invocation, not an app defect, and I reran with proper argument splitting. |
