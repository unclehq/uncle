# Verification report

## Findings

### MC-101

- **Action:** Ran `printf '/q\n' | ./uncle --noui` from the worktree (piped stdin, not a TTY) and read the exit status.
- **Expected result:** The session quits and the process exit status is 0.
- **Actual result:** Session started, printed the banner, and exited with status 0.
- **Defects:** None

### MC-102

- **Action:** Ran `printf '/s\n/S\n/s extra\n/mode\n/quit\n' | ./uncle --noui` from the worktree (piped stdin).
- **Expected result:** Each of /s, /S and /s extra is refused with `ambiguous command: /s (matches: /settings, /stop)`, no command runs, and /mode still answers.
- **Actual result:** All three inputs printed `ambiguous command: /s (matches: /settings, /stop)`. The session continued and `/mode` answered `mode: unattended`. The process exit status was 2 after /quit. The check does not specify an exit status, and the likely cause is the earlier refused commands, but I did not investigate.
- **Defects:** None

### MC-103

- **Action:** Piped `/qu`, `/frob`, `/x`, `/1`, `/?`, `/` (one per line) then `/mode` into `uncle --noui` from /tmp/mcw (non-TTY stdin).
- **Expected result:** Each line refused with `unknown command: /<name>`, nothing expands or runs, session continues and `/mode` answers.
- **Actual result:** All six lines printed `unknown command: /qu`, `/frob`, `/x`, `/1`, `/?`, and `/` (bare slash), each followed by the command list. Nothing expanded. `/mode` then answered `mode: unattended`.
- **Defects:** None

### MC-105

- **Action:** Piped `/q now`, `/e foo`, `/mode`, `/Q` into `uncle --noui` and captured exit status.
- **Expected result:** `usage: /quit` and `usage: /exit` printed, neither quits, `/mode` answers, `/Q` quits with exit 0.
- **Actual result:** Output was `usage: /quit`, `usage: /exit`, `mode: unattended`; session then ended on `/Q` with EXIT=0.
- **Defects:** None

### MC-200

- **Action:** Piped '/s', '/s extra', '/S', '/h', '/q' into `./uncle --noui` (stdin not a TTY), captured output and exit status. Also ran '/q' and '/quit' alone.
- **Expected result:** Each of /s, /s extra, /S prints 'ambiguous command: /s (matches: /settings, /stop)' and runs nothing; /h shows help; /q exits with status 0.
- **Actual result:** The three refusals printed exactly 'ambiguous command: /s (matches: /settings, /stop)', nothing ran, and /h printed help. But after the refusals, /q exited with status 2, not 0. A lone '/q' or '/quit' exits 0. Running python3 scripts/lib/uncle_repl.py directly with '/x' then '/q' exited 0, so the 2 comes from running through ./uncle. I did not find the cause.
- **Defects:** Observed defect: ./uncle --noui exits 2 on /q or /quit after an earlier refusal; expected 0. Not yet logged in DEFECTS.md (worker may not edit it).

### MC-201

- **Action:** Piped '/qu', '/x', '/1', '/?', '/', '/q' into `./uncle --noui` and captured output and exit status.
- **Expected result:** Each of /qu, /x, /1, /?, / is refused as an unknown command, nothing expands or runs, and /q exits with status 0.
- **Actual result:** All five were refused with 'unknown command: /<token>' followed by the Commands line, and nothing ran or expanded. The session continued to /q, but the final exit status was 2, not 0.
- **Defects:** Same defect as MC-200: exit status 2 after /q following refusals, expected 0.

### MC-202

- **Action:** Ran `uncle --noui` (worktree ./uncle) in /tmp/mc2 with piped stdin: `/q now`, `/e foo`, `/Q`; captured output and exit status.
- **Expected result:** `/q now` prints `usage: /quit`, `/e foo` prints `usage: /exit`, session does not quit on either; `/Q` quits with status 0.
- **Actual result:** Output: banner, `usage: /quit`, `usage: /exit`. Session continued past both (the subsequent commands were processed) and `/Q` ended it with exit=0.
- **Defects:** None

### MC-203

- **Action:** Ran `uncle --noui` with piped stdin: `/m unattended`, `/mode`, `/M attended`, `/mode`, `/q`.
- **Expected result:** `/m unattended` acts like `/mode unattended` (mode: unattended), `/mode` reports unattended, `/M attended` gives mode: attended.
- **Actual result:** Output lines in order: `mode: unattended`, `mode: unattended`, `mode: attended`, `mode: attended`. Uppercase /M expanded and argument was kept.
- **Defects:** None

