# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the app (./uncle) in a real terminal sized about 24 rows and again about 50 rows, and look at the home page with an empty composer.
- Expected result: The status line (model/project/branch) is on the very last terminal row, and the composer's bottom rule sits directly above it with no blank row between them.
- Evidence to capture: Screenshot or pasted screen text of the home page at each terminal height.
- Actual result: 
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page type a long message that wraps to 2, 4 and then 6+ composer rows, watching the bottom of the screen after each step.
- Expected result: The status stays on the last row and the bottom rule stays directly above it. The composer grows upward and the cursor stays on the last visible composer row. The greeting, hint and logo text are unchanged.
- Evidence to capture: Screenshots or screen text at each wrap count, noting the cursor position.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page type `/` to trigger the slash-command hint. Then trigger a chat error, for example by submitting a message that is expected to produce one. Do this at a non-compact height of about 40 rows and again at a compact height of about 14 rows.
- Expected result: One feedback line stays visible on a row other than the last row and never overlaps the status. In compact mode it temporarily replaces the hint, and the hint returns once the feedback clears. When several conditions are active, chat_error shows first.
- Evidence to capture: Screenshots or screen text showing the feedback line and status in each case, and after clearing.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the home page with several chat history entries, resize the terminal to about 12 rows, then to about 5 rows. Scroll the history and try mouse selection of a history line.
- Expected result: History renders above the greeting and composer block and is scrollable. Mouse selection hits the correct history rows. Nothing crashes at small sizes. At 5 rows the status is on the last row and the bottom rule is directly above it.
- Evidence to capture: Screen text at each size, and the selected text matching the clicked line.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the app in a real terminal of about 24 rows, open the home page, and look at the bottom of the screen with an empty composer, then after typing text long enough to wrap to 2 through 6 rows.
- Expected result: The status text sits on the very last screen row. The composer's bottom rule is directly above it with no blank row between them, at every wrap count.
- Evidence to capture: Screenshots or terminal captures at each wrap count showing the last rows.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page, trigger each feedback condition one at a time: a chat error, a file choice, and typing '/'. Then trigger several at once and clear them.
- Expected result: One feedback line is visible and never overlaps the status row. With several active, the order is chat error, then file choice, then slash hint. In compact height the hint is hidden only while feedback shows and returns when it clears.
- Evidence to capture: Captures of each condition and the cleared state.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page with several chat history entries, resize the terminal down to very small heights (about 5 rows, then 3 rows) and back up. Type a long wrapped message, check where the cursor sits, and scroll or click history.
- Expected result: The app does not crash or garble the screen. The status stays on the last row and the bottom rule on the row above it. History appears only above the composer and scrolls. The cursor sits on the last visible composer row.
- Evidence to capture: Captures at each size and a note on cursor position and absence of errors.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Launch ./uncle in a real terminal sized about 24 rows and again about 50 rows, and look at the home page with an empty composer.
- Expected result: The status bar is on the very last terminal row, and no blank row separates the composer's bottom rule from the status line.
- Evidence to capture: Screenshot or terminal capture at each size with the last two rows visible.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: On the home page, type a long message that wraps to several rows, then resize the terminal taller and shorter.
- Expected result: As the composer grows, the block moves up. The status stays on the last row, directly under the bottom rule, and the cursor sits on the last visible composer row.
- Evidence to capture: Captures with 1, 3 and 6+ wrapped rows, noting cursor position.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: On the home page, type `/` to show the slash hint. Then trigger a chat error and a file choice if possible.
- Expected result: One feedback line is visible and does not overlap the status row. The precedence is chat_error, then file choice, then slash hint. The hint text returns when the feedback clears.
- Evidence to capture: Captures of each feedback state and after it clears.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: With chat history present on the home page, scroll the history and select text with the mouse. Then resize to a very short terminal of about 5 rows.
- Expected result: History renders above the composer and scrolls. Mouse selection hits the correct rows. The status stays on the last row with the bottom rule above it, with no crash at the small size.
- Evidence to capture: Captures of history, a selection result and the 5-row view.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a run from the home page so the build page (state running) is shown in a real terminal of ~30 rows; observe the composer, the blank-row spacing and the status row beneath it.
- Expected result: Build page layout is unchanged: status row sits two rows below the composer's first row (directly after the bottom rule, no blank row), is not forced to the last screen row, and greeting/hint/status text is unchanged.
- Evidence to capture: Terminal screenshot or text capture of the build page with row positions noted.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the chat panel page (if reachable from the TUI) in a real terminal and type a multi-line message into its composer.
- Expected result: Chat panel composer and status placement behave as before the change (not bottom-anchored), and no layout corruption or exceptions occur.
- Evidence to capture: Screenshot or text capture of the chat panel with composer and status visible.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page with several chat history entries present, scroll the history and click/drag with the mouse to select history text, then resize the terminal taller and shorter and repeat.
- Expected result: History renders above the composer, scrolls, and mouse selection highlights the text under the pointer (no row offset); the status stays on the last row with no gap below the composer rule after each resize.
- Evidence to capture: Screenshots after each resize and note of selected text versus pointer location.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On the home page, type a long message that wraps to 6+ rows, then clear it and type '/' ; also trigger a chat error or file choice if possible.
- Expected result: Composer growth moves the block up while status stays on the last row; feedback remains visible on one line not overlapping the status; hint text returns once feedback clears; cursor stays on the last visible composer row and the terminal shows no crash.
- Evidence to capture: Screenshots at each state plus note that the cursor location is on the composer.
- Actual result: 
- Status: NOT RUN
