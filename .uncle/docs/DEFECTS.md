# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Probe output: enter [call('hello')] ''; ctrl+enter 'a\nb' False; esc+enter 'a\nb' False. Check requires a human-visible observation in a real CSI-u capable terminal, which was not performed.
- **Expected result:** Plain Enter submits 'hello' and clears composer. Ctrl+Enter and Esc+Enter insert a newline at the cursor and send nothing.
- **Actual result:** Enter: send_home_chat('hello') called once, composer ''. Ctrl+Enter (ESC[13;5u) after 'a' then 'b': composer 'a\nb', nothing sent. Esc+Enter on 'ab' cursor 1: 'a\nb', nothing sent. Handler-level behavior matches; live-terminal observation not made.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Probe output: paste 'Xl1\nl2\nl3Y' False; ctrl paste 'a[31mbc\td\ne' False. Live terminal paste and before/after screenshots require a human.
- **Expected result:** Block inserted at cursor with newlines preserved, nothing submitted. Control/escape chars dropped, TAB and LF kept.
- **Actual result:** Paste: composer 'Xl1\nl2\nl3Y', nothing sent. Control paste: composer 'a[31mbc\td\ne' (ESC and BEL dropped, TAB and LF kept; the printable '[31m' remains as expected from dropping only the ESC byte), nothing sent. Handler-level behavior matches; live-terminal observation not made.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No screenshot or pasted text was captured.
- **Expected result:** The selected composer text is copied and pasted correctly; Ctrl-C inside the app still quits.
- **Actual result:** Not performed. This worker has no interactive terminal emulator, mouse selection, or system clipboard and paste target.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No terminal transcript was captured.
- **Expected result:** No ESC[200~ markers or modifyOtherKeys residue appear in the shell after any exit. While suspended modes are off, and after fg Ctrl+Enter and paste work again.
- **Actual result:** Not performed. This worker cannot observe real terminal mode state, bracketed-paste behaviour, or job-control suspend/resume.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None captured. The scripts/tests/home-composer-keys-test.py file exists but was not run here, and I did not read the driver green-check. Neither is a substitute for a human keypress observation.
- **Expected result:** Each Ctrl+Enter inserts a newline and nothing is submitted; the composer retains 'abc' and 'def' on separate lines (SI-1).
- **Actual result:** Not observed. I did not run the check and did not infer a result from automated tests.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None captured. The needed screenshots before and after the Enter could not be taken here.
- **Expected result:** The whole block appears as 3 lines without submitting; only the final plain Enter submits it as a single message (SI-1, AC-3).
- **Actual result:** Not observed. I did not run the check and did not infer a result from automated tests.

## None. A person with a capable terminal (e.g. kitty, WezTerm or iTerm2) must launch the TUI, exit it by quit, kill -TERM and kill -HUP, then run cat, paste multi-line text and press Ctrl+D.

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The driver green-check was not cited because it does not cover this live terminal observation.
- **Expected result:** After each exit path the shell is clean: no ESC[200~ markers on paste and keys behave normally (SI-3).
- **Actual result:** Not executed. I did not simulate the terminal, so there is no observation to report and nothing is claimed as passed.

## None. A person must run the TUI in an enhanced-key-capable terminal and record each key's outcome.

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The prepared probe scripts/tests/home-composer-keys-test.py was not run or cited as proof.
- **Expected result:** Plain Enter submits, backslash-Enter inserts a newline without submitting, Meta b/f/d move or delete by word, and Ctrl-C quits as before (SI-5, AC-4).
- **Actual result:** Not executed. No key outcomes were observed, so nothing is claimed as passed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No terminal transcript captured.
- **Expected result:** After exit, `cat` echoes the paste with no ESC[200~ / ESC[201~ markers, and keys behave normally.
- **Actual result:** Not executed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No transcript captured.
- **Expected result:** The shell is clean after each signal exit: no bracketed-paste markers in pasted text and normal key behavior.
- **Actual result:** Not executed.

## None. A person in a real terminal must run the Ctrl-Z, cat, paste, fg, paste sequence.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No transcript or screenshots exist. The row's evidence_to_capture asks for a suspended-shell paste transcript, which cannot be produced without an interactive terminal.
- **Expected result:** While suspended, paste has no markers; after fg, bracketed paste is active again (multi-line paste inserts without submitting).
- **Actual result:** Not performed.

## None. A person in a Ctrl+Enter-capable terminal must run this sequence.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No screenshots exist. The row needs human-visible terminal observation of the composer after each step.
- **Expected result:** Ctrl+Enter inserts a newline without submitting; the 3-line paste inserts at the cursor without submitting; plain Enter then submits and clears the composer.
- **Actual result:** Not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation was made. The driver green-check is not cited as a PASS for these live key and paste interactions.
- **Expected result:** Paste and Ctrl+Enter while the picker is open are ignored with no insert or submit; with plain composer focus, Esc+Enter inserts a newline, and backslash-Enter still continues the line.
- **Actual result:** Not performed. This worker has no interactive terminal or screenshot capability for the TUI.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live observation was made.
- **Expected result:** Selected text copies and pastes correctly elsewhere; Meta b/f/d still move/delete by word; Ctrl-C quits the app.
- **Actual result:** Not performed. Terminal text selection, the system clipboard and a second application cannot be exercised from this worker.

## None. Needs a pty screen emulator (e.g. pexpect+pyte, or tmux) to drive the live TUI and cover the picker and slash command.

- **Status:** BLOCKED-SETUP
- **Evidence:** Script output: "401a hello '' [('hello',)]"; "401 empty '' [('',)]"; "401 /help (slash) '/help' [('',)]". Not a live TUI observation. Driver unit tests (home-composer-keys-test.py AC1) are cited as separate automated evidence.
- **Expected result:** Plain Enter submits non-empty text and clears the composer; with the picker/menu open Enter accepts the entry; slash command runs; Enter on an empty composer sends nothing.
- **Actual result:** 'hello' + Enter called send_home_chat('hello') and left the composer ''. Enter on an empty composer called send_home_chat('') (the handler passes it through; whether the real send_home_chat ignores blank text was not checked here, and the unit test AC1 filters blank calls). After '/help' + Enter in this harness the composer stayed '/help'. The slash path (uncle_tui.py:7176) was not shown to run, so slash execution is unverified. The picker case was not tested.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** pty transcript from /tmp/pt.py: both runs end with '\x1b[?2004l\x1b[>4;0m ... \x1b[?1049l'. Word-motion and Esc-then-key pushback is covered by the driver green-check unit tests (test_AC4_esc_other_key_pushed_back, not re-run here).
- **Expected result:** Ctrl-C quits; Alt+b/f/d move/delete by word as before; Esc then 'x' delivers key with no newline/submit.
- **Actual result:** Ctrl-C: the app ran its full exit teardown (alt-screen leave ?1049l, ?2004l, >4;0m emitted). Alt+b/f/d and Esc+x were sent without crash or early exit, and the app was still running until Ctrl-C. Cursor positions and the absence of a newline were NOT visually observed, because the raw pty byte stream was not rendered to a screen. Real terminal with enhanced key reporting not available here.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. The row declares the exclusive resource 'clipboard' and requires screenshots of the selection and the paste. The driver green-check does not cover clipboard behavior.
- **Expected result:** Selected composer text copies and pastes elsewhere unchanged; mouse capture toggling still works; Ctrl-C in the TUI still quits rather than copying.
- **Actual result:** Not executed. The check depends on human mouse selection and the OS clipboard, and the required screenshots of the selection and of the pasted text cannot be produced by this worker.

## MC-107

- **Status:** NOT RUN
- **Evidence:** No worker observation was supplied for this checklist item.
- **Expected result:** Multi-line paste does not submit per line, and a lone Enter after typing still submits.
- **Actual result:** Not performed.

## MC-205

- **Status:** NOT RUN
- **Evidence:** No worker observation was supplied for this checklist item.
- **Expected result:** While suspended, pasted text has no markers; after resume, bracketed paste and Ctrl+Enter work again in the composer (SI-3).
- **Actual result:** Not performed.
