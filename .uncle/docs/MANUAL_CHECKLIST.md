# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui`, type `/q` and press Enter, then check the process exit status.
- Expected result: The session quits and the process exit status is 0.
- Evidence to capture: Terminal transcript and the exit status.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/s`, then `/S`, then `/s extra`. Afterwards type `/mode` to confirm the session is still alive.
- Expected result: Each of the three inputs is refused with `ambiguous command: /s (matches: /settings, /stop)`, and no command runs. The session continues and `/mode` still answers.
- Evidence to capture: Terminal transcript showing all three refusal messages and the `/mode` reply.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/qu`, `/frob`, `/x`, `/1`, `/?` and a bare `/`, one per line. Then type `/mode` to confirm the session is still alive.
- Expected result: Each line is refused with `unknown command: /<name>` and nothing expands or runs. The session continues and `/mode` still answers.
- Evidence to capture: Terminal transcript of the six refusals and the `/mode` reply.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui`, type `/q now`, then `/e foo`, then `/mode`. Finish by typing `/Q`.
- Expected result: `/q now` prints `usage: /quit` and `/e foo` prints `usage: /exit`. Neither quits the session. `/mode` still answers, and `/Q` then quits with exit status 0.
- Evidence to capture: Terminal transcript of the two usage messages and the `/mode` reply, plus the final exit status.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/s`, then `/s extra`, `/S`, then `/h`, and finish with `/q`.
- Expected result: Each of `/s`, `/s extra` and `/S` prints `ambiguous command: /s (matches: /settings, /stop)` and runs neither command; the session continues, then `/h` shows help and `/q` exits with status 0.
- Evidence to capture: Terminal transcript showing the refusal text for all three inputs and the final exit status.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/qu`, `/x`, `/1`, `/?`, `/`, then `/q`.
- Expected result: Each of `/qu`, `/x`, `/1`, `/?` and `/` is refused as an unknown command and nothing expands or runs. The session continues until `/q` exits with status 0.
- Evidence to capture: Terminal transcript of the refusals and the final exit status.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/q now`, then `/e foo`, then `/Q`.
- Expected result: `/q now` prints `usage: /quit` and `/e foo` prints `usage: /exit`; the session does not quit on either. `/Q` then quits with status 0.
- Evidence to capture: Terminal transcript showing the usage lines, the session still accepting input, and the exit status after `/Q`.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/m unattended`, `/mode`, `/M attended`, `/mode`, then `/q`.
- Expected result: `/m unattended` behaves exactly like `/mode unattended` and the argument is kept: `mode: unattended`, then `/mode` reports unattended. `/M attended` switches to `mode: attended`, so uppercase one-letter names expand too.
- Evidence to capture: Terminal transcript showing the mode output after each command.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui`, type `/h`, `/i`, `/c`, `/t`, `/d`, `/r`, `/e`, one command per line, and watch for each result. Run `/e` last, since it exits.
- Expected result: Each one-letter command behaves as its full command would (help, issue, clear, triage, do, resume, exit) with no extra confirmation. Any usage complaint, for example `/i` with no issue number, is the full command's own complaint and not an unknown or ambiguous refusal. `/e` ends the session.
- Evidence to capture: Terminal transcript with the output of each command, compared against its full-name form.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` and type an unknown command whose name contains a raw escape sequence, such as `/` followed by Esc `[31mred`. Do this by piping `printf '/\033[31mred\n/q\n' | uncle --noui | cat -v`.
- Expected result: The unknown-command refusal appears, but the raw escape byte is not emitted: `cat -v` shows no `^[[31m` color sequence passing through. The session then quits on `/q`.
- Evidence to capture: The `cat -v` output of the refusal line.
- Actual result: 
- Status: NOT RUN

## Resources: live --noui session

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui` in a terminal, type `/q`, then check the process exit status with `echo $?`.
- Expected result: The session quits immediately with no error, and the exit status is 0.
- Evidence to capture: Terminal transcript showing `/q` and `echo $?` printing 0.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui`. Type `/s`, then `/qu`, then `/frob`, then `/1`, then `/q extra`. After that type `/q`.
- Expected result: `/s` prints `ambiguous command: /s (matches: /settings, /stop)`. `/qu`, `/frob` and `/1` each print `unknown command: /<name>`. `/q extra` prints `usage: /quit` and does not quit. Every refusal leaves the session running, and the final `/q` quits.
- Evidence to capture: Terminal transcript with the message for each input and the session still accepting input until the final `/q`.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui`. Type `/m`, then `/m unattended`, then `/mode`, then `/h`, then `/S`, then `/Q`.
- Expected result: `/m` prints the current mode. `/m unattended` behaves like `/mode unattended` and prints `mode: unattended`. `/mode` then reports unattended. `/h` prints the help text. `/S` is refused as ambiguous with the same message as `/s`. `/Q` quits the session.
- Evidence to capture: Terminal transcript of each input with its output, ending with the session quitting on `/Q`.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui`. Type `/` followed by an ESC character and `[31m` (for example `/\x1b[31mx`), then `/?`. Observe the terminal's colour and the output.
- Expected result: Both inputs are refused as unknown commands. The terminal does not switch to red, and no raw escape byte is emitted. The session keeps running.
- Evidence to capture: Terminal transcript or `cat -v` of the output showing no raw ESC byte, plus a note that the terminal colour was unchanged.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start `uncle --noui` and type full-name commands: `/help`, `/mode`, `/mode unattended`, `/mode attended`, then `/quit`.
- Expected result: Each full command behaves as before: help text lists the commands, mode reports and switches correctly, and `/quit` ends the session with exit status 0.
- Evidence to capture: Session transcript and the process exit status after `/quit`.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/qu`, `/frob`, `/x`, `/`, `/?` and `/1`, then `/q`.
- Expected result: Each of the first six prints `unknown command: /<name>` with refusal status 2, none expands or runs a command, and the session stays open until `/q` quits it with exit status 0.
- Evidence to capture: Transcript showing each refusal message and the final exit status.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/s`, `/S` and `/s extra`, then `/q extra`, then `/q`.
- Expected result: The first three print exactly `ambiguous command: /s (matches: /settings, /stop)` with status 2 and run nothing. `/q extra` prints `usage: /quit` and does not quit. Bare `/q` then quits with exit status 0.
- Evidence to capture: Transcript with the messages and the final exit status.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/m`, `/m unattended`, `/m`, `/mode`, `/h` and `/Q`.
- Expected result: `/m` and `/mode` print the same mode line, and `/m unattended` switches the mode exactly as `/mode unattended` does. `/h` prints the same help text as `/help`. `/Q` quits with exit status 0.
- Evidence to capture: Transcript showing the mode output, the help text and the exit status.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In `uncle --noui` type `/\x1b[31mred` (a real ESC byte in the name), capture the raw output bytes, then type `/q`.
- Expected result: The unknown-command refusal does not emit the raw escape sequence, because the output is escape-filtered. The session continues until `/q` quits it.
- Evidence to capture: Hex dump of the captured output showing no raw ESC (0x1b) byte.
- Actual result: 
- Status: NOT RUN
