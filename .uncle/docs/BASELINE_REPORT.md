# Baseline Report

Omitted sections: Reproduction result (not a crash bug; reproduction is the PATH scan itself); API/schema contracts (none touched); Flaky behavior (none documented)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md: with no claude/codex/kimi/opencode on PATH, runner choices and default must be only `self-hosted`.

## 2. Repository architecture
Single-module TUI `uncle_tui.py` (large; grep only) plus shell drivers and `scripts/tests/*-test.py` / shell suites.

## 3. Relevant code paths
- `uncle_tui.py:690` `runners_for(side)`: scans PATH for claude, codex, kimi, opencode (opencode maps to self-hosted); returns list. `side` is unused.
- `uncle_tui.py:1196-1212` `stage_runner`: configured value wins, then DEFAULT_RUNNER, else `installed[0]` or "".
- `uncle_tui.py:1441` description text lists `runners_for(side)`.
- `uncle_tui.py:1459-1464` `_picker_rows` runner picker (supervision picker filters by `supervision_lib.SUPPORTED_RUNNERS`).
- `uncle_tui.py:1527-1529` second consumer of `runners_for`.
- `uncle_tui.py:1297` shows "No agents installed" when default is empty.
- `uncle_tui.py:7427` renders `self-hosted` as "Self hosted".

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | PATH has >=1 of the four binaries | list holds installed runners in fixed order claude, codex, kimi, self-hosted(opencode) | uncle_tui.py:692-709 | Yes |
| B2 | PATH has none | `runners_for` returns [], picker empty, `stage_runner` returns "" | uncle_tui.py:1211-1212 | No (this change) |
| B3 | Saved/explicit runner or DEFAULT_RUNNER set | used regardless of discovery | uncle_tui.py:1197-1210 | Yes |
| B4 | Unreadable/non-executable PATH entry | stderr diagnostic, entry skipped | uncle_tui.py:697-706 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Only supported runner names are returned/selected | fixed binary tuple and stage_runner whitelist | none found targeting runners_for | Medium |
| I2 | Configured runner overrides discovery | stage_runner order | none found | Medium |

## 7. Existing automated-test coverage
No test references `runners_for` or "No agents installed" (grep of scripts/). Python suites import uncle_tui in e.g. scripts/tests/home-actions-test.py. Shell and Python runners use separate temp dirs and no shared ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (existence verified). Not executed here; the driver baseline is authoritative (.uncle/workflow/green-check.baseline.tsv). Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`uncle_tui.py` `runners_for`; one new `scripts/tests/*-test.py`.

## 13. Regression-sensitive components
runner picker, stage default, supervision picker (filters by SUPPORTED_RUNNERS), config description, status display.

## 14. Outside the change
Self-hosted configuration flow, shims, other runners, DEFAULT_RUNNER semantics.

## 15. Unknowns and assumptions
- Whether `supervision_lib.SUPPORTED_RUNNERS` contains self-hosted (not checked; supervision picker may legitimately stay filtered).
- Assumption: a fallback inside `runners_for` is acceptable for every caller.

## 16. Initial risk assessment
Low. Single small function; main risk is a caller that treats empty list as 'nothing installed' (line 1297 label becomes unreachable).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

