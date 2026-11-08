# Manual checklist

## Coverage: Enter and newline

### MC-101
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a live home composer in a CSI-u or modifyOtherKeys capable terminal, type 'hello', press Enter; then type 'a', press Ctrl+Enter, type 'b'; then press Esc followed by Enter in a plain composer.
- Expected result: Plain Enter submits 'hello' and clears the composer. Ctrl+Enter and Esc+Enter insert a newline at the cursor, advance it, and send nothing.
- Evidence to capture: Screenshots or transcript after each key showing the composer content and whether a message was sent.
- Actual result: 
- Status: NOT RUN

## Coverage: Paste

### MC-102
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Paste a 3-line block ('l1\nl2\nl3') into the home composer mid-text with the cursor in the middle, then paste text containing an embedded ESC sequence or control characters.
- Expected result: The block is inserted at the cursor with newlines preserved and nothing is submitted. Control and escape characters are dropped but TAB and LF are kept.
- Evidence to capture: Screenshot of the composer before and after each paste and confirmation no message was sent.
- Actual result: 
- Status: NOT RUN

## Coverage: Paste in non-composing states

### MC-103
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Open the slash menu or issue picker (and separately edit mode with F4), then paste a multi-line block and press Ctrl+Enter.
- Expected result: The paste and Ctrl+Enter are swallowed: no text inserted, no newline, nothing submitted, and the picker or edit state is unchanged.
- Evidence to capture: Screenshots of each state before and after the paste and Ctrl+Enter.
- Actual result: 
- Status: NOT RUN

## Coverage: Preserved behaviors

### MC-104
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In the home composer, verify backslash then Enter continues onto a new line, double backslash then Enter sends one trailing backslash, picker or slash Enter still accepts the entry, Ctrl-C quits, and Meta b/f/d move by word.
- Expected result: All pre-existing behaviors work as before with the enhanced key modes enabled.
- Evidence to capture: Transcript or screenshots of each action and its result.
- Actual result: 
- Status: NOT RUN

## Coverage: Copy

### MC-105
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Toggle mouse capture off with Ctrl-G (or use the terminal bypass modifier), select composer text, copy with the system shortcut, and paste it into another application.
- Expected result: The selected composer text is copied and pasted correctly; Ctrl-C inside the app still quits.
- Evidence to capture: Screenshot of the selection and the text pasted elsewhere.
- Actual result: 
- Status: NOT RUN

## Coverage: Terminal teardown

