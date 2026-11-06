# Implementation notes

### Files changed

- `scripts/lib/uncle_repl.py` — In Session.slash, expand a single a-z character name to the unique command (USAGE keys plus quit/exit) starting with it; ambiguous names refuse via self.refuse naming candidates (rc 2, session continues); unmatched stays unknown.; one-character expansion before quit/exit branch; S1-S6, V1, V2
- `scripts/tests/repl-session-test.py` — Added checks for /q, /h /m /i /e /c /t /d /r, /s ambiguity, /qu and /frob refusal, /Q, bare /, /?, /q with args.; test strategy; AC-1..AC-4, V2

### Unresolved concerns

- repl-session-test.py at repo root is in the frozen list but does not exist; only scripts/tests/repl-session-test.py was changed.
- Full shell/python suites left to the driver.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | scripts/lib/uncle_repl.py slash(): /q -> quit | python3 scripts/tests/repl-session-test.py: 'AC-1 /q quits; later /mode not processed' ok |
| AC-2 | IMPLEMENTED | scripts/lib/uncle_repl.py slash(): unique letters expand, args preserved | AC-2 checks for h,m,i,e,c,t,d,r ok (102 ok, 0 failures) |
| AC-3 | IMPLEMENTED | scripts/lib/uncle_repl.py slash(): ambiguous refusal listing /settings and /stop | 'AC-3 /s refused rc 2 naming stop and settings' ok |
| AC-4 | IMPLEMENTED | unchanged unknown-command path for multi-char names | AC-4 /qu and /frob checks ok |
| AC-5 | IMPLEMENTED | No other source changed | Targeted suite passes; full shell/python suites are run by the driver (DRIVER PENDING) |
