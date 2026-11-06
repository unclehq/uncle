# Baseline Report (Issue 168)

Omitted sections: Reproduction (feature, not bug); Schema contracts (none)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md: in `uncle --noui`, a one-character slash command whose first letter matches exactly one command should run that command.

## 2. Repository architecture
Shell driver plus Python libs. The --noui REPL is `scripts/lib/uncle_repl.py`; tests in `scripts/tests/repl-session-test.py` (subprocess-driven via `session()`, line ~52).

## 3. Relevant code paths
- `scripts/lib/uncle_repl.py:~15-29` USAGE dict (keys: help, mode, issue, stop, resume, clear, triage, do, settings, and quit/exit - `USAGE[name]` is used at line 218).
- `uncle_repl.py:30-32` HELP text.
- `uncle_repl.py:212-262` `slash()`: lowercases name, handles quit/exit, refuses names not in USAGE (line 221-223, via `self.refuse`, exit code 2), dispatches by name.
- `uncle_repl.py:264-269` `handle()` routes lines starting with `/` to `slash()`.
- Tests: `repl-session-test.py:111-118` slash tests incl. `/frob` unknown -> rc 2.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | `/quit` or `/exit` | session ends, later lines unread | test line 117 | Yes |
| B2 | `/frob` | stderr `unknown command: /frob` + commands line, rc 2 | test line 118 | Yes |
| B3 | `/q`, `/h`, `/m` etc. | refused as unknown | uncle_repl.py:221 | No (modified) |
| B4 | `/mode unattended` | sets mode | uncle_repl.py:229 | Yes |
| B5 | `/qu` | refused as unknown | uncle_repl.py:221 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Unmatched slash command refused with rc 2 | slash() line 221 | repl-session-test.py:118 | High |
| I2 | All REPL output passes the escape filter | Out class | other tests | Medium |
| I3 | Per-command arg validation via USAGE | slash() branches | line 112-116 | High |

## 6. Interfaces
Stdin lines in; stdout/stderr and exit code out. No API/schema.

## 7. Existing test coverage
Python suite `repl-session-test.py` covers slash commands. Shell and Python runners use separate temp dirs and no shared ports, so they may run in parallel.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (Uncle runners, per workflow instructions). No results run here; the driver's baseline supplies them. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`uncle_repl.py` slash() (and HELP optionally); `repl-session-test.py`.

## 13. Regression-sensitive components
quit/exit handling; unknown-command refusal; `self.refuse` exit code.

## 14. Outside the change
TUI slash handling; multi-character abbreviations; other scripts.

## 15. Unknowns
Exact content of USAGE keys beyond line 25-29 assumed to include quit/exit (inferred from line 218); verify at implementation.

## 16. Risk
Low. Main risk: prefix matching accidentally accepting longer abbreviations or mis-ordering the ambiguous list.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