### MC-106
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: After quitting the app normally, then separately after kill -TERM and kill -HUP, run 'cat' in the shell, paste text and type keys; also Ctrl-Z suspend then fg resume the app and test Ctrl+Enter.
- Expected result: No ESC[200~ markers or modifyOtherKeys residue appear in the shell after any exit. While suspended modes are off, and after fg Ctrl+Enter and paste work again.
- Evidence to capture: Terminal transcript of the cat output after each exit and after resume.
- Actual result: 
- Status: NOT RUN

## Coverage: Fallback terminals

### MC-107
- Required for acceptance: NO
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a terminal lacking enhanced-key support (or with UNCLE_ENHANCED_KEYS=0), paste a multi-line block and press Enter once after typing.
- Expected result: Multi-line paste does not submit per line, and a lone Enter after typing still submits.
- Evidence to capture: Screenshot of the composer after the paste and after the lone Enter.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: In a CSI-u/modifyOtherKeys-capable terminal, launch the TUI, type 'abc', then press Ctrl+Enter, type 'def', and press Ctrl+Enter again.
- Expected result: Each Ctrl+Enter inserts a newline at the cursor and advances it; nothing is submitted and the composer retains 'abc', 'def' on separate lines (SI-1).
- Evidence to capture: Screenshot or transcript of the composer showing multi-line text and no sent message.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the home composer, paste a 3-line text block (including CRLF line endings) from the system clipboard, then press Enter once.
- Expected result: The whole block appears at the cursor as 3 lines without submitting; only the final plain Enter submits it as a single message (SI-1, AC-3).
- Evidence to capture: Screenshots before and after the Enter showing the composer content and a single sent message.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Paste a text block far larger than the composer limit (over 1 MiB, e.g. generated with multibyte characters and many newlines) into the composer.
- Expected result: The composer is truncated at the limit, the app does not hang, nothing is submitted, and no leftover paste bytes act as keystrokes afterwards (SI-2).
- Evidence to capture: Screenshot of the composer after paste and confirmation that no message was sent.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the slash menu (type '/') and, separately, an issue picker, then paste a multi-line block and press Ctrl+Enter in each state.
- Expected result: The paste and Ctrl+Enter are swallowed: no text inserted, no newline, no picker/menu selection, nothing submitted (D-6).
- Evidence to capture: Screenshots of the menu/picker state before and after each action.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: tui:home-agent-session
- Depends on: none
- Exact action: Launch the TUI in a capable terminal, then quit normally; run `cat`, paste multi-line text and press Ctrl+D. Repeat quitting via `kill -TERM` and via `kill -HUP` of the TUI process.
- Expected result: After each exit path the shell is clean: pasted text shows no ESC[200~ markers and keys behave normally, confirming modes were disabled (SI-3).
- Evidence to capture: Terminal transcript of the cat output for each of the three exit paths.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: NO
- Exclusive resources: none
- Depends on: none
- Exact action: With the TUI running, press Ctrl-Z to suspend, run `cat` and paste to check for residue, then `fg` to resume and paste again in the composer.
- Expected result: While suspended, pasted text has no markers; after resume, bracketed paste and Ctrl+Enter work again in the composer (SI-3).
- Evidence to capture: Transcript of the suspended-shell paste and screenshot of the resumed composer.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With enhanced key modes active, press plain Enter with text, backslash-then-Enter, type text and press Alt/Meta b, f, d for word movement, and press Ctrl-C.
- Expected result: Plain Enter submits, backslash-Enter inserts a newline without submitting, Meta b/f/d move/delete by word, and Ctrl-C quits as before (SI-5, AC-4).
- Evidence to capture: Transcript or screenshots of each key's observed outcome.
- Actual result: 
- Status: NOT RUN

## Resources: terminal mode lifecycle

### MC-301
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a real terminal, launch the TUI, then quit normally with Ctrl-C. At the shell, run `cat`, paste a multi-line text, press Ctrl-D, and press Enter on an empty line.
- Expected result: After exit, `cat` echoes the paste with no ESC[200~ / ESC[201~ markers, and keys behave normally (no CSI-u/modifyOtherKeys residue).
- Evidence to capture: Terminal transcript or screenshot of the cat output and shell key behavior.
- Actual result: 
- Status: NOT RUN

### MC-302
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Launch the TUI in a terminal, then from a second terminal run `kill -TERM <pid>`; repeat in a fresh launch with `kill -HUP <pid>`. In the original terminal, run `cat` and paste multi-line text.
- Expected result: The shell is clean after each signal exit: no bracketed-paste markers in pasted text and normal key behavior.
- Evidence to capture: Transcript of both kill runs and the cat paste output.
- Actual result: 
- Status: NOT RUN

### MC-303
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Launch the TUI, press Ctrl-Z to suspend, run `cat` and paste text at the shell, Ctrl-D, then run `fg` and paste multi-line text into the composer.
- Expected result: While suspended, paste has no markers; after `fg`, bracketed paste is active again (multi-line paste inserts without submitting).
- Evidence to capture: Transcript/screenshots of suspended-shell paste and the composer after resume.
- Actual result: 
- Status: NOT RUN

## Resources: composer paste and Ctrl+Enter

### MC-304
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a Ctrl+Enter-capable terminal (e.g. kitty, WezTerm, iTerm2, Ghostty), launch the TUI, type text, press Ctrl+Enter, type more, then paste a 3-line text at the cursor mid-text, then press Enter.
- Expected result: Ctrl+Enter inserts a newline without submitting; the 3-line paste inserts at the cursor without submitting; plain Enter then submits and clears the composer.
- Evidence to capture: Screenshots of the composer after each step and the sent message.
- Actual result: 
- Status: NOT RUN

## Resources: composer picker and fallback

### MC-305
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Open the slash menu or issue picker in the composer, then paste multi-line text and press Ctrl+Enter. Afterward, close the picker, press Esc then Enter, and also test backslash-Enter at the end of a line.
- Expected result: Paste and Ctrl+Enter while the picker is open are ignored with no insert or submit; with plain composer focus, Esc+Enter inserts a newline, and backslash-Enter still continues the line.
- Evidence to capture: Screenshots of the picker state after paste/Ctrl+Enter and of the composer after Esc+Enter and backslash-Enter.
- Actual result: 
- Status: NOT RUN

## Resources: copy and key smoke

### MC-306
- Exclusive resources: browser:system
- Depends on: none
- Exact action: With composer text present, toggle mouse capture off with Ctrl-G (or use the terminal's bypass modifier), select composer text and copy with the system shortcut, paste into another app. Then test Meta b/f/d word movement and Ctrl-C quit.
- Expected result: Selected text copies and pastes correctly elsewhere; Meta b/f/d still move/delete by word; Ctrl-C quits the app.
- Evidence to capture: Screenshot of the pasted text in the other app and notes on word-movement and quit behavior.
- Actual result: 
- Status: NOT RUN

## Resources: cleanup on quit

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the home composer of the running TUI, type 'hello' and press plain Enter; then type 'build #45' with an issue picker/slash menu open and press Enter; then type '/help' and press Enter.
- Expected result: Plain Enter submits non-empty text and clears the composer; with the picker/menu open Enter accepts the entry; slash command runs; Enter on an empty composer sends nothing.
- Evidence to capture: Screenshot or terminal transcript after each Enter showing composer cleared/message sent/command output.
- Actual result: 
- Status: NOT RUN

## Resources: UI responsiveness

### MC-306
- Required for acceptance: NO
- Exclusive resources: tui:session-E
- Depends on: none
- Exact action: In the home composer, type 'line one\' and press Enter, then type 'x\\' and press Enter; then press F4 for edit mode, type text and press Enter.
- Expected result: Trailing single backslash plus Enter becomes a newline without submitting; double backslash sends one trailing backslash; Enter in edit mode inserts a newline at the cursor without submitting.
- Evidence to capture: Screenshots of composer contents after each step and the sent message text for the double-backslash case.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: terminal:uncle-tui
- Depends on: none
- Exact action: With text in the composer, press Ctrl-C; separately in a fresh session with a word-filled composer press Meta/Alt+b, Alt+f, Alt+d, and Esc followed by a non-Enter key (e.g. 'x'), in a terminal with enhanced key reporting enabled.
- Expected result: Ctrl-C still quits the app; Alt+b/f/d move/delete by word as before; Esc then 'x' behaves as before (key delivered, no newline inserted, no submit).
- Evidence to capture: Terminal transcript/screenshots showing cursor positions after each key and the app exiting on Ctrl-C.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: terminal:interactive
- Depends on: none
- Exact action: Launch the TUI in a terminal, quit normally, then launch again and terminate it with kill -TERM and again with kill -HUP; after each, run 'cat' in the shell, paste multi-line text and type arrow keys, then press Ctrl-D.
- Expected result: After every exit path the shell is clean: no '^[[200~' or '^[[201~' markers appear on paste and keys behave normally; the terminal is not left in a modified key-reporting mode.
- Evidence to capture: Terminal transcript of the cat session after each exit showing pasted text without escape markers.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: clipboard
- Depends on: none
- Exact action: Turn mouse capture off with Ctrl-G (or use the terminal's bypass modifier), select text in the home composer with the mouse, copy with the system shortcut, and paste into another application; then toggle Ctrl-G back.
- Expected result: Selected composer text copies and pastes elsewhere unchanged; mouse capture toggling still works; Ctrl-C in the TUI still quits rather than copying.
- Evidence to capture: Screenshot of selection and of the pasted text in the other application.
- Actual result: 
- Status: NOT RUN
