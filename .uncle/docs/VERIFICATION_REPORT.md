# Verification report

## Findings

### MC-100

- **Action:** None performed. The check needs a human to look at the title of a real terminal tab. This worker is headless and has no terminal tab whose title it can read.
- **Expected result:** Each tab title reads `<dir basename> · uncle`, the two tabs are distinguishable, and the title matches the project name in the TUI status bar.
- **Actual result:** Not observed. I did not run uncle in a real terminal tab, so I have no tab-title observation.
- **Defects:** None. A person must run `uncle` in two project directories in real terminal tabs, for example one named grove-issue-33, and record both tab titles.

### MC-101

- **Action:** None performed. This check depends on the real tab from MC-100 and needs a person to watch the tab title during and after a live run with issue #152.
- **Expected result:** During the run the title reads `<project> · uncle issue #152`. After the run ends it returns to `<project> · uncle`, never bare `uncle`.
- **Actual result:** Not observed. No run was started in a real terminal tab, so there is no tab-title observation.
- **Defects:** None. A person must start an issue-numbered run in the TUI tab from MC-100 and watch the title through the run and after it ends.

### MC-102

- **Action:** Not performed live. The check needs a real terminal emulator tab where a person can see the tab title change and be restored after quitting uncle. This headless worker has no visible tab title to observe.
- **Expected result:** After quitting, the tab title is restored to MYSHELL on a terminal supporting the xterm title stack (otherwise it stays '<project> · uncle'), and is never bare 'uncle'.
- **Actual result:** Not observed.
- **Defects:** None

### MC-103

- **Action:** Not performed live. The check needs a person to watch a real terminal tab title across three launches: UNCLE_TERMINAL_TITLE=0 uncle, uncle | cat, and TERM=dumb uncle. They also need to confirm no stray escape characters appear on screen.
- **Expected result:** In all three cases the tab title is never changed by uncle and no stray escape characters appear on screen.
- **Actual result:** Not observed.
- **Defects:** None

### MC-104

- **Action:** Read the checklist row only. Did not launch the interactive uncle menu: the check requires a human to watch a real terminal tab title and use Ctrl-C interactively, which this headless worker cannot observe.
- **Expected result:** Title shows `<project> · uncle` (with ` issue #N` when given) once, is not mangled by child drivers, and is restored on exit including after Ctrl-C.
- **Actual result:** Not performed. The tab title is a property of the host terminal emulator and cannot be read from a non-TTY worker.
- **Defects:** None. A person must run `uncle` in a terminal tab, start a driver with and without an issue number, exit, repeat with Ctrl-C, and watch the tab title.

### MC-105

- **Action:** Read the checklist row only. Did not run stagegate.sh, change-workflow.sh or from-issue.sh with Ctrl-C: the check requires a human to watch the tab title of a real terminal tab while each driver runs and after it is aborted.
- **Expected result:** Each driver sets `<project> · uncle` (plus issue suffix where applicable) while running and restores the prior title on exit/cancel, with no garbage characters printed.
- **Actual result:** Not performed. The tab title cannot be observed from a headless worker.
- **Defects:** None. A person must run each driver directly from a terminal tab, abort with Ctrl-C, and observe the title during and after.

### MC-106

- **Action:** Created /tmp/x106 dirs: one named with embedded ESC]0;PWNED BEL bytes, one with a 110-char name. In a real pty (TERM=xterm) ran the shipped scripts/lib/terminal_title.py begin (the title writer used by uncle) in each cwd and captured raw bytes. Did not launch the full interactive uncle TUI or view a real terminal tab; the observation is the emitted title bytes.
- **Expected result:** No injected title or control effect; control chars absent from title; long name cut to 60 chars with ' · uncle' suffix intact.
- **Actual result:** Evil dir emitted ESC[22;2t ESC]2;evil]0;PWNEDname · uncle BEL: the ESC and BEL inside the name were stripped, so exactly one OSC title is emitted with no injected OSC. Long dir emitted a title of 60 'L' characters followed by ' · uncle'.
- **Defects:** None

### MC-202

