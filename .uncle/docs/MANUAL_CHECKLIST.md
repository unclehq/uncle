# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui` in a scratch project directory, type `/q` and press Enter, then type `echo after` on the next line (or pipe both lines via stdin).
- Expected result: The session ends on `/q` exactly as `/quit` does; the following line is not processed and no unknown-command error appears.
- Evidence to capture: Terminal transcript showing the session exit, absence of any response to the later line, and the process exit code.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fresh `uncle --noui` session, type `/s` and press Enter, then type `/mode` on the next line.
- Expected result: `/s` prints `ambiguous command: /s (matches: /settings, /stop)` (matches sorted alphabetically per the change plan) to stderr with no `unknown command` text and runs nothing. The session keeps running, so `/mode` still responds. When the session ends, the exit code is 2.
- Evidence to capture: Transcript with stdout and stderr shown separately, the `/mode` response after the refusal, and the exit code.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/m unattended`, then `/m`, then `/h`, then `/i` with no number, then `/Q`.
- Expected result: `/m unattended` prints `mode: unattended`, and `/m` then reports `mode: unattended`. `/h` prints the help text. `/i` prints `usage: /issue`, the same as `/issue`. `/Q` quits the session.
- Evidence to capture: Terminal transcript of each command's output and the final session exit.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/qu`, `/frob`, `/x`, `/?`, `/1`, and a bare `/`, one per line, then `/quit`.
- Expected result: Each of the first five lines prints `unknown command: /<name>` followed by the Commands line, and the session continues. The refusals use the unknown-command path and contain no raw escape bytes, and the bare `/` is also refused. `/quit` then exits.
- Evidence to capture: Transcript of the refusals, a check that no raw ESC bytes appear in the output (for example `cat -v`), and the exit code.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/q now`, `/e foo`, `/c x`, `/r x`, `/t x`, then `/t`, `/d`, then `/quit`.
- Expected result: `/q now` prints `usage: /quit` and `/e foo` prints `usage: /exit`, and neither quits. `/c x`, `/r x` and `/t x` print `usage: /clear`, `usage: /resume` and `usage: /triage`. `/t` and `/d` print the `needs the TUI` message, and `/quit` finally ends the session.
- Evidence to capture: Transcript of each command's output, showing the session still alive after the usage errors.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/frob`, then `/qu`, then `/x`, then `/`, then `/?`, then `/1`, then `/help`, and finally `/quit`.
- Expected result: Each of the first six lines prints `unknown command: /<name>` plus the Commands line on stderr and is not run, the session keeps reading, `/help` still prints help, and `/quit` ends the session.
- Evidence to capture: Terminal transcript showing each refusal, the later `/help` output and the session ending.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/s`, then `/s foo`, then `/mode`, then `/quit`; check the exit code after the session ends.
- Expected result: `/s` and `/s foo` each print `ambiguous command: /s (matches: ...)` naming both /stop and /settings, without the text `unknown command` and without running either command. `/mode` is still processed afterwards. The exit code is 2 and the output has no raw escape bytes.
- Evidence to capture: Transcript with both ambiguity messages, the later `/mode` output and the exit code.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/q now`, then `/e foo`, then `/mode`, then `/q`, then `/mode`. Run `printf '/Q\n/mode\n' | uncle --noui` in a separate session.
- Expected result: `/q now` prints `usage: /quit` and `/e foo` prints the exit usage, neither quits, and the first `/mode` still prints. Bare `/q` quits so the final `/mode` is never processed. In the separate session `/Q` quits and its `/mode` output never appears.
- Evidence to capture: Both terminal transcripts showing the usage lines and where each session ended.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` and type `/m unattended`, `/m`, `/h`, `/i`, `/i x`, `/issue`, `/c x`, `/clear x`, `/r x`, `/t`, `/t x`, `/d`, `/triage`, `/do`, then `/quit`.
- Expected result: `/m unattended` sets and reports unattended mode and `/m` reports it. `/h` prints help. Each shortcut gives the same output as its full name, so `/i` and `/issue` both print `usage: /issue`, and `/c x`, `/r x` and `/t x` print the full-name usage lines. `/t` and `/d` print the same `needs the TUI` message as `/triage` and `/do`.
- Evidence to capture: Transcript pairing each shortcut with its full-name output.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` and type `/\x1b` (a literal escape character) and a non-ASCII single character such as `/é`. Then type `/s`.
- Expected result: The escape and non-ASCII names are refused as unknown commands with no crash. No raw terminal escape sequence reaches the terminal for any of the three lines, and the session continues.
- Evidence to capture: Transcript, plus a hex dump of the output (for example via `| od -c`) showing no raw ESC bytes.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui` in a scratch project directory, type `/q`, then type `/help` on the next line, and note the process exit status.
- Expected result: The session ends on `/q` with exit code 0, and the following `/help` line is never processed (no help output).
- Evidence to capture: Terminal transcript showing no help output after `/q`, and the exit code.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/s`, then `/s foo`, then `/mode`, then `/quit`; capture stderr separately and the exit code.
- Expected result: Both `/s` and `/s foo` print `ambiguous command: /s (matches: /settings, /stop)` on stderr without the text `unknown command`; the session keeps running so `/mode` prints the mode, and `/quit` ends the session.
- Evidence to capture: Transcript with stdout and stderr distinguished, showing the ambiguity messages and the `/mode` output.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/m unattended`, `/m`, `/h`, `/i`, `/t`, `/d`, then `/quit`.
- Expected result: `/m unattended` prints `mode: unattended` and `/m` then reports unattended; `/h` prints the help text; `/i` prints `usage: /issue`; `/t` and `/d` print the `needs the TUI` messages for triage and do.
- Evidence to capture: Transcript of each command's output.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/qu`, `/frob`, `/x`, `/?`, `/1`, a bare `/`, then `/q now`, then `/mode`, then `/Q`.
- Expected result: Each of the first six prints `unknown command: /<name>` followed by the Commands line, with no crash and no raw escape characters; `/q now` prints `usage: /quit` and does not quit; `/mode` is still processed; `/Q` quits the session.
- Evidence to capture: Transcript of the outputs and the final exit.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/quit`, then type `/help` on a second session after `/exit`, confirming each full name still works; in a third session type `/quit` followed by `/help`.
- Expected result: `/quit` and `/exit` end the session with later lines unread; `/help` prints the help text in a session that continues.
- Evidence to capture: Terminal transcript of the three sessions showing no output for lines after quit.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/frob`, `/qu`, `/x`, bare `/`, `/?` and `/1`, then `/help`, noting the exit code at the end via `/quit`.
- Expected result: Each unmatched name prints `unknown command: /<name>` followed by the Commands line, nothing is executed, the session keeps reading lines, and the process exit code is 2.
- Evidence to capture: Transcript of stderr output for each line and the final process exit code.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/mode unattended`, `/mode`, `/mode attended`, `/mode bogus`, `/issue` and `/issue abc`.
- Expected result: Full-name commands behave as before: mode is set and echoed, `/mode bogus` prints `usage: /mode ...`, `/issue` and `/issue abc` print `usage: /issue`.
- Evidence to capture: Transcript showing each output line.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/q now`, `/e foo`, `/c x`, `/r x`, `/t x`, then `/h`, then `/q`, then a final line `/help`.
- Expected result: Argument forms print the full-name usage lines (`usage: /quit`, `usage: /exit`, `usage: /clear`, `usage: /resume`, `usage: /triage`) and do not quit; `/h` prints help; bare `/q` ends the session and the final `/help` is not processed.
- Evidence to capture: Transcript showing usage lines and absence of output after `/q`.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/Q` in one session, and in another type `/m unattended`, `/m`, `/i`, `/t`, `/d`.
- Expected result: `/Q` quits like `/q`; `/m unattended` sets and echoes mode unattended, `/m` shows the mode, `/i` prints `usage: /issue`, `/t` and `/d` print `/triage needs the TUI; run `uncle` without --noui.` and the `/do` equivalent.
- Evidence to capture: Transcripts of both sessions.
- Actual result: 
- Status: NOT RUN
