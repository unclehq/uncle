# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: file:err.txt, file:out.txt
- Depends on: none
- Exact action: Run `uncle --noui` with a request that makes the driver fail, redirecting with `2>err.txt >out.txt`, then view both files.
- Expected result: err.txt contains the driver's error text exactly once, followed by one `driver exited with status N` line. out.txt contains neither. The process exit status is 1.
- Evidence to capture: Contents of err.txt and out.txt plus the printed exit status.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` interactively in a terminal with a failing request, with no redirection.
- Expected result: The driver's error text and the exit status line are visible on the terminal. Stdout lines still carry the `[+hh:mm:ss]` prefix.
- Evidence to capture: Terminal transcript or screenshot of the run.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:err.txt
- Depends on: none
- Exact action: Run `uncle --noui` with a request that stops at a gate, capturing `2>err.txt`, and note the exit status.
- Expected result: Exit status is 3. The gate message appears on stderr as before. Stdout formatting is unchanged.
- Evidence to capture: Exit status and contents of err.txt and stdout.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:err.txt
- Depends on: none
- Exact action: Run `uncle --help` and `uncle --noui --help`. Then run `uncle --noui` with an invalid or refused invocation and capture `2>err.txt`.
- Expected result: Help text states that errors go to stderr. The launcher refusal appears in err.txt with exit status 2, unchanged.
- Evidence to capture: Help output, err.txt contents and exit status.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, start a run that makes the driver fail with a non-zero exit, and watch the build window.
- Expected result: The build window shows driver errors as before, followed by one line `Driver exited with status N: <last non-empty output line>`, with secrets and escape codes removed.
- Evidence to capture: Screenshot or screen text of the build window.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, run one driver that exits 0 and one that exits non-zero while printing nothing, or stop a run with Ctrl-C so it exits 130 or 143.
- Expected result: Exit 0 adds no failure line. The silent failure shows `Driver exited with status N: (no output)`. The user stop shows the failure line with 130 or 143.
- Evidence to capture: Screenshots of the build window for each case.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` against a disposable project with a request that makes the driver fail, redirecting with `1>out.txt 2>err.txt`. Then run `cat out.txt err.txt`.
- Expected result: err.txt holds the driver's error text exactly once, followed once by the status line `driver exited with status N`. The shell exit status is 1. out.txt holds neither the error text nor the status line.
- Evidence to capture: Contents of out.txt and err.txt, plus the exit status.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` against a disposable project whose driver writes a stderr prompt with no trailing newline and then waits. Watch the terminal live, then let the run finish.
- Expected result: The prompt text appears on the terminal within the idle timeout, before the driver exits. A normal gate still stops the run with exit status 3 and its message naming the gate.
- Evidence to capture: Timestamped terminal observation and the exit status.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` against a disposable project, interrupt it with Ctrl-C while the driver has stderr output pending, and run it again with the same setup but send SIGTERM instead. Capture stderr to a file each time.
- Expected result: Exit status is 130 for Ctrl-C and 143 for SIGTERM. All driver stderr text precedes the single status line, and no driver process is left running (`pgrep` finds none).
- Evidence to capture: stderr files, exit statuses, and the `pgrep` output.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` against a disposable project where the driver prints a normal progress line to stdout and also writes to stderr, capturing `1>out.txt 2>err.txt`. Then check the stdout line format.
- Expected result: Each stdout line in out.txt has a single `[+hh:mm:ss]` prefix, as before. Stderr text is not duplicated onto stdout.
- Evidence to capture: Contents of out.txt and err.txt.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start the TUI against a disposable project whose driver prints a line and then exits with a non-zero status. Watch the build window. Repeat with a driver that exits 0.
- Expected result: For the non-zero exit the build window ends with `Driver exited with status N: <last non-empty output line>`, or `(no output)` if the driver printed nothing, with any secret redacted and no escape sequences. For exit 0 no failure line appears.
- Evidence to capture: Screenshot or terminal capture of the build window in both cases.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` interactively in a terminal with a failing request (no redirection) and watch the display.
- Expected result: The error text is visible in the terminal, stdout lines keep the `[+hh:mm:ss]` prefix, and stderr error lines are shown verbatim without that prefix.
- Evidence to capture: Terminal transcript or screenshot.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:/tmp/uncle-gate-err.txt
- Depends on: none
- Exact action: Run `uncle --noui` against a driver run that stops at an approval gate, with `2>/tmp/uncle-gate-err.txt`, and check the exit status.
- Expected result: Exit status is 3, the gate is named on stderr, and gate behavior and stdout format are unchanged from before.
- Evidence to capture: Exit status, stderr file, stdout excerpt.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In the TUI, start a build whose driver fails with a non-zero exit, and observe the build window after it ends.
- Expected result: The build window ends with a line `Driver exited with status N: <last non-empty output line>` with secrets redacted and no escape sequences; a successful run adds no such line.
- Evidence to capture: Screenshot or captured build-window text of the failure line.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `--noui` against a driver that prints an attended prompt without a trailing newline on stdout while also writing stderr noise, observing the terminal live.
- Expected result: The stdout prompt appears promptly and the gate behaves as before; stderr noise does not trigger or delay the gate.
- Evidence to capture: Terminal transcript showing prompt timing and gate outcome.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Invoke the launcher refusals under `--noui` (for example with a missing or invalid argument) with `2>err.txt`.
- Expected result: The refusal message is in err.txt and the exit status is 2, unchanged from prior behavior.
- Evidence to capture: Exit code and err.txt contents.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `--noui` with a driver that emits a secret, ANSI escape codes, and an unterminated last line on stderr; capture stderr to a file.
- Expected result: The file has no unredacted secret and no escape sequences, and the unterminated last line is present, redacted.
- Evidence to capture: Contents of the stderr file (hex or cat -v view).
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a `--noui` run and interrupt it with Ctrl-C (SIGINT) while the driver is writing to stderr; afterwards check for leftover driver processes.
- Expected result: Exit status is 130, all stderr output written before interrupt is present before a single status line, and no descendant processes survive.
- Evidence to capture: Exit code, stderr contents, process listing after exit.
- Actual result: 
- Status: NOT RUN
