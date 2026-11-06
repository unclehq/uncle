# Verification report

## Findings

### MC-101

- **Action:** Piped '/q' then 'echo after' into `./uncle --noui` from the worktree root, with the inherited UNCLE_RUNTIME_ROOT (/opt/homebrew/opt/uncle/libexec, an installed older build) unset so the worktree code under test ran.
- **Expected result:** Session ends on /q exactly as /quit; the following line is not processed and no unknown-command error appears.
- **Actual result:** Session ended on /q. stdout showed only the banner, with no echo of 'after'. stderr was empty. Exit code 0. Note: with the inherited UNCLE_RUNTIME_ROOT set, ./uncle ran the installed Homebrew build, which printed 'unknown command: /q'. That is an environment artifact, not the worktree code.
- **Defects:** None

### MC-102

- **Action:** Piped '/s' then '/mode' into `./uncle --noui` from the worktree root, with UNCLE_RUNTIME_ROOT unset so the worktree code ran. Captured stdout and stderr separately.
- **Expected result:** /s prints 'ambiguous command: /s (matches: /settings, /stop)' to stderr, with no 'unknown command' text, and runs nothing. The session continues so /mode responds. Exit code is 2.
- **Actual result:** stderr: 'ambiguous command: /s (matches: /settings, /stop)'. stdout: banner followed by 'mode: attended', so the session kept running. No 'unknown command' text. Exit code 2.
- **Defects:** None

### MC-103

- **Action:** Ran the worktree's `uncle --noui` (UNCLE_RUNTIME_ROOT set to the worktree, inherited startup-action env vars unset so the plain REPL started) in a scratch git repo, piping `/m unattended`, `/m`, `/h`, `/i`, `/Q`.
- **Expected result:** `/m unattended` prints `mode: unattended`; `/m` reports `mode: unattended`; `/h` prints help; `/i` prints `usage: /issue`; `/Q` quits.
- **Actual result:** Output: `mode: unattended`, `mode: unattended`, the help text ('Type a message to chat...' plus the Commands line), `usage: /issue N`. `/Q` ended the session with exit code 0.
- **Defects:** None

### MC-104

- **Action:** Ran the worktree's `uncle --noui` and piped `/qu`, `/frob`, `/x`, `/?`, `/1`, a bare `/`, then `/quit`. Output went to a file and was inspected with cat -v and a grep for ESC bytes.
- **Expected result:** Each of the first five lines prints `unknown command: /<name>` plus the Commands line and the session continues; the bare `/` is also refused; there are no raw escape bytes; `/quit` exits.
- **Actual result:** All six inputs printed `unknown command: /<name>` (/qu, /frob, /x, /?, /1, and `/` with an empty name), each followed by the Commands line. The session continued through all of them and `/quit` ended it. The ESC byte count in the output was 0. The exit code was 2, which matches the documented --noui refusal contract; MC-103, with no refusals, exited 0.
- **Defects:** None

### MC-105

- **Action:** Ran the worktree's ./uncle --noui (UNCLE_RUNTIME_ROOT set to the worktree, because the ambient value pointed to the installed Homebrew copy, which predates the change) with piped input: /q now, /e foo, /c x, /r x, /t x, /t, /d, /quit.
- **Expected result:** /q now prints usage: /quit and /e foo prints usage: /exit without quitting; /c x, /r x, /t x print usage: /clear, /resume, /triage; /t and /d print the needs the TUI message; /quit ends the session.
- **Actual result:** stderr: usage: /quit, usage: /exit, usage: /clear, usage: /resume, usage: /triage. stdout: '/triage needs the TUI; run `uncle` without --noui.' and '/do needs the TUI; run `uncle` without --noui.' The session kept reading after each error and ended on /quit with exit code 0.
- **Defects:** None

### MC-200

- **Action:** Ran the worktree's ./uncle --noui (UNCLE_RUNTIME_ROOT set to the worktree) with piped input: /frob, /qu, /x, /, /?, /1, /help, /quit.
- **Expected result:** Each of the first six lines prints 'unknown command: /<name>' plus the Commands line on stderr and is not run; the session keeps reading; /help still prints help; /quit ends the session.
- **Actual result:** stderr had six 'unknown command: /frob', '/qu', '/x', '/', '/?', '/1' messages, each followed by the Commands line. stdout showed the /help output (Type a message to chat... Commands: ...). /quit ended the session. The process exit code was 2, presumably because refusals occurred; the checklist does not specify an exit code.
- **Defects:** None

### MC-201

