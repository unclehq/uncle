# Implementation notes

### Files changed

- `scripts/tests/repl-session-test.py` — Adds a-z map pin, /Q /S case checks, /q|/e with args, /s extra, /1, ESC-filter, paired /i /t /d /c /r equivalence and stubbed-execute payload tests; fixes /q extra and /e extra assertions (usage is a complaint, final rc is the later /mode's 0, so rc==2 was wrong).; Test strategy 16-17; SB-1..SB-5, SI-1, SI-2, SI-3
- `scripts/lib/uncle_repl.py` — No source change; expansion in Session.slash already implements the feature. Mutated temporarily for defect injection and restored byte-for-byte (cmp verified).; Section 1; SI-1, SI-2

### Unresolved concerns

- Plan states both alphabetical (/settings, /stop) and USAGE order for ambiguity candidates; code and tests use alphabetical (R-2/AR-019).
- Full shell and python suites are left to the driver.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | scripts/lib/uncle_repl.py slash() expands /q to quit (pre-existing); tests in repl-session-test.py | python3 scripts/tests/repl-session-test.py exit 0, no FAIL lines |
| AC-2 | IMPLEMENTED | Map-pin loop over a-z, /m unattended check, /i vs /issue, /t,/d equivalence, /c,/r payload equality in repl-session-test.py | same command exit 0; mutant disabling unique-prefix expansion produced 30 FAIL lines |
| AC-3 | IMPLEMENTED | Tests assert '/s' and '/S' give 'ambiguous command: /s (matches: /settings, /stop)', rc 2, not run | exit 0; mutants removing sorted() gave 3 FAIL lines, removing lower() gave 2 |
| AC-4 | IMPLEMENTED | Tests for /qu, /frob, /, /?, /1, ESC-bearing and non-ASCII names, and 16 unmatched letters | exit 0, no FAIL lines |
| AC-5 | IMPLEMENTED | No source change; only the test file was extended | Full suites are driver-run (DRIVER PENDING); repl-session-test.py passes standalone |
