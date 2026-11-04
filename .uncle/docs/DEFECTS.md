# Defects

## None. Setup needed: run the --change-request check in a real interactive terminal (a TTY) against the worktree build, then confirm CHANGE_REQUEST.md is written and the change workflow starts.

- **Status:** BLOCKED-SETUP
- **Evidence:** Terminal output: exit=1 for both mixed-option runs with the mutual-exclusion error. The --change-request run printed a curses traceback (cbreak() returned ERR) and 'Error: TUI failed to start with startup action'. The Python traceback paths point to /opt/homebrew/opt/uncle/libexec/uncle_tui.py. The scratch project is under /tmp/scratch*. The background task id is bpc5r2syf.
- **Expected result:** The mixed options exit 1 with the mutually exclusive error before reading stdin. `--change-request` behaves as before, writing CHANGE_REQUEST.md and starting the change workflow.
- **Actual result:** Part 1 passed. Both mixed-option runs printed 'Error: --application, --issue, --change-request and --housekeeping are mutually exclusive' and exited 1. Part 2 could not be observed. The change-request run reached the curses TUI, which failed with 'cbreak() returned ERR' because this worker has no TTY. It printed 'Error: TUI failed to start with startup action', and the wrapping command then hung and was backgrounded. I did not confirm that CHANGE_REQUEST.md was written or that the change workflow started. My cleanup command was denied by the permission classifier. The scratch-project check also appeared to run the Homebrew-installed libexec/uncle_tui.py (/opt/homebrew/opt/uncle), not the worktree copy.

## None. The check is only partly executed: the end-to-end start was not run, and the help text has no explicit value-wins statement, which a human should judge.

- **Status:** NOT RUN
- **Evidence:** Help lines 4, 22-36 of `./uncle --help`. Helper rc=0 and rc=1 transcripts with the file content still 'exists'. Code in uncle lines 183-199 reads stdin through the helper and then sets the change_request startup action.
- **Expected result:** Help documents the stdin form, the value-wins rule and --OPT=VALUE. --change-request starts normally and refuses to overwrite an existing CHANGE_REQUEST.md.
- **Actual result:** Help documents the stdin form: `uncle --change-request [--unattended] < request.md`, with a paragraph on stdin limits. It documents --OPT=TEXT: 'text beginning with -- must use the --OPT=TEXT form'. The value-wins rule is only implied by '(or piped stdin when TEXT is omitted)'. No sentence says an explicit value wins over stdin. With the helper, piped stdin was accepted (rc=0) and a temp dir path was returned. With an existing CHANGE_REQUEST.md the helper exited rc=1 with 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.', and the file was unchanged. The end-to-end `uncle --change-request` start was not observed.

## None. Setup action: run `echo 'request text' | uncle --change-request` in a scratch project from a real interactive terminal (TUI needs a tty) and confirm CHANGE_REQUEST.md is written and the workflow starts.

- **Status:** BLOCKED-SETUP
- **Evidence:** Run 1 output: _curses.error: cbreak() returned ERR from uncle_tui.py; ls showed no CHANGE_REQUEST.md. Run 2 and 3 messages as quoted above. Under `script`, stdin became the pty so the pipe was lost, which gave the run-2 message instead of exercising run 1. A real terminal is needed for run 1.
- **Expected result:** Run 1 writes CHANGE_REQUEST.md and starts the change workflow. Run 2 is refused immediately with the existing stdin message. Run 3 refuses to overwrite and names CHANGE_REQUEST.md.
- **Actual result:** Run 2 PASS: printed 'Error: --change-request reads the change request from stdin; pipe or redirect it in'. Run 3 PASS: printed 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.' and the file still contained 'x'. Run 1 NOT confirmed: the stdin validator accepted the text (exit 0, wrote a private temp file), but the TUI that writes CHANGE_REQUEST.md and starts the workflow crashed with curses cbreak() ERR because this worker has no interactive terminal. No CHANGE_REQUEST.md was created and the workflow was not observed to start.