- **Action:** Piped '/s', '/s foo', '/mode', '/quit' into the worktree REPL (UNCLE_NOUI=1 python3 scripts/lib/uncle_repl.py), which is the code `uncle --noui` execs. The `uncle` launcher in this shell honors UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec (installed build without the change, printed 'unknown command'), so it was bypassed.
- **Expected result:** /s and /s foo print 'ambiguous command' naming /stop and /settings, no 'unknown command'; /mode still processed; exit code 2; no raw escape bytes.
- **Actual result:** Both /s and /s foo printed 'ambiguous command: /s (matches: /settings, /stop)'. No 'unknown command'. /mode printed 'mode: attended' afterwards. Exit code 2. Output viewed with cat -v showed no escape bytes. The launcher was not exercised against the worktree code.
- **Defects:** None

### MC-202

- **Action:** Piped '/q now','/e foo','/mode','/q','/mode' into the worktree REPL, then '/Q','/mode' in a separate session (same direct-REPL invocation, bypassing the installed-runtime launcher).
- **Expected result:** /q now prints 'usage: /quit'; /e foo prints exit usage; neither quits; first /mode prints; bare /q quits so the final /mode is never processed; /Q quits and its /mode output never appears.
- **Actual result:** Printed 'usage: /quit' and 'usage: /exit'; first /mode printed 'mode: attended'; after /q exactly one mode line appeared (second not processed), exit 0. In the /Q session no mode output appeared, exit 0.
- **Defects:** None

### MC-203

- **Action:** Piped the MC-203 line sequence (/m unattended, /m, /h, /i, /i x, /issue, /c x, /clear x, /r x, /t, /t x, /d, /triage, /do, /quit) into the worktree's scripts/lib/uncle_repl.py (the --noui REPL module) in a scratch dir; also ran '/triage x' and '/clear x' for full-name comparison.
- **Expected result:** /m unattended sets and reports unattended; /m reports it; /h prints help; each shortcut equals its full-name output; /i and /issue both print 'usage: /issue N'; /c x, /r x, /t x print the full-name usage lines; /t and /d print the same needs-the-TUI message as /triage and /do.
- **Actual result:** /m unattended -> 'mode: unattended'; /m -> 'mode: unattended'; /h -> help text; /i, /i x, /issue -> 'usage: /issue N'; /c x and /clear x -> 'usage: /clear'; /r x -> 'usage: /resume'; /t and /d -> '/triage needs the TUI...' and '/do needs the TUI...' identical to /triage and /do; /t x -> 'usage: /triage' identical to '/triage x'; /quit exit 0. Note: the literal text printed for '/issue' is 'usage: /issue N' (checklist abbreviates as 'usage: /issue').
- **Defects:** None

### MC-204

