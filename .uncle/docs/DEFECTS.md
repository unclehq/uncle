# Defects

## Observed defect: ./uncle --noui exits 2 on /q or /quit after an earlier refusal; expected 0. Not yet logged in DEFECTS.md (worker may not edit it).

- **Status:** FAIL
- **Evidence:** Transcript: 'ambiguous command: /s (matches: /settings, /stop)' x3, then the help line, then exit status 2 (`echo $?` after the run). Source comment at scripts/lib/uncle_repl.py:387 says an explicit /quit after a refusal should return 0, but via ./uncle --noui the status was 2. Same exit 2 for '/x' then '/quit' and for '/h', '/x', '/q'.
- **Expected result:** Each of /s, /s extra, /S prints 'ambiguous command: /s (matches: /settings, /stop)' and runs nothing; /h shows help; /q exits with status 0.
- **Actual result:** The three refusals printed exactly 'ambiguous command: /s (matches: /settings, /stop)', nothing ran, and /h printed help. But after the refusals, /q exited with status 2, not 0. A lone '/q' or '/quit' exits 0. Running python3 scripts/lib/uncle_repl.py directly with '/x' then '/q' exited 0, so the 2 comes from running through ./uncle. I did not find the cause.

## Same defect as MC-200: exit status 2 after /q following refusals, expected 0.

- **Status:** FAIL
- **Evidence:** Transcript: 'unknown command: /qu', '/x', '/1', '/?' and '/', each followed by the Commands line. `echo $?` printed 2.
- **Expected result:** Each of /qu, /x, /1, /?, / is refused as an unknown command, nothing expands or runs, and /q exits with status 0.
- **Actual result:** All five were refused with 'unknown command: /<token>' followed by the Commands line, and nothing ran or expanded. The session continued to /q, but the final exit status was 2, not 0.

## Unrecorded: exit status 2 instead of 0 after /q following refusals when launched via ./uncle --noui (module-direct run returns 0)

- **Status:** FAIL
- **Evidence:** Transcript in /tmp/mc402.txt; `printf '/qu\n/frob\n/x\n/\n/?\n/1\n/q\n' | ./uncle --noui` -> exit=2; `printf '/frob\n/quit\n' | ./uncle --noui` -> exit=2; same input to python3 scripts/lib/uncle_repl.py -> exit=0.
- **Expected result:** First six each print 'unknown command: /<name>' with refusal status 2, nothing expands, session stays open until '/q' quits with exit status 0.
- **Actual result:** All six printed 'unknown command: /qu', '/frob', '/x', '/', '/?', '/1' (followed by the command list) and nothing expanded; session stayed open and /q quit silently. However the final process exit status was 2, not 0. '/q' alone exits 0. '/frob' then '/quit' via ./uncle also exits 2. Running scripts/lib/uncle_repl.py directly (also with UNCLE_NOUI=1) with '/frob' then '/quit' exits 0, so the code comment 'explicit /quit is a clean exit' holds in the module but not via the ./uncle --noui launcher path; cause not determined.

## New: bare /q (or /quit) after an ambiguous slash command exits with status 2 instead of 0 (last-command status leaks into quit exit code). Not recorded in DEFECTS.md by this worker.

- **Status:** FAIL
- **Evidence:** Transcript: 'ambiguous command: /s (matches: /settings, /stop)' x3, 'usage: /quit', EXIT=2. Isolation runs: '/s\n/q' EXIT=2; '/s\n/quit' EXIT=2; '/q' EXIT=0.
- **Expected result:** First three print exactly `ambiguous command: /s (matches: /settings, /stop)`, run nothing. `/q extra` prints `usage: /quit` and does not quit. Bare `/q` then quits with exit status 0.
- **Actual result:** Output matched for the first three (identical ambiguous line x3) and `/q extra` printed `usage: /quit` without quitting; session then quit on `/q`. But the process exit status was 2, not 0. Isolation: '/q' alone -> 0; '/q extra' then '/q' -> 0; any prior ambiguous command ('/s' then '/q' or '/quit') -> exit 2. The ambiguous status 2 is carried into the final exit code of the quit.