### MC-204

- **Action:** Ran repo ./uncle --noui (and installed uncle for the first pass) feeding /h, /i, /c, /t, /d, /r each followed by /e, and /e alone followed by /h, piping output through cat -v.
- **Expected result:** Each one-letter command behaves as its full command; usage complaints are the full command's own; /e ends the session.
- **Actual result:** /h printed the help text and command list; /i printed 'usage: /issue N' (the /issue command's own usage); /c printed 'clear_build is available in the full-screen UI only'; /t printed '/triage needs the TUI'; /d printed '/do needs the TUI'; /r printed 'resume_build is available in the full-screen UI only' (all are the full commands' own noui messages, none say unknown or ambiguous); /e ended the session (the following /h produced no output, exit code 0).
- **Defects:** None

### MC-205

- **Action:** Ran: printf '/\033[31mred\n/q\n' | ./uncle --noui | cat -v
- **Expected result:** Unknown-command refusal appears without the raw escape byte (no ^[[31m in cat -v), then the session quits on /q.
- **Actual result:** Output was 'unknown command: /red' followed by the command list; no ^[ or [31m sequence appeared; the session terminated on /q without hanging.
- **Defects:** None

### MC-301

- **Action:** Ran `printf '/q\n' | env -u UNCLE_RUNTIME_ROOT ./uncle --noui; echo EXIT=$?` from the worktree. The ambient UNCLE_RUNTIME_ROOT points at the installed brew build, so I unset it to exercise the worktree's scripts/lib/uncle_repl.py. Input was piped, not typed in a TTY.
- **Expected result:** The session quits and the process exit status is 0.
- **Actual result:** The session printed its banner and quit with no error. EXIT=0.
- **Defects:** None

### MC-302

- **Action:** Ran `printf '/s\n/qu\n/frob\n/1\n/q extra\n/q\n' | env -u UNCLE_RUNTIME_ROOT ./uncle --noui; echo EXIT=$?` from the worktree, so the worktree's uncle_repl.py was used. The 'Commands:' hint lines that follow each unknown-command message were filtered out of the transcript.
- **Expected result:** /s prints the ambiguous message. /qu, /frob and /1 each print 'unknown command: /<name>'. '/q extra' prints 'usage: /quit' and does not quit. Every refusal leaves the session running, and the final /q quits.
- **Actual result:** All messages matched. /s gave 'ambiguous command: /s (matches: /settings, /stop)'. /qu, /frob and /1 each gave 'unknown command: /<name>'. '/q extra' gave 'usage: /quit' without quitting. The session stayed alive through every refusal, and the final /q quit with EXIT=0. The installed brew build (older, 41398a8) returned EXIT=2 after refusals followed by /q. That is a stale-install difference. The worktree code (scripts/lib/uncle_repl.py loop) returns 0 on an explicit /quit.
- **Defects:** None

### MC-303

- **Action:** Piped `/m`, `/m unattended`, `/mode`, `/h`, `/S`, `/Q` into `./uncle --noui` from the worktree (non-tty, piped stdin) and captured output and exit status.
- **Expected result:** /m prints current mode; /m unattended prints `mode: unattended`; /mode reports unattended; /h prints help; /S refused as ambiguous with same message as /s; /Q quits.
- **Actual result:** Output: `mode: unattended` (/m), `mode: unattended` (/m unattended), `mode: unattended` (/mode), help text (`Type a message to chat...` and `Commands: /help /mode [attended|unattended] /issue N /stop /resume [N] /clear /triage /do /settings /quit`), `ambiguous command: /s (matches: /settings, /stop)` for /S, then the session ended on /Q. Process exit status was 2 in that run (the status of the earlier refusal carried through; `/Q` alone exits 0, and `/S` then `/Q` also exits 2). The check does not assert an exit status, so this is noted only as an observation relevant to MC-402/MC-403 style exit-status expectations.
- **Defects:** None

### MC-304

- **Action:** Piped `/<ESC>[31mx`, `/?`, `/mode`, `/q` into `./uncle --noui`, captured output to a file, inspected with `cat -v` and counted ESC bytes.
- **Expected result:** Both inputs refused as unknown commands; no raw escape byte emitted; terminal colour not changed; session keeps running.
- **Actual result:** Output `unknown command: /x` and `unknown command: /?`, each followed by the commands help line; `/mode` still answered `mode: unattended`, so the session kept running. ESC byte count in the output was 0 and `cat -v` showed no `^[` sequence. Terminal colour was not changed (output was captured to a file, so a live terminal colour was not watched). Exit status was 2, which this check does not assert.
- **Defects:** None

### MC-401

- **Action:** Piped '/help', '/mode', '/mode unattended', '/mode attended', '/quit' into `./uncle --noui` (worktree launcher) and captured transcript and exit status.
- **Expected result:** Full commands behave as before: help lists commands, mode reports and switches, /quit exits 0.
- **Actual result:** Banner and command list printed; '/mode' reported 'mode: unattended'; '/mode unattended' -> 'mode: unattended'; '/mode attended' -> 'mode: attended'; session ended with exit status 0.
- **Defects:** None

### MC-402

- **Action:** Piped '/qu', '/frob', '/x', '/', '/?', '/1', then '/q' into `./uncle --noui`; captured transcript and exit status. Also ran '/q' alone, '/frob' then '/quit', and '/frob' then EOF.
- **Expected result:** First six each print 'unknown command: /<name>' with refusal status 2, nothing expands, session stays open until '/q' quits with exit status 0.
- **Actual result:** All six printed 'unknown command: /qu', '/frob', '/x', '/', '/?', '/1' (followed by the command list) and nothing expanded; session stayed open and /q quit silently. However the final process exit status was 2, not 0. '/q' alone exits 0. '/frob' then '/quit' via ./uncle also exits 2. Running scripts/lib/uncle_repl.py directly (also with UNCLE_NOUI=1) with '/frob' then '/quit' exits 0, so the code comment 'explicit /quit is a clean exit' holds in the module but not via the ./uncle --noui launcher path; cause not determined.
- **Defects:** Unrecorded: exit status 2 instead of 0 after /q following refusals when launched via ./uncle --noui (module-direct run returns 0)

### MC-403

- **Action:** Piped '/s','/S','/s extra','/q extra','/q' into `uncle --noui` from /tmp/mc4 and captured output and exit status; then isolated with '/q' alone, '/s' then '/q', '/s' then '/quit', '/q extra' then '/q'.
- **Expected result:** First three print exactly `ambiguous command: /s (matches: /settings, /stop)`, run nothing. `/q extra` prints `usage: /quit` and does not quit. Bare `/q` then quits with exit status 0.
- **Actual result:** Output matched for the first three (identical ambiguous line x3) and `/q extra` printed `usage: /quit` without quitting; session then quit on `/q`. But the process exit status was 2, not 0. Isolation: '/q' alone -> 0; '/q extra' then '/q' -> 0; any prior ambiguous command ('/s' then '/q' or '/quit') -> exit 2. The ambiguous status 2 is carried into the final exit code of the quit.
- **Defects:** New: bare /q (or /quit) after an ambiguous slash command exits with status 2 instead of 0 (last-command status leaks into quit exit code). Not recorded in DEFECTS.md by this worker.

### MC-404

- **Action:** Piped '/m','/m unattended','/m','/mode','/h','/Q' into `uncle --noui`; separately ran '/help','/mode unattended','/q' as reference.
- **Expected result:** `/m` and `/mode` print the same mode line, `/m unattended` switches the mode as `/mode unattended` does, `/h` prints same help as `/help`, `/Q` quits with exit 0.
- **Actual result:** `/m`, `/m unattended`, `/m`, `/mode` all printed `mode: unattended`; `/h` printed the same two-line help text as `/help` in the reference run; `/mode unattended` in reference printed `mode: unattended` same as `/m unattended`; `/Q` quit with EXIT=0. Note: the starting mode was already unattended so a real switch was not distinguishable from a no-op.
- **Defects:** None

### MC-405

- **Action:** Piped printf '/\x1b[31mred\n/q\n' (real ESC byte) into `./uncle --noui` and captured the raw output through xxd.
- **Expected result:** Unknown-command refusal does not emit a raw ESC byte; session continues until /q quits it.
- **Actual result:** Output was 'unknown command: /red' followed by the commands help line; the ESC byte and the '[31m' sequence were stripped. No 0x1b byte appears in the hex dump. /q then ended the session cleanly with no further unknown-command message and exit code 0.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Transcript: 'uncle --noui interactive session. Type /help for commands, /quit to exit.' exit=0. Run used piped stdin rather than an interactive terminal. |
| MC-102 | YES | PASS | Transcript: three identical ambiguous-command lines, then 'mode: unattended'. |
| MC-103 | YES | PASS | Transcript: 'unknown command: /qu' ... 'unknown command: /' then 'mode: unattended'. Note: in a combined run, process exit status was 2 after unknown commands (not asserted by this check). |
| MC-105 | YES | PASS | Transcript: 'usage: /quit' / 'usage: /exit' / 'mode: unattended' / EXIT=0. Standalone `/Q` also gave EXIT=0. |
| MC-200 | YES | FAIL | Transcript: 'ambiguous command: /s (matches: /settings, /stop)' x3, then the help line, then exit status 2 (`echo $?` after the run). Source comment at scripts/lib/uncle_repl.py:387 says an explicit /quit after a refusal should return 0, but via ./uncle --noui the status was 2. Same exit 2 for '/x' then '/quit' and for '/h', '/x', '/q'. |
| MC-201 | YES | FAIL | Transcript: 'unknown command: /qu', '/x', '/1', '/?' and '/', each followed by the Commands line. `echo $?` printed 2. |
| MC-202 | YES | PASS | Transcript: 'uncle --noui interactive session. Type /help for commands, /quit to exit.' / 'usage: /quit' / 'usage: /exit'; exit=0. Piped stdin rather than a TTY. |
| MC-203 | YES | PASS | Transcript after banner: mode: unattended / mode: unattended / mode: attended / mode: attended. Piped stdin rather than a TTY. |
| MC-204 | YES | PASS | Terminal transcript: '/h' -> 'Commands: /help /mode ... /quit'; '/i' -> 'usage: /issue N'; '/t' -> '/triage needs the TUI; run uncle without --noui.'; '/e' then '/h' -> only the banner line. |
| MC-205 | YES | PASS | cat -v output: 'unknown command: /red' / 'Commands: /help /mode [attended/unattended] /issue N /stop /resume [N] /clear /triage /do /settings /quit' |
| MC-301 | YES | PASS | Transcript: 'uncle --noui interactive session. Type /help for commands, /quit to exit.' then 'EXIT=0'. The installed brew build also gave EXIT=0 for bare /q. |
| MC-302 | YES | PASS | Transcript: ambiguous command: /s (matches: /settings, /stop) / unknown command: /qu / unknown command: /frob / unknown command: /1 / usage: /quit / EXIT=0. |
| MC-303 | YES | PASS | Captured transcript of the run in a temp dir; separate runs: `printf '/Q\n' / uncle --noui` -> exit 0; `printf '/S\n/Q\n' / uncle --noui` -> `ambiguous command: /s (matches: /settings, /stop)`, exit 2. |
| MC-304 | YES | PASS | `cat -v b.out` showed no `^[`; `grep -c $'\x1b' b.out` -> 0. |
| MC-401 | YES | PASS | Transcript: 'Commands: /help /mode [attended/unattended] /issue N /stop /resume [N] /clear /triage /do /settings /quit', 'mode: unattended', 'mode: unattended', 'mode: attended'; exit=0. |
| MC-402 | YES | FAIL | Transcript in /tmp/mc402.txt; `printf '/qu\n/frob\n/x\n/\n/?\n/1\n/q\n' / ./uncle --noui` -> exit=2; `printf '/frob\n/quit\n' / ./uncle --noui` -> exit=2; same input to python3 scripts/lib/uncle_repl.py -> exit=0. |
| MC-403 | YES | FAIL | Transcript: 'ambiguous command: /s (matches: /settings, /stop)' x3, 'usage: /quit', EXIT=2. Isolation runs: '/s\n/q' EXIT=2; '/s\n/quit' EXIT=2; '/q' EXIT=0. |
| MC-404 | YES | PASS | Run 1 output: 'mode: unattended' x4, then 'Type a message to chat...' / 'Commands: /help /mode [attended/unattended] /issue N /stop /resume [N] /clear /triage /do /settings /quit', EXIT=0. Reference run help text identical. |
| MC-405 | YES | PASS | xxd offsets 0x4a-0x5b: '756e 6b6e 6f77 6e20 636f 6d6d 616e 643a 202f 7265 640a' = 'unknown command: /red\n'. Full dump (0x00-0xcb) contains no 0x1b byte. |
