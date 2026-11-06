# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. Automated coverage exists in scripts/tests/tui-failure-line-test.py, but I did not rerun or cite a driver result for it, so it is not evidence for this row.
- **Expected result:** The build window shows driver errors as before, followed by one line `Driver exited with status N: <last non-empty output line>`, with secrets and escape codes removed.
- **Actual result:** Not observed. The live TUI observation was not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** uncle_tui.py:102 returns 'Driver exited with status %s: %s' % (status, text or '(no output)'). The unit test tui-failure-line-test.py asserts the (no output) case at line 23 and the 130/143 cases at line 26. I did not re-run it, because the driver green-check owns automated commands. This is code-level evidence only and does not satisfy the required screenshots of the real build window.
- **Expected result:** Exit 0 adds no failure line. A silent non-zero exit shows `Driver exited with status N: (no output)`. A user stop shows the failure line with 130 or 143.
- **Actual result:** Not observed live. A worker without an interactive terminal cannot run a driver in the curses TUI, press Ctrl-C, or take screenshots of the build window.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Terminal output of the function calls; uncle_tui.py:93-102 and :2063 call site. The live TUI capture the checklist requires was not performed.
- **Expected result:** Non-zero exit: build window ends with 'Driver exited with status N: <last line>' or '(no output)', redacted, no escapes. Exit 0: no failure line.
- **Actual result:** Function output matched: 'Driver exited with status 3: last'; 'Driver exited with status 4: (no output)'; None for status 0; 'Driver exited with status 1: token=[REDACTED]' with escapes stripped. The live build-window rendering was not observed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** uncle_tui.py:102; python3 scripts/tests/tui-failure-line-test.py -> Ran 6 tests, OK. Check requires a human-visible TUI observation of a real failing build.
- **Expected result:** The build window ends with a line `Driver exited with status N: <last non-empty output line>` with secrets redacted and no escape sequences; a successful run adds no such line.
- **Actual result:** Formatter produces 'Driver exited with status %s: %s' (with '(no output)' fallback). The unit test for it passed (6 tests OK). The live build-window rendering after a real non-zero driver exit was not observed.
