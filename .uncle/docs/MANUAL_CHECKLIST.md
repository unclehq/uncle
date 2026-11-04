# Manual checklist

### MC-103
- Exclusive resources: none
- Depends on: none
- Exact action: In a real interactive terminal, run `uncle --application` and `uncle --housekeeping` with no value and no piped stdin, timing each.
- Expected result: Each exits non-zero immediately without waiting for input, with a message naming the option, both forms (TEXT or piped stdin), and the substring `empty input`.
- Evidence to capture: Terminal transcript with messages and exit codes.
- Actual result: 
- Status: NOT RUN

### MC-104
- Exclusive resources: none
- Depends on: none
- Exact action: Pipe invalid stdin into `uncle --application`: a NUL byte, invalid UTF-8 bytes, whitespace only, and 1048577 bytes; check the system temp directory for leftovers after each.
- Expected result: Each is refused with an error naming the reason, exit non-zero, nothing starts, and no temp files remain.
- Evidence to capture: Error messages, exit codes, and temp directory listing before and after.
- Actual result: 
- Status: NOT RUN

### MC-108
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application --housekeeping < brief.md` and `uncle --issue 1 --application < brief.md`, and confirm `uncle --change-request < request.md` in a fresh scratch project still works.
- Expected result: The mixed options exit 1 with the mutually exclusive error before reading stdin; `--change-request` behaves as before, writing CHANGE_REQUEST.md and starting the change workflow.
- Evidence to capture: Terminal output and exit codes for each run.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal (stdin is a TTY), run `uncle --application` and then `uncle --housekeeping` with no value, under a 10-second timeout.
- Expected result: Each exits non-zero promptly without waiting for input, with a message naming the option and both forms (text or piped stdin) and containing `empty input`.
- Evidence to capture: Terminal transcript with exit codes and elapsed time for both commands.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In an empty scratch directory, run `printf 'line one\n\nline three\n' | uncle --application --unattended` and `uncle --unattended --application < brief.md`, then repeat both for `--housekeeping`.
- Expected result: Each starts the matching workflow (application build or housekeeping) using the piped text, with --unattended applied and --unattended never used as the text.
- Evidence to capture: Screenshot or transcript of the TUI showing the startup text and unattended mode for each of the four runs.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Pipe oversized (1048577 bytes), NUL-containing, invalid UTF-8 and whitespace-only input into `uncle --application` and `uncle --housekeeping`, then check the temp directory for leftover files.
- Expected result: Every case exits 1 with an `Error: --OPT ...` message naming the cause, nothing starts, and no temp files are left behind.
- Evidence to capture: Transcript with the error text and exit code for each case, plus a temp-directory listing before and after.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application=--my-brief < /dev/null` for both options and `uncle --application "-h"`. Pipe `printf 'x\r\n'` and `printf 'x\n\n'` into the launcher with the TUI observing the received text.
- Expected result: `--OPT=--my-brief` delivers `--my-brief` as the text. `-h` is taken as a value, not as help. CRLF input yields `x`, and double-newline input yields `x` followed by a single newline.
- Evidence to capture: Transcript or TUI screenshot showing the exact text received in each case.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --help`, then run `uncle --change-request < request.md` in a scratch project, and again with an existing CHANGE_REQUEST.md.
- Expected result: The help text documents the stdin form, the value-wins rule and `--OPT=VALUE`. `--change-request` behaves as before: it starts normally, and it refuses to overwrite an existing CHANGE_REQUEST.md.
- Evidence to capture: Help output excerpt and transcripts of both change-request runs.
- Actual result: 
- Status: NOT RUN

## resources

### MC-304
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application=--my-text < /dev/null`, `uncle --application --bogus < brief.md`, and `uncle --application ""` with piped input.
- Expected result: `--application=--my-text` starts with text `--my-text`; `--bogus` exits 1 with `Unknown argument` without reading stdin; the empty value is refused with `text cannot be empty` and the pipe is left unread.
- Evidence to capture: Output and exit codes for each run, plus proof the pipe data remained unread.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-402
- Required for acceptance: YES
- Exclusive resources: file:scratch-project/CHANGE_REQUEST.md
- Depends on: none
- Exact action: Run `echo 'request text' | uncle --change-request` in a scratch project with no CHANGE_REQUEST.md, then repeat on a terminal with no pipe, and again with an existing CHANGE_REQUEST.md.
- Expected result: The first run writes CHANGE_REQUEST.md and starts the change workflow. The terminal run is refused immediately with the existing stdin message. The third run refuses to overwrite and names CHANGE_REQUEST.md.
- Evidence to capture: Terminal output and exit codes for the three runs.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping "tidy branches"` (value form), then `uncle --housekeeping` on a real terminal with no pipe, and observe both.
- Expected result: The value form proceeds to housekeeping planning with that text. The bare terminal form exits non-zero at once, never waits for input, and the message contains `empty input`.
- Evidence to capture: Terminal output, exit codes, and a note that the bare run returned promptly.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application x --housekeeping y`, `uncle --issue 1 --application x`, and `uncle --change-request --housekeeping` (stdin piped), and observe each.
- Expected result: Each exits 1 with the mutually-exclusive error, starts nothing, and leaves no temp files.
- Evidence to capture: Stderr and exit code for each command.
- Actual result: 
- Status: NOT RUN
