# Baseline Report

Omitted sections: Reproduction (not a bug); Existing failures (none documented; driver baseline is authority)

## 1. Change-request summary
Issue 168 (.uncle/docs/CHANGE_REQUEST.md): in `--noui`, a single-character slash command expands to the one command with that prefix; ambiguous `/s` refused with candidates; `/qu` stays unknown.

## 2. Repository architecture
Shell workflow drivers in `scripts/`, Python REPL in `scripts/lib/uncle_repl.py`, tests in `scripts/tests/*-test.py` (custom `check()` scripts, hyphenated names), runners `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh`.

## 3. Relevant code paths
- `scripts/lib/uncle_repl.py:212-234` `Session.slash()`: one-letter expansion block (lines 216-226) over `USAGE` keys plus quit/exit, then quit/exit handling, then unknown-command refusal.
- `scripts/lib/uncle_repl.py:~14-32` `USAGE` dict and `HELP` text.
- `scripts/tests/repl-session-test.py:145-160` (AC-2/3/4 checks) and `:555-575` (full a-z map pin).

## 4. Current observable behavior
The working tree already contains the requested feature (HEAD 73c9097 "expand one-character slash commands when the prefix is unique", +11 lines in uncle_repl.py, +82 in repl-session-test.py).

| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `/q` | quits (rc 0) | uncle_repl.py:216-231 | Yes |
| B-2 | `/h /m /i /c /t /d /e /r` | expand to full command, args kept | uncle_repl.py:221-223; test :145-152, :555-568 | Yes |
| B-3 | `/s` | refused rc 2: `ambiguous command: /s (matches: /settings, /stop)` | uncle_repl.py:225; test :153-155 | Yes |
| B-4 | `/qu`, `/frob`, `/x` | `unknown command: /<name>` rc 2 | uncle_repl.py:232-234; test :156-159 | Yes |
| B-5 | bare `/`, `/?`, non-ASCII | unknown, session continues | test :130-132, :598 | Yes |
| B-6 | `/quit extra` | usage complaint | uncle_repl.py:228-230 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Only 1-char ASCII a-z names expand | uncle_repl.py:216 | map pin :555-572 | High |
| I-2 | Ambiguous/unmatched never runs a command; rc 2 | uncle_repl.py:224-226,232-234 | :153-159 | High |
| I-3 | All output passes the escape filter (`Out`) | uncle_repl.py:35+ | :598 | High |

## 6. Interface contracts
CLI `uncle --noui` stdin slash lines; exit codes 0 quit, 2 refusal. No API/schema changes.

## 7. Existing automated-test coverage
`repl-session-test.py` covers all rows above. The shell suite and the Python suite use separate temp dirs and no shared ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (both exist). Not executed here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
None required: feature and tests already present. At most `HELP` text (uncle_repl.py:30-32).

## 13. Regression-sensitive components
TUI slash handling (out of scope); HELP text pinned by tests; escape filtering.

## 14. Outside the change
TUI slash handling, longer abbreviations, workflow shell scripts.

## 15. Unknowns and assumptions
- ASSUMPTION: the existing HEAD commit is the intended implementation; this change verifies and, if gaps exist, closes them.
- UNKNOWN: whether CHANGE_REQUEST.md's "update HELP if useful" is wanted; treated as optional.

## 16. Risk
Low. Risk of redundant or conflicting edits since the feature already exists.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

