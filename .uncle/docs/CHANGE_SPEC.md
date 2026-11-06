# Change Spec: Issue 168

Omitted sections: Performance, Security (no change), Migration, Prototype isolation (n/a)

## 1. Change type
Feature.

## 2. Problem
`--noui` refuses `/q` though only one command starts with `q`.

## 3. Current behavior
See baseline B-1..B-6: the working tree already implements expansion.

## 4. Desired behavior
One-character slash names expand to the unique command with that prefix among help, quit, exit, mode, issue, stop, resume, clear, triage, do, settings; ambiguous or unmatched keep refusal rc 2; ambiguous names candidates.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | `/q` | quits (already) | runs /quit, rc 0 | repl-session-test |
| SB-2 | ADD | `/h /m /i /c /t /d /e /r` | expand (already) | run the mapped command | map pin test |
| SB-3 | ADD | `/m unattended` | args kept | same as `/mode unattended` | test :145ff |
| SB-4 | ADD | `/s` | refused naming matches | not run, rc 2, lists /settings, /stop | test :153 |
| SB-5 | PRESERVE | `/qu`, `/frob`, `/`, `/?` | unknown, rc 2 | unchanged | test :156-159 |
| SB-6 | PRESERVE | full command names | work | unchanged | existing suite |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | Only 1-char a-z names expand | uncle_repl.slash | uncle_repl.py:216 | map pin a-z |
| SI-2 | EXISTING | Ambiguous/unmatched never executes; rc 2 | slash | uncle_repl.py:224-234 | AC-3/4 tests |
| SI-3 | EXISTING | Output escape-filtered | REPL | Out class | :598 test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Full command names and arguments unchanged.

## 8. Error behavior
Ambiguous: `ambiguous command: /s (matches: /settings, /stop)`, rc 2. Unmatched: `unknown command: /x`, rc 2.

## 12. Rollback
Revert commit 73c9097 changes to the two files.

## 14. Non-goals
TUI slash handling; abbreviations longer than one character.

## 15. Assumptions
Existing implementation satisfies the request; HELP edit optional.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `/q` in --noui quits the session with rc 0. | repl-session-test.py check for /q |
| AC-2 | `/h /m /i /c /t /d /e /r` each run help, mode, issue, clear, triage, do, exit, resume, and arguments are preserved (`/m unattended` == `/mode unattended`). | repl-session-test.py AC-2 and map-pin checks |
| AC-3 | `/s` is not run, exits rc 2, and the message names /settings and /stop. | repl-session-test.py AC-3 checks |
| AC-4 | `/qu`, unmatched letters, `/`, and `/?` remain unknown commands with rc 2. | repl-session-test.py AC-4 and map-pin checks |
| AC-5 | The shell and Python regression suites show no regression versus baseline. | bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh |

