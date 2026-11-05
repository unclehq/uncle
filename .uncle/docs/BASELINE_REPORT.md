# Baseline Report

Omitted sections: Reproduction (feature, not bug); Areas outside change folded into section 12

## 1. Change-request summary
CHANGE_REQUEST.md (Issue 158): housekeeping must be startable while a build is in progress, without altering build inputs, results or the working tree under build.

## 2. Repository architecture
Bash drivers in `scripts/` (workflow.sh, change-workflow.sh, housekeeping-workflow.sh) launched by `uncle` (launcher) or by the Python TUI `uncle_tui.py` as one subprocess `self.proc`. Housekeeping = one free-form claude agent run with a deny list (`scripts/lib/housekeeping_config.py`, prompt `prompts/housekeeping-plan.md`).

## 3. Relevant code paths
- `scripts/housekeeping-workflow.sh:60-83`: takes exclusive non-blocking flock on `.uncle/workflow/driver.lock` (shared with builds) and writes `.uncle/workflow/mode` (shared build state).
- `scripts/housekeeping-workflow.sh:~84`: `rm -f` of own files in `.uncle/workflow/housekeeping/`.
- `uncle_tui.py:6042-6045`: `/housekeeping` refused when `self.state=='running'` or `self.proc` alive ("A workflow is already active").
- `uncle_tui.py:1567-1592`: `cmd_for`, `_start_housekeeping` (uses `self._run`, which sets `self.proc`).
- `uncle_tui.py:2195-2210`: `_run` Popen; `uncle_tui.py:2007+`: `_poll_workflow`; poll called at 2248, 2916, 2919.
- `uncle:70-260`: `--housekeeping` startup option (runs via TUI startup action, `uncle_tui.py:4134`).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `/housekeeping TEXT` while a build runs | Refused: 'A workflow is already active...' | uncle_tui.py:6042; tui-housekeeping-test.py:51 | No (MODIFY) |
| B-2 | `housekeeping-workflow.sh` while build holds driver.lock | Exits 1 'another workflow holds this checkout' | housekeeping-workflow.sh:62-66 | No (MODIFY) |
| B-3 | Housekeeping run writes `.uncle/workflow/mode` | Overwrites mode file read by the build driver | housekeeping-workflow.sh:78-82 | No (MODIFY) |
| B-4 | `/housekeeping TEXT` when idle | Starts driver as foreground workflow via `_run` | tui-housekeeping-test.py:34-41 | Yes |
| B-5 | `uncle --housekeeping TEXT` | Startup action runs housekeeping | uncle:246; tui test:58 | Yes |
| B-6 | Deny list / empty request / REFUSED states / REPORT.md | Enforced per script | housekeeping-workflow-test.sh | Yes |
| B-7 | Two housekeeping runs at once | Second refused via driver.lock | housekeeping-workflow.sh:62 | Yes (must still refuse) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | At most one housekeeping run per checkout | driver.lock flock | housekeeping-workflow-test.sh (partial) | Medium |
| I-2 | Deny list applies to every run | `--disallowedTools` from floor+config | housekeeping-policy-test.py | High |
| I-3 | Housekeeping records confined to `.uncle/workflow/housekeeping/` (except mode file) | script | none explicit | Low |
| I-4 | Only one build/workflow per checkout | driver.lock in workflow drivers; TUI guard | tui tests | Medium |

## 6. Interface contracts
CLI: `housekeeping-workflow.sh [--attended|--unattended] [TEXT]`, exit 0 done/declined, 1 otherwise. TUI slash `/housekeeping TEXT`. State file `.uncle/workflow/housekeeping/state` (STARTED, RUNNING, DONE, FAILED, REFUSED, DECLINED).

## 7. Existing automated-test coverage
Shell: housekeeping-workflow-test.sh, housekeeping-launcher-test.sh, launcher-stdin-text-test.sh. Python: housekeeping-policy-test.py, housekeeping-input-test.py, tui-housekeeping-test.py. Shell and Python runners use separate temp dirs and bind no shared ports, so they run as one parallel group.

## 9. Baseline test results
Commands taken from scripts/run-shell-tests.sh, scripts/run-python-tests.sh (CLAUDE.md mandated runners). Not run here; the driver's baseline is authoritative. Repository documents no flaky test; some Python suites may fail on a clean checkout.

## 12. Likely change surface
`scripts/housekeeping-workflow.sh`, `prompts/housekeeping-plan.md`, `uncle_tui.py`, `scripts/tests/housekeeping-workflow-test.sh`, `scripts/tests/tui-housekeeping-test.py`, README.md.

## 13. Regression-sensitive components
TUI workflow state machine (`self.proc`, `state`, `_poll_workflow`); driver.lock semantics shared with build drivers; mode resolution.

## 15. Unknowns and assumptions
- 'Build window' interpreted as: the TUI session/checkout while a build workflow runs (no new UI pane).
- Agent file edits cannot be sandboxed from the working tree (deny list is a guard rail); containment is by prompt rule plus deny patterns.

## 16. Initial risk assessment
Medium: concurrent subprocess in a single-proc TUI; shared-state writes (mode file). Low for script lock change.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