- **Action:** Ran terminal_title.py begin in a pty with UNCLE_TERMINAL_TITLE=0 and captured raw output. Ran `uncle --help | cat` (stdout/stderr piped, non-tty), grepping for ESC]2 and ESC[22/23 sequences, and ran terminal_title.py begin piped through od -c. Did not launch the full TUI in a titled tab, so tab-title behavior was inferred from zero bytes emitted.
- **Expected result:** Tab title unchanged and piped output has no ESC]2 or CSI 22/23 t sequences.
- **Actual result:** With UNCLE_TERMINAL_TITLE=0 in a pty, output was b'' (nothing written). Piped `uncle --help | cat` had 0 matches for ESC]2 or ESC[22/23; piped terminal_title.py begin produced no bytes.
- **Defects:** None

### MC-205

- **Action:** Read the checklist row. No live action performed: it requires watching a real terminal tab title while a driver runs under the TUI and the line menu. This headless worker has no terminal tab whose title it can observe.
- **Expected result:** Only the owner (TUI or line menu) changes the title. The driver sets nothing and does not restore early, and the title is restored once on final exit.
- **Actual result:** Not observed. Automated coverage is the driver green-check's terminal-title tests, which this worker did not run and does not cite as a pass for this row.
- **Defects:** None. A person must watch a real terminal tab's title during a TUI run and a line-menu run, then confirm that only the owner sets the title and that it is restored once on exit.

### MC-301

- **Action:** Read the checklist row. No live action performed: it requires a real terminal tab with a known custom title, running `uncle`, a numbered issue run, and watching the tab title at each step. This headless worker cannot observe a terminal tab title.
- **Expected result:** Title goes `<project> · uncle`, then `<project> · uncle issue #N` during the run, back to `<project> · uncle` at run end, and the previous custom title is restored on exit; bare `uncle` never appears.
- **Actual result:** Not observed. The worker could not see a terminal tab title.
- **Defects:** None. A person must run `uncle` in a real terminal tab that has a custom title, run a numbered issue, and observe the title at each step.

### MC-302

- **Action:** Read the checklist row. No live action taken: it needs two real terminal emulator tabs and a person watching their titles.
- **Expected result:** Neither tab title changes from its previous value and no stray escape text is printed.
- **Actual result:** Not performed. This worker has no real terminal tab, so it cannot observe tab titles.
- **Defects:** None

### MC-303

- **Action:** Read the checklist row. No live action taken: it needs an interactive terminal tab running the uncle menu and a driver, with a person observing the title before, during and after.
- **Expected result:** Title shows `<project> · uncle` during the run, with no nested push, and the prior title is restored on exit.
- **Actual result:** Not performed. This worker has no real terminal tab, so it cannot observe tab titles.
- **Defects:** None

### MC-401

- **Action:** Read the checklist row. No action performed: it requires observing a real terminal tab title around an interactive `uncle` TUI session, which a headless worker cannot see.
- **Expected result:** Tab title shows `<project> · uncle` while idle; previous title restored after quit; bare `uncle` never shown.
- **Actual result:** Not executed. No real terminal tab is available to this worker, and the tab title cannot be observed programmatically.
- **Defects:** None

### MC-402

- **Action:** Read the checklist row. No action performed: it requires watching the tab title and status bar through issue-backed and no-issue runs in an interactive TUI.
- **Expected result:** Issue run shows `<project> · uncle issue #N`; no-issue run shows `<project> · uncle`; title returns to `<project> · uncle` at run end without popping the saved title; status bar unchanged.
- **Actual result:** Not executed. A person must observe the real terminal tab title and status bar during live runs.
- **Defects:** None

### MC-404

- **Action:** Ran `./uncle --help` piped through `cat -v` with and without UNCLE_TERMINAL_TITLE=0 (non-TTY stdin/stdout) and grepped for OSC escape sequences. Did not observe a real terminal tab title, since no graphical terminal is available to this worker.
- **Expected result:** Tab title is not changed in either case, and no escape sequence garbage appears in the piped output.
- **Actual result:** Piped output contained no OSC title escape sequences (grep count 0). The tab-title half of the check could not be observed.
- **Defects:** None

### MC-405

- **Action:** Not performed. The check needs a human to watch a terminal tab title across TUI, direct stagegate.sh and line-menu launches, including Ctrl-C cancel.
- **Expected result:** Under the TUI the driver does not alter the title or push extra; run directly or from the line menu, the title is `<project> · uncle` (with ` issue #N` when applicable) and is restored on exit, including after Ctrl-C cancel.
- **Actual result:** No tab title observation was made. Launching real drivers also requires an interactive terminal with a visible tab.
- **Defects:** None

### MC-406

- **Action:** Created /tmp/x406/<'a' ESC ]2;PWNED BEL> and a 100-char 'b' directory. In each, ran the real scripts/lib/terminal_title.py functions (project_name, build_title, osc) to get the title and OSC sequence uncle would emit. Did not launch the full uncle TUI or screenshot a real terminal tab.
- **Expected result:** No injected title text appears; control characters are removed; long names are truncated to 60 characters with ' · uncle' suffix intact.
- **Actual result:** Control dir: ESC and BEL stripped, title 'a]2;PWNED · uncle'. The emitted sequence is a single OSC 2 (\x1b]2;...\x07), so there is no second injected OSC. The leftover ']2;PWNED' is inert printable text. Long dir: build_title gave 60 'b' characters + ' · uncle', suffix intact.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | BLOCKED-HUMAN | No live observation. The driver green-check covers automated assertions only and is not evidence of what a real terminal tab shows. |
| MC-101 | YES | BLOCKED-HUMAN | No live observation. The tab title cannot be read headlessly. |
| MC-102 | YES | BLOCKED-HUMAN | No live terminal tab was available. Automated coverage of title restore is in the driver green-check, which this worker did not re-run or cite as a pass for this row. |
| MC-103 | YES | BLOCKED-HUMAN | No live terminal tab was available. This worker made no tab-title or screen observation. |
| MC-104 | YES | BLOCKED-HUMAN | No live observation was made. The driver green-check and the terminal-title unit, shell and TUI tests cover escape-sequence emission, but they are not a visual tab-title observation. |
| MC-105 | YES | BLOCKED-HUMAN | No live observation was made. Automated tests cited by the driver green-check do not substitute for the human-visible tab-title observation. |
| MC-106 | YES | PASS | pty capture: b'\x1b[22;2t\x1b]2;evil]0;PWNEDname \xc2\xb7 uncle\x07' and b'\x1b[22;2t\x1b]2;LLLL...(60 L) \xc2\xb7 uncle\x07'. L count was read by eye from the repr, not measured programmatically; terminal_title.py MAX_PROJECT=60 and sanitize drop Cc/Cf. |
| MC-202 | YES | PASS | Opt-out pty capture: b''. grep -c of ESC]2/ESC[2[23] on piped uncle --help output: 0. od -c of piped begin: empty. |
| MC-205 | YES | BLOCKED-HUMAN | MANUAL_CHECKLIST.json row MC-205. No terminal tab title observation was possible in this environment. |
| MC-301 | YES | BLOCKED-HUMAN | MANUAL_CHECKLIST.json row MC-301. No terminal tab title observation was possible in this environment. |
| MC-302 | YES | BLOCKED-HUMAN | Needs a person with a terminal emulator. The driver green-check covers automated assertions only. It does not replace the visual tab-title observation. |
| MC-303 | YES | BLOCKED-HUMAN | Needs a person to run the uncle menu in a real tab and report the tab title during the run and after exit. |
| MC-401 | YES | BLOCKED-HUMAN | None. The driver green-check covers the automated terminal-title tests only. It does not replace this human observation. |
| MC-402 | YES | BLOCKED-HUMAN | None. The driver green-check covers the automated terminal-title tests only. It does not replace this human observation. |
| MC-404 | YES | BLOCKED-HUMAN | cat -v output showed only the usage text; `grep -c '\^\[\]'` returned 0. This only covers the piped part, and only for --help rather than the interactive menu. |
| MC-405 | YES | BLOCKED-HUMAN | None. A person must run the three launch paths in a real terminal and note the tab title at start, during and after exit. |
| MC-406 | YES | PASS | build_title/osc output: '\x1b]2;a]2;PWNED · uncle\x07' and '\x1b]2;' + 60*'b' + ' · uncle\x07'. Caveat: evidence is from the title functions, not a screenshot of an actual terminal tab. |
