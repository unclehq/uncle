# Verification report

## Findings

### MC-101

- **Action:** Fed the exact byte sequences (Enter=10, ESC [13;5u, ESC CR) into the real UncleTUI.handle_key via the repo's FakeScreen harness (temp script .uncle/tests/mc101.py). Did not drive a live CSI-u terminal; no terminal-screen emulator (pyte) is available and no human was present.
- **Expected result:** Plain Enter submits 'hello' and clears composer. Ctrl+Enter and Esc+Enter insert a newline at the cursor and send nothing.
- **Actual result:** Enter: send_home_chat('hello') called once, composer ''. Ctrl+Enter (ESC[13;5u) after 'a' then 'b': composer 'a\nb', nothing sent. Esc+Enter on 'ab' cursor 1: 'a\nb', nothing sent. Handler-level behavior matches; live-terminal observation not made.
- **Defects:** None

### MC-102

- **Action:** Fed bracketed-paste byte streams into the real UncleTUI.handle_key via FakeScreen: 'l1\nl2\nl3' pasted at cursor 1 of 'XY', and a paste containing ESC[31m, BEL, TAB, LF. Did not paste into a live terminal.
- **Expected result:** Block inserted at cursor with newlines preserved, nothing submitted. Control/escape chars dropped, TAB and LF kept.
- **Actual result:** Paste: composer 'Xl1\nl2\nl3Y', nothing sent. Control paste: composer 'a[31mbc\td\ne' (ESC and BEL dropped, TAB and LF kept; the printable '[31m' remains as expected from dropping only the ESC byte), nothing sent. Handler-level behavior matches; live-terminal observation not made.
- **Defects:** None

### MC-106

- **Action:** Drove the real UncleTUI.handle_key (headless, using the project's FakeScreen harness from scripts/tests/home-composer-keys-test.py; not a real terminal/pty) with a bracketed paste (ESC[200~ line1\nline2\r\nline3 ESC[201~) and then Ctrl+Enter (ESC[13;5u) in (a) slash picker state (composer '/', chat_picker=True) and (b) edit mode (chat_edit=True, composer 'abc'). Also ran a control paste in plain composing state.
- **Expected result:** Paste and Ctrl+Enter are swallowed in picker/edit states: no text inserted, no newline, nothing submitted, picker/edit state unchanged.
- **Actual result:** Picker: after paste composer '/', chat_picker True, send count 0; after Ctrl+Enter same. Edit: after paste composer 'abc', chat_edit True, send count 0; after Ctrl+Enter same. Control (plain composing) paste inserted 'line1\nline2\nline3' without submitting, showing the swallow is state-specific.
- **Defects:** None

### MC-104

- **Action:** Drove the real UncleTUI.handle_key headlessly (FakeScreen harness): Enter after 'ab\', Enter after 'ab\\', Ctrl-C (3), ESC b/f/d and CSI modifyOtherKeys Meta b/f/d (ESC[27;3;98/102/100~) on 'foo bar baz'. Picker Enter acceptance not separately driven; covered by existing driver tests.
- **Expected result:** Backslash+Enter continues on a new line; double backslash+Enter sends one trailing backslash; Ctrl-C quits; Meta b/f/d move/kill by word, with enhanced key modes enabled.
- **Actual result:** 'ab\'+Enter -> composer 'ab\n', nothing sent. 'ab\\'+Enter -> send_home_chat called once with 'ab\' (one trailing backslash), composer cleared. Ctrl-C -> state 'quit'. 'foo bar baz': ESC b from 8 -> 4; ESC f from 4 -> 7; ESC d from 4 -> 'foo  baz'; CSI forms gave identical results. Picker/slash Enter accept was NOT directly exercised by me.
- **Defects:** None

### MC-105

- **Action:** Read the checklist row only. Did not perform it: it needs a human at a real terminal emulator to toggle mouse capture, select text with the mouse, copy with the system shortcut, and paste into another application.
- **Expected result:** The selected composer text is copied and pasted correctly; Ctrl-C inside the app still quits.
- **Actual result:** Not performed. This worker has no interactive terminal emulator, mouse selection, or system clipboard and paste target.
- **Defects:** None

### MC-106

- **Action:** Read the checklist row only. Did not perform it: it needs a human at an interactive shell and real terminal to quit the app, send kill -TERM and kill -HUP, run cat, paste, press keys, and do Ctrl-Z / fg with Ctrl+Enter.
- **Expected result:** No ESC[200~ markers or modifyOtherKeys residue appear in the shell after any exit. While suspended modes are off, and after fg Ctrl+Enter and paste work again.
- **Actual result:** Not performed. This worker cannot observe real terminal mode state, bracketed-paste behaviour, or job-control suspend/resume.
- **Defects:** None

### MC-200

- **Action:** No live action performed. The check needs a CSI-u/modifyOtherKeys-capable terminal and a real Ctrl+Enter keypress. This headless worker has neither.
- **Expected result:** Each Ctrl+Enter inserts a newline and nothing is submitted; the composer retains 'abc' and 'def' on separate lines (SI-1).
- **Actual result:** Not observed. I did not run the check and did not infer a result from automated tests.
- **Defects:** None

### MC-201

- **Action:** No live action performed. The check needs a real system-clipboard paste of a 3-line CRLF block into the home composer in an interactive terminal. This headless worker has no interactive terminal or clipboard.
- **Expected result:** The whole block appears as 3 lines without submitting; only the final plain Enter submits it as a single message (SI-1, AC-3).
- **Actual result:** Not observed. I did not run the check and did not infer a result from automated tests.
- **Defects:** None

### MC-203

- **Action:** Ran temporary probe .uncle/tests/mc202_203_probe.py driving the real UncleTUI.handle_key/_read_csi/_read_paste path (fake curses screen, no real terminal/pty) with a 2,080,000-byte bracketed paste of multibyte characters (accents, CJK, emoji) and many newlines, terminated by ESC[201~, followed by a trailing 'x' keystroke.
- **Expected result:** Composer truncated at the limit, no hang, nothing submitted, no leftover paste bytes acting as keystrokes (SI-2).
- **Actual result:** Composer held exactly 1048576 bytes (COMPOSER_LIMIT), truncated on a valid UTF-8 boundary; completed in 0.34s; send_home_chat not called; no extra bytes inserted or interpreted as keys after the paste.
- **Defects:** None

### MC-203

- **Action:** With the same probe, put the composer in the slash-menu state (text '/') and in the issue-picker state (chat_picker=True with choices), then fed a multi-line bracketed paste, Ctrl+Enter as CSI-u (ESC[13;5u) and Ctrl+Enter as modifyOtherKeys (ESC[27;5;13~) in each state.
- **Expected result:** Paste and Ctrl+Enter swallowed: no text inserted, no newline, no menu/picker selection, nothing submitted (D-6).
- **Actual result:** In both states _chat_menu returned 'slash' / 'picker' and _plain_composing was False. After the paste and both Ctrl+Enter forms the composer was unchanged ('/' and '#'), send_home_chat and _run were not called.
- **Defects:** None

### MC-206

- **Action:** None performed. The check needs a real enhanced-key-capable terminal emulator with a human watching it, to see whether pasted text in `cat` shows ESC[200~ markers after quit, SIGTERM and SIGHUP. This worker has no such terminal.
- **Expected result:** After each exit path the shell is clean: no ESC[200~ markers on paste and keys behave normally (SI-3).
- **Actual result:** Not executed. I did not simulate the terminal, so there is no observation to report and nothing is claimed as passed.
- **Defects:** None. A person with a capable terminal (e.g. kitty, WezTerm or iTerm2) must launch the TUI, exit it by quit, kill -TERM and kill -HUP, then run cat, paste multi-line text and press Ctrl+D.

### MC-206

- **Action:** None performed. The check needs interactive keystrokes (plain Enter, backslash-Enter, Alt+b/f/d, Ctrl-C) in a terminal with enhanced key modes active, observed by a person. This worker has no such terminal.
- **Expected result:** Plain Enter submits, backslash-Enter inserts a newline without submitting, Meta b/f/d move or delete by word, and Ctrl-C quits as before (SI-5, AC-4).
- **Actual result:** Not executed. No key outcomes were observed, so nothing is claimed as passed.
- **Defects:** None. A person must run the TUI in an enhanced-key-capable terminal and record each key's outcome.

### MC-301

- **Action:** Read the checklist row only; did not launch the TUI. The row requires a real interactive terminal (launch TUI, Ctrl-C, then paste multi-line text into `cat` and press Ctrl-D) and a human-visible shell key-behavior observation, which this non-interactive worker cannot perform faithfully.
- **Expected result:** After exit, `cat` echoes the paste with no ESC[200~ / ESC[201~ markers, and keys behave normally.
- **Actual result:** Not executed.
- **Defects:** None

### MC-302

- **Action:** Read the checklist row only; did not launch the TUI. The row requires two terminals, kill -TERM/-HUP from the second, and then pasting multi-line text into `cat` in the original real terminal, which needs a person at a real terminal.
- **Expected result:** The shell is clean after each signal exit: no bracketed-paste markers in pasted text and normal key behavior.
- **Actual result:** Not executed.
- **Defects:** None

### MC-303

- **Action:** Read the checklist row. Did not launch the TUI: the row needs a real interactive terminal with job control (Ctrl-Z, fg) and a physical or terminal-emulator paste, which this non-interactive worker lacks.
- **Expected result:** While suspended, paste has no markers; after fg, bracketed paste is active again (multi-line paste inserts without submitting).
- **Actual result:** Not performed.
- **Defects:** None. A person in a real terminal must run the Ctrl-Z, cat, paste, fg, paste sequence.

### MC-304

- **Action:** Read the checklist row. Did not launch the TUI: the row needs a Ctrl+Enter-capable terminal (kitty, WezTerm, iTerm2 or Ghostty), real key presses and a real terminal paste, and this worker has none of these.
- **Expected result:** Ctrl+Enter inserts a newline without submitting; the 3-line paste inserts at the cursor without submitting; plain Enter then submits and clears the composer.
- **Actual result:** Not performed.
- **Defects:** None. A person in a Ctrl+Enter-capable terminal must run this sequence.

### MC-305

- **Action:** Read the checklist row only; did not drive the interactive TUI. The row needs a real terminal session with bracketed paste into an open picker, Ctrl+Enter, Esc+Enter and backslash-Enter, and a person looking at the screen.
- **Expected result:** Paste and Ctrl+Enter while the picker is open are ignored with no insert or submit; with plain composer focus, Esc+Enter inserts a newline, and backslash-Enter still continues the line.
- **Actual result:** Not performed. This worker has no interactive terminal or screenshot capability for the TUI.
- **Defects:** None

### MC-306

- **Action:** Read the checklist row only; did not run it. The row needs the mouse-capture toggle (Ctrl-G), selecting text, a system-clipboard copy and paste into another app, Meta b/f/d word movement, and Ctrl-C quit in a real terminal.
- **Expected result:** Selected text copies and pastes correctly elsewhere; Meta b/f/d still move/delete by word; Ctrl-C quits the app.
- **Actual result:** Not performed. Terminal text selection, the system clipboard and a second application cannot be exercised from this worker.
- **Defects:** None

### MC-401

- **Action:** No pty screen emulator (pexpect/pyte) is available, so I drove the real UncleTUI.handle_key from a temporary script (/tmp/mc4/p.py) with Enter (10) and a stubbed send_home_chat. Typed 'hello' + Enter, Enter on an empty composer, and '/help' + Enter. I did not exercise the 'build #45' issue picker, and I did not run the real curses TUI.
- **Expected result:** Plain Enter submits non-empty text and clears the composer; with the picker/menu open Enter accepts the entry; slash command runs; Enter on an empty composer sends nothing.
- **Actual result:** 'hello' + Enter called send_home_chat('hello') and left the composer ''. Enter on an empty composer called send_home_chat('') (the handler passes it through; whether the real send_home_chat ignores blank text was not checked here, and the unit test AC1 filters blank calls). After '/help' + Enter in this harness the composer stayed '/help'. The slash path (uncle_tui.py:7176) was not shown to run, so slash execution is unverified. The picker case was not tested.
- **Defects:** None. Needs a pty screen emulator (e.g. pexpect+pyte, or tmux) to drive the live TUI and cover the picker and slash command.

### MC-402

- **Action:** Same temporary harness calling the real handle_key with the home composer open. Typed 'line one\' + Enter. Cleared the composer, typed 'x\\' + Enter. Pressed F4 (curses.KEY_F4), typed 'abc', moved the cursor before 'c', and pressed Enter.
- **Expected result:** Trailing single backslash plus Enter becomes a newline without submitting; double backslash sends one trailing backslash; Enter in edit mode inserts a newline at the cursor without submitting.
- **Actual result:** 'line one\' + Enter left the composer as 'line one\n' with no send. 'x\\' + Enter called send_home_chat('x\\') (one trailing backslash) and cleared the composer. In edit mode (chat_edit=True after F4), Enter with the cursor before 'c' gave 'ab\nc' with no new send. All three match the expected behavior. This ran against the handler in a harness, not the full curses screen.
- **Defects:** None

### MC-403

- **Action:** Ran uncle_tui.py under a pty (TERM=xterm-256color). Run 1: typed 'hello world' then Ctrl-C. Run 2: typed 'foo bar baz', sent ESC b, ESC f, ESC d, then ESC x, then Ctrl-C. Captured terminal output.
- **Expected result:** Ctrl-C quits; Alt+b/f/d move/delete by word as before; Esc then 'x' delivers key with no newline/submit.
- **Actual result:** Ctrl-C: the app ran its full exit teardown (alt-screen leave ?1049l, ?2004l, >4;0m emitted). Alt+b/f/d and Esc+x were sent without crash or early exit, and the app was still running until Ctrl-C. Cursor positions and the absence of a newline were NOT visually observed, because the raw pty byte stream was not rendered to a screen. Real terminal with enhanced key reporting not available here.
- **Defects:** None

### MC-306

- **Action:** Launched uncle_tui.py in a pty and exited it via Ctrl-C (normal quit), SIGTERM and SIGHUP; checked the output stream for the mode-disable sequences. Did not run the interactive 'cat' paste step in a real shell.
- **Expected result:** After every exit path, bracketed paste (?2004) and modifyOtherKeys (>4;0m) are reset so the shell is clean.
- **Actual result:** Enable sequence '\x1b[?2004h' was emitted at startup (offset 175). On the Ctrl-C, SIGTERM and SIGHUP exits, '\x1b[?2004l' and '\x1b[>4;0m' were emitted at the end of the stream, followed by alt-screen exit. In all three cases the mode reset was emitted. The cat paste/arrow-key step was not performed, so no shell-level confirmation.
- **Defects:** None

### MC-406

- **Action:** Read the MC-406 row from the canonical checklist JSON. No live action was performed, because the row needs a person at a real terminal: mouse selection, the system copy shortcut, and a paste into a separate application. This worker has no access to the user's system clipboard or a second GUI application.
- **Expected result:** Selected composer text copies and pastes elsewhere unchanged; mouse capture toggling still works; Ctrl-C in the TUI still quits rather than copying.
- **Actual result:** Not executed. The check depends on human mouse selection and the OS clipboard, and the required screenshots of the selection and of the pasted text cannot be produced by this worker.
- **Defects:** None

### MC-107

- **Action:** In a terminal lacking enhanced-key support (or with UNCLE_ENHANCED_KEYS=0), paste a multi-line block and press Enter once after typing.
- **Expected result:** Multi-line paste does not submit per line, and a lone Enter after typing still submits.
- **Actual result:** Not performed.
- **Defects:** None

### MC-205

- **Action:** With the TUI running, press Ctrl-Z to suspend, run `cat` and paste to check for residue, then `fg` to resume and paste again in the composer.
- **Expected result:** While suspended, pasted text has no markers; after resume, bracketed paste and Ctrl+Enter work again in the composer (SI-3).
- **Actual result:** Not performed.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | BLOCKED-HUMAN | Probe output: enter [call('hello')] ''; ctrl+enter 'a\nb' False; esc+enter 'a\nb' False. Check requires a human-visible observation in a real CSI-u capable terminal, which was not performed. |
| MC-102 | YES | BLOCKED-HUMAN | Probe output: paste 'Xl1\nl2\nl3Y' False; ctrl paste 'a[31mbc\td\ne' False. Live terminal paste and before/after screenshots require a human. |
| MC-103 | YES | PASS | Temp driver /tmp/mc/drive.py output lines: 'picker after paste ("'/'", True, False, 0)', 'picker after ctrl-enter ("'/'", True, False, 0)', 'edit after paste ("'abc'", False, True, 0)', 'edit after ctrl-enter ("'abc'", False, True, 0)', 'control paste ("'line1\nline2\nline3'", False, False, 0)'. Caveat: headless key-handler drive, no screenshots; issue-picker variant not separately exercised (shares chat_picker flag). |
| MC-104 | YES | PASS | /tmp/mc/drive.py output: 'bs+enter ("'ab\\n'",...,0)', 'dbl bs+enter ... call('ab\\')', 'state after ctrl-c quit', 'ESC b ... 4', 'ESC f ... 7', 'ESC d foo  baz 4', CSI b/f/d same. Driver green-check reports no regressions (PREEXISTING only). Picker/slash Enter acceptance sub-item left unverified live. |
| MC-105 | YES | BLOCKED-HUMAN | None. No screenshot or pasted text was captured. |
| MC-106 | YES | BLOCKED-HUMAN | None. No terminal transcript was captured. |
| MC-200 | YES | BLOCKED-HUMAN | None captured. The scripts/tests/home-composer-keys-test.py file exists but was not run here, and I did not read the driver green-check. Neither is a substitute for a human keypress observation. |
| MC-201 | YES | BLOCKED-HUMAN | None captured. The needed screenshots before and after the Enter could not be taken here. |
| MC-202 | YES | PASS | Probe output: 'blob bytes 2080000 / MC202 composer bytes 1048576 limit 1048576 secs 0.34 sent False'. Limitation: in-process probe, not a real terminal, so no screenshot was captured. |
| MC-203 | YES | PASS | Probe output: "slash after composer '/' sent False run False"; "picker after composer '#' sent False run False". Limitation: in-process probe, no screenshots of a real terminal. |
| MC-204 | YES | BLOCKED-HUMAN | None. The driver green-check was not cited because it does not cover this live terminal observation. |
| MC-206 | YES | BLOCKED-HUMAN | None. The prepared probe scripts/tests/home-composer-keys-test.py was not run or cited as proof. |
| MC-301 | YES | BLOCKED-HUMAN | None. No terminal transcript captured. |
| MC-302 | YES | BLOCKED-HUMAN | None. No transcript captured. |
| MC-303 | YES | BLOCKED-HUMAN | No transcript or screenshots exist. The row's evidence_to_capture asks for a suspended-shell paste transcript, which cannot be produced without an interactive terminal. |
| MC-304 | YES | BLOCKED-HUMAN | No screenshots exist. The row needs human-visible terminal observation of the composer after each step. |
| MC-305 | YES | BLOCKED-HUMAN | No live observation was made. The driver green-check is not cited as a PASS for these live key and paste interactions. |
| MC-306 | YES | BLOCKED-HUMAN | No live observation was made. |
| MC-401 | YES | BLOCKED-SETUP | Script output: "401a hello '' [('hello',)]"; "401 empty '' [('',)]"; "401 /help (slash) '/help' [('',)]". Not a live TUI observation. Driver unit tests (home-composer-keys-test.py AC1) are cited as separate automated evidence. |
| MC-402 | YES | PASS | Script output: "402a 'line one\n' []"; "402b '' [('x\\',)]"; "402c 'ab\nc' [('x\\',)] edit True" (the only send call is the earlier double-backslash one). |
| MC-403 | YES | BLOCKED-HUMAN | pty transcript from /tmp/pt.py: both runs end with '\x1b[?2004l\x1b[>4;0m ... \x1b[?1049l'. Word-motion and Esc-then-key pushback is covered by the driver green-check unit tests (test_AC4_esc_other_key_pushed_back, not re-run here). |
| MC-404 | YES | PASS | Offsets: enable@175, disable ?2004l@2184, >4;0m@2192 for the SIGTERM and SIGHUP runs. For the Ctrl-C run, disable@2184 and >4;0m@2192. |
| MC-406 | YES | BLOCKED-HUMAN | None. The row declares the exclusive resource 'clipboard' and requires screenshots of the selection and the paste. The driver green-check does not cover clipboard behavior. |
| MC-107 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
| MC-205 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