- **Action:** Piped '/<ESC>', '/\u00e9' (UTF-8), '/s', '/quit' into the worktree's scripts/lib/uncle_repl.py; inspected output with cat -v and od -c for ESC (033) bytes.
- **Expected result:** Escape and non-ASCII names refused as unknown commands, no crash, no raw escape sequences emitted, session continues.
- **Actual result:** 'unknown command: /' (ESC stripped) and 'unknown command: /é' were printed, each followed by the command list; '/s' printed 'ambiguous command: /s (matches: /settings, /stop)'; no crash. Zero ESC bytes in output (od -c grep for 033 count 0; cat -v showed no ^[). Session continued through all lines. Process exit status was 2 (likely due to the refused lines; the checklist does not constrain it).
- **Defects:** None

### MC-301

- **Action:** Ran the worktree's scripts/lib/uncle_repl.py (the --noui REPL entry point) in a scratch git dir with piped stdin '/q\n/help\n', capturing stdout, stderr and exit status. The installed `uncle` binary is a separate Homebrew build, so it was not used.
- **Expected result:** Session ends on /q with exit code 0; the following /help line is never processed (no help output).
- **Actual result:** Exit code 0. Stdout contained only the startup banner ('uncle --noui interactive session. Type /help for commands, /quit to exit.'); no help listing was printed after /q. Stderr empty.
- **Defects:** None

### MC-302

- **Action:** Ran the worktree's scripts/lib/uncle_repl.py in a scratch git dir with piped stdin '/s\n/s foo\n/mode\n/quit\n', capturing stdout and stderr to separate files plus the exit code.
- **Expected result:** Both /s and /s foo print 'ambiguous command: /s (matches: /settings, /stop)' on stderr without 'unknown command'; session keeps running so /mode prints the mode; /quit ends the session.
- **Actual result:** Stderr had the line 'ambiguous command: /s (matches: /settings, /stop)' twice, with no 'unknown command' text. Stdout showed the banner then 'mode: attended', so the session continued past both ambiguous inputs, and /quit ended it. The process exit code was 2, because refuse() sets the session code to 2 after a refusal (uncle_repl.py:139-141). The check does not specify an exit code.
- **Defects:** None

### MC-303

- **Action:** Piped '/m unattended', '/m', '/h', '/i', '/t', '/d', '/quit' into the worktree's `uncle --noui` with UNCLE_RUNTIME_ROOT set to the worktree (the ambient UNCLE_RUNTIME_ROOT pointed at the stale /opt/homebrew/opt/uncle/libexec install, which printed 'unknown command: /m'; that was an environment issue, not a worktree defect). Output captured through cat -v.
- **Expected result:** /m unattended prints 'mode: unattended'; /m reports unattended; /h prints help; /i prints 'usage: /issue'; /t and /d print 'needs the TUI' messages.
- **Actual result:** Output: 'mode: unattended', 'mode: unattended', help text (with Commands line), 'usage: /issue N', '/triage needs the TUI; run `uncle` without --noui.', '/do needs the TUI; run `uncle` without --noui.'. Session ended on /quit. No raw escape characters. Shell exit code was not captured (PIPESTATUS read empty in zsh).
- **Defects:** None

### MC-304

- **Action:** Piped '/qu', '/frob', '/x', '/?', '/1', '/', '/q now', '/mode', '/Q', then a trailing '/mode' into the worktree's `uncle --noui` (UNCLE_RUNTIME_ROOT set to the worktree). Output captured through cat -v.
- **Expected result:** First six print 'unknown command: /<name>' plus the Commands line, no crash or raw escapes; '/q now' prints 'usage: /quit' and does not quit; '/mode' is still processed; '/Q' quits.
- **Actual result:** 'unknown command: /qu', '/frob', '/x', '/?', '/1', '/' each printed followed by the Commands line (filtered from the final view, seen in the earlier run). '/q now' printed 'usage: /quit' and the session continued. '/mode' printed 'mode: attended'. '/Q' quit: the trailing '/mode' after it produced no output. No crash and no escape characters. Shell exit code was not captured (PIPESTATUS read empty in zsh).
- **Defects:** None

### MC-401

- **Action:** Ran scripts/lib/uncle_repl.py (the --noui session module) via piped stdin in three sessions: (1) '/quit' then '/help'; (2) '/help' then '/exit' then '/help'; (3) covered by (1) as the quit-then-help case. The `uncle` wrapper was not launched; the REPL module was driven directly.
- **Expected result:** /quit and /exit end the session with later lines unread; /help prints help text in a session that continues.
- **Actual result:** Session 1: /quit ended with rc=0 and the later /help printed nothing (only the banner). Session 2: first /help printed help text and the session continued; /exit ended it with rc=0 and the trailing /help was unread (help text appeared once only).
- **Defects:** None

### MC-402

- **Action:** Piped '/frob /qu /x / /? /1 /help /quit' (one per line) into scripts/lib/uncle_repl.py, captured stdout, stderr and exit code separately.
- **Expected result:** Each unmatched name prints 'unknown command: /<name>' followed by the Commands line, nothing is executed, the session keeps reading, and the process exit code is 2.
- **Actual result:** All six unmatched names produced 'unknown command: /<name>' plus the Commands line on stderr; the session continued, /help then printed help on stdout, /quit ended it, and the exit code was 2.
- **Defects:** None

### MC-403

- **Action:** Piped '/mode unattended','/mode','/mode attended','/mode bogus','/issue','/issue abc' into scripts/lib/uncle_repl.py (the --noui REPL entry) from a scratch dir and read the transcript.
- **Expected result:** Mode set and echoed; /mode bogus prints usage: /mode ...; /issue and /issue abc print usage: /issue.
- **Actual result:** Output: 'mode: unattended', 'mode: unattended', 'mode: attended', 'usage: /mode [attended|unattended]', 'usage: /issue N', 'usage: /issue N'. Matches expectation.
- **Defects:** None

### MC-405

- **Action:** Piped '/q now','/e foo','/c x','/r x','/t x','/h','/q','/help' into scripts/lib/uncle_repl.py and read the transcript.
- **Expected result:** Argument forms print usage: /quit,/exit,/clear,/resume,/triage and do not quit; /h prints help; bare /q ends the session and final /help is not processed.
- **Actual result:** Output printed usage: /quit, usage: /exit, usage: /clear, usage: /resume, usage: /triage, then help text once (from /h). After /q the session ended with exit code 0; there was only one help output, so the trailing /help was not processed.
- **Defects:** None

### MC-406

- **Action:** Ran the real scripts/lib/uncle_repl.py (the --noui REPL) with piped stdin in two sessions. Session 1 input: /Q. Session 2 input: /m unattended, /m, /i, /t, /d, /q.
- **Expected result:** /Q quits like /q; /m unattended sets and echoes mode unattended; /m shows the mode; /i prints usage: /issue; /t and /d print the needs-the-TUI messages for /triage and /do.
- **Actual result:** Session 1: /Q exited cleanly with exit=0. Session 2: '/m unattended' printed 'mode: unattended'; '/m' printed 'mode: unattended'; '/i' printed 'usage: /issue N'; '/t' printed '/triage needs the TUI; run `uncle` without --noui.'; '/d' printed '/do needs the TUI; run `uncle` without --noui.'; exit=0. Note: the driver ran a piped, non-tty session, not a human-typed one.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Transcript: OUT=banner only; ERR=empty; rc=0. Running scripts/lib/uncle_repl.py directly gave the same result (rc=0, no 'after' output). |
| MC-102 | YES | PASS | Transcript: ERR2='ambiguous command: /s (matches: /settings, /stop)'; OUT2=banner + 'mode: attended'; rc2=2. |
| MC-103 | YES | PASS | Terminal transcript captured with cat -v; exit code 0. An earlier run against the installed Homebrew runtime (UNCLE_RUNTIME_ROOT inherited from the environment) printed 'unknown command: /m'. That run exercised the old build, not the worktree, so it is not counted. |
| MC-104 | YES | PASS | cat -v transcript; `grep -c ESC` returned 0; exit=2 after the refusals. |
| MC-105 | YES | PASS | Captured transcripts /tmp/o1 (stdout) and /tmp/e1 (stderr), rc=0. Source: scripts/lib/uncle_repl.py slash() single-letter expansion. Note: with the ambient UNCLE_RUNTIME_ROOT=/opt/homebrew/opt/uncle/libexec (installed older build) the same input gave 'unknown command: /q' etc.; that is a stale install, not the change under test. |
| MC-200 | YES | PASS | Captured transcripts /tmp/o2 (stdout) and /tmp/e2 (stderr), rc=2. |
| MC-201 | YES | PASS | exit=2; transcript: 'ambiguous command: /s (matches: /settings, /stop)' x2, then 'mode: attended'. |
| MC-202 | YES | PASS | Session 1 output: usage: /quit / usage: /exit / mode: attended. Session 2 output: banner only. |
| MC-203 | YES | PASS | Transcript captured in the scratch dir (o203.txt); exit=0; '/triage x' printed 'usage: /triage' and '/clear x' printed 'usage: /clear'. Ran the worktree module directly rather than the installed /opt/homebrew/bin/uncle. |
| MC-204 | YES | PASS | o204.txt in scratch dir; cat -v output showed no ^[ sequences; od -c / grep -c '033' = 0. |
| MC-301 | YES | PASS | exit1=0; OUT1 had only the banner line; ERR1 empty. |
| MC-302 | YES | PASS | exit2=2; OUT2: banner + 'mode: attended'; ERR2: two identical ambiguity lines. |
| MC-303 | YES | PASS | Transcript above from `printf ... / UNCLE_RUNTIME_ROOT=<worktree> <worktree>/uncle --noui / cat -v`; matched by running scripts/lib/uncle_repl.py directly. |
| MC-304 | YES | PASS | Transcript from the cat -v pipeline. The Commands lines were removed with grep -v in the final run; the direct run of uncle_repl.py showed them in full. |
| MC-401 | YES | PASS | stdout for '/quit\n/help\n' = banner only, rc=0. stdout for '/help\n/exit\n/help\n' = banner + one help block ('Type a message to chat...' and 'Commands: /help /mode ...'), rc=0. Note: a bare '/exit' session with no preceding line was not run separately; /exit was exercised as the second line of session 2. |
| MC-402 | YES | PASS | stderr: 'unknown command: /frob', '/qu', '/x', '/', '/?', '/1', each followed by 'Commands: /help /mode [attended/unattended] /issue N /stop /resume /clear /triage /do /settings /quit'. stdout contained the banner and the help text from /help. rc=2. |
| MC-403 | YES | PASS | Transcript captured from python3 scripts/lib/uncle_repl.py with piped stdin; exit code 0. Ran the REPL module directly rather than the uncle wrapper script. |
| MC-405 | YES | PASS | Transcript from python3 scripts/lib/uncle_repl.py with piped stdin: exactly one help block (two lines) and rc=0. Ran the REPL module directly rather than the uncle wrapper script. |
| MC-406 | YES | PASS | Transcript: S1 banner then exit=0. S2: banner, 'mode: unattended', 'mode: unattended', 'usage: /issue N', '/triage needs the TUI; run `uncle` without --noui.', '/do needs the TUI; run `uncle` without --noui.', exit=0. |
