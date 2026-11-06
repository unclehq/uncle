# Change Spec (Issue 168)

Omitted sections: Performance, Security, Migration, Prototype isolation (not applicable)

## 1. Change type
Feature.

## 2. Problem
In `--noui`, `/q` is refused though only one command starts with `q`.

## 3. Current behavior
See baseline B2, B3.

## 4. Desired behavior
A slash command whose name is exactly one character expands to the single command starting with that character; ambiguous or unmatched stays refused (rc 2), ambiguous names its candidates. Arguments preserved.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S1 | MODIFY | `/q` | unknown, rc 2 | quits like /quit | repl-session-test |
| S2 | MODIFY | `/h /m /i /c /t /d /e /r` | unknown | run help, mode, issue, clear, triage, do, exit, resume | repl-session-test |
| S3 | MODIFY | `/s` | unknown | refused, rc 2, message lists stop and settings, nothing run | repl-session-test |
| S4 | PRESERVE | `/qu`, `/frob`, `/x` | unknown, rc 2 | unchanged | repl-session-test |
| S5 | MODIFY | `/m unattended` | unknown | acts as `/mode unattended` | repl-session-test |
| S6 | MODIFY | `/i` without N | unknown | usage error for /issue | repl-session-test |
| S7 | PRESERVE | full-name commands | works | unchanged | existing tests |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V1 | EXISTING | Unmatched slash commands refused with rc 2 | REPL | slash() | existing + new test |
| V2 | NEW | Only single-character names expand; never ambiguous prefixes | REPL | slash() | /qu, /s tests |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Full-name commands unchanged.

## 8. Errors
Ambiguous: stderr message naming candidates, rc 2, no command executed.

## 14. Non-goals
TUI slash handling; longer abbreviations; new commands.

## 15. Assumptions
Candidate set is the REPL's known command names (including quit/exit). Help text update is optional.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `/q` quits the session and later lines are not processed. | New check in scripts/tests/repl-session-test.py |
| AC-2 | Unique one-character commands (h,m,i,c,t,d,e,r) run the matching command; arguments are preserved (`/m unattended` sets unattended mode). | New checks in repl-session-test.py |
| AC-3 | `/s` is not run, exits rc 2 and the stderr message names both stop and settings. | New check in repl-session-test.py |
| AC-4 | `/qu` and `/frob` remain refused with `unknown command` and rc 2. | New check for /qu plus existing /frob check |
| AC-5 | Existing shell and Python suites show no new regressions versus baseline. | Driver verification commands |

