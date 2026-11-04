# Defects

## None. A person must run `uncle` in two project directories in real terminal tabs, for example one named grove-issue-33, and record both tab titles.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation. The driver green-check covers automated assertions only and is not evidence of what a real terminal tab shows.
- **Expected result:** Each tab title reads `<dir basename> · uncle`, the two tabs are distinguishable, and the title matches the project name in the TUI status bar.
- **Actual result:** Not observed. I did not run uncle in a real terminal tab, so I have no tab-title observation.

## None. A person must start an issue-numbered run in the TUI tab from MC-100 and watch the title through the run and after it ends.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation. The tab title cannot be read headlessly.
- **Expected result:** During the run the title reads `<project> · uncle issue #152`. After the run ends it returns to `<project> · uncle`, never bare `uncle`.
- **Actual result:** Not observed. No run was started in a real terminal tab, so there is no tab-title observation.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live terminal tab was available. Automated coverage of title restore is in the driver green-check, which this worker did not re-run or cite as a pass for this row.
- **Expected result:** After quitting, the tab title is restored to MYSHELL on a terminal supporting the xterm title stack (otherwise it stays '<project> · uncle'), and is never bare 'uncle'.
- **Actual result:** Not observed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live terminal tab was available. This worker made no tab-title or screen observation.
- **Expected result:** In all three cases the tab title is never changed by uncle and no stray escape characters appear on screen.
- **Actual result:** Not observed.

## None. A person must run `uncle` in a terminal tab, start a driver with and without an issue number, exit, repeat with Ctrl-C, and watch the tab title.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation was made. The driver green-check and the terminal-title unit, shell and TUI tests cover escape-sequence emission, but they are not a visual tab-title observation.
- **Expected result:** Title shows `<project> · uncle` (with ` issue #N` when given) once, is not mangled by child drivers, and is restored on exit including after Ctrl-C.
- **Actual result:** Not performed. The tab title is a property of the host terminal emulator and cannot be read from a non-TTY worker.

## None. A person must run each driver directly from a terminal tab, abort with Ctrl-C, and observe the title during and after.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation was made. Automated tests cited by the driver green-check do not substitute for the human-visible tab-title observation.
- **Expected result:** Each driver sets `<project> · uncle` (plus issue suffix where applicable) while running and restores the prior title on exit/cancel, with no garbage characters printed.
- **Actual result:** Not performed. The tab title cannot be observed from a headless worker.

## None. A person must watch a real terminal tab's title during a TUI run and a line-menu run, then confirm that only the owner sets the title and that it is restored once on exit.

- **Status:** BLOCKED-HUMAN
- **Evidence:** MANUAL_CHECKLIST.json row MC-205. No terminal tab title observation was possible in this environment.
- **Expected result:** Only the owner (TUI or line menu) changes the title. The driver sets nothing and does not restore early, and the title is restored once on final exit.
- **Actual result:** Not observed. Automated coverage is the driver green-check's terminal-title tests, which this worker did not run and does not cite as a pass for this row.

## None. A person must run `uncle` in a real terminal tab that has a custom title, run a numbered issue, and observe the title at each step.

- **Status:** BLOCKED-HUMAN
- **Evidence:** MANUAL_CHECKLIST.json row MC-301. No terminal tab title observation was possible in this environment.
- **Expected result:** Title goes `<project> · uncle`, then `<project> · uncle issue #N` during the run, back to `<project> · uncle` at run end, and the previous custom title is restored on exit; bare `uncle` never appears.
- **Actual result:** Not observed. The worker could not see a terminal tab title.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs a person with a terminal emulator. The driver green-check covers automated assertions only. It does not replace the visual tab-title observation.
- **Expected result:** Neither tab title changes from its previous value and no stray escape text is printed.
- **Actual result:** Not performed. This worker has no real terminal tab, so it cannot observe tab titles.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs a person to run the uncle menu in a real tab and report the tab title during the run and after exit.
- **Expected result:** Title shows `<project> · uncle` during the run, with no nested push, and the prior title is restored on exit.
- **Actual result:** Not performed. This worker has no real terminal tab, so it cannot observe tab titles.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The driver green-check covers the automated terminal-title tests only. It does not replace this human observation.
- **Expected result:** Tab title shows `<project> · uncle` while idle; previous title restored after quit; bare `uncle` never shown.
- **Actual result:** Not executed. No real terminal tab is available to this worker, and the tab title cannot be observed programmatically.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The driver green-check covers the automated terminal-title tests only. It does not replace this human observation.
- **Expected result:** Issue run shows `<project> · uncle issue #N`; no-issue run shows `<project> · uncle`; title returns to `<project> · uncle` at run end without popping the saved title; status bar unchanged.
- **Actual result:** Not executed. A person must observe the real terminal tab title and status bar during live runs.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** cat -v output showed only the usage text; `grep -c '\^\[\]'` returned 0. This only covers the piped part, and only for --help rather than the interactive menu.
- **Expected result:** Tab title is not changed in either case, and no escape sequence garbage appears in the piped output.
- **Actual result:** Piped output contained no OSC title escape sequences (grep count 0). The tab-title half of the check could not be observed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. A person must run the three launch paths in a real terminal and note the tab title at start, during and after exit.
- **Expected result:** Under the TUI the driver does not alter the title or push extra; run directly or from the line menu, the title is `<project> · uncle` (with ` issue #N` when applicable) and is restored on exit, including after Ctrl-C cancel.
- **Actual result:** No tab title observation was made. Launching real drivers also requires an interactive terminal with a visible tab.
