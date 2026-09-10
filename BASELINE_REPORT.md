# Baseline Report
Omitted sections: none

## 1. Change-request summary
See `CHANGE_REQUEST.md:13-18`.

## 2. Repository architecture
Bash/Python; no build (`CONTRIBUTING.md`).
Dependencies: `Formula/uncle.rb:7-11`.

## 3. Relevant code paths
| ID | Path |
|---|---|
| P1 | `uncle_tui.py:2444` selection → `2491` launch → `1268` subprocess |
| P3 | `scripts/change-workflow.sh:1523` input guard |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | Missing inputs; choose new/change | Launch requested | §8 command 4: mocked launcher | No |
| B2 | Change ANALYZE; missing/empty input | Exit 1 | P3; `require_file:341` | Yes |
| B3 | Dismiss notice | Configure opens | `uncle_tui.py:2276` inspection | Existing notice: yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Launch in project root | `uncle_tui.py:1303`, `_project_root:53` | issue-project-root-test.sh (seeder only) | High: code |
| I2 | Issue selection precedes launch | `uncle_tui.py:2454` | Unverified | High: code |

## 6. Current API, schema, and interface contracts
| ID | Contract |
|---|---|
| C1 | `uncle_tui.py:1013`: issue/mode arguments; optional --unattended |

## 7. Existing automated-test coverage
Inspected TUI tests lack input-file checks.
Driver/packaging/Windows suites unexecuted.

## 8. Exact build and test commands executed
```sh
bash -c 'for f in uncle install.sh scripts/*.sh scripts/lib/*.sh scripts/tests/*.sh; do bash -n "$f" || exit; done'
bash -o pipefail -c 'export PYTHONDONTWRITEBYTECODE=1; failed=0; for t in scripts/tests/tui-config-test.sh scripts/tests/tui-performance-test.sh scripts/tests/tui-session-panel-test.sh scripts/tests/issue-project-root-test.sh; do bash "$t" 2>&1 | tail -8; rc=$?; printf "%s: exit %s\n" "$t" "$rc"; [ "$rc" -eq 0 ] || failed=1; done; exit "$failed"'
python3 -B scripts/tests/tui-support-test.py -q
python3 -B -c 'import tempfile; from unittest.mock import Mock, patch; from uncle_tui import UncleTUI; tmp=tempfile.TemporaryDirectory(); ui=UncleTUI.__new__(UncleTUI); ui.maybe_reload=Mock(); ui.start_workflow=Mock(); ctx=patch("uncle_tui._project_root", return_value=tmp.name); ctx.start(); [(setattr(ui,"state","menu"),setattr(ui,"sel",i),ui._confirm(),print(i,ui.state,ui.start_workflow.call_count)) for i in (0,2)]; ctx.stop(); tmp.cleanup()'
bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/tui-session-panel-test.sh 2>&1 | tail -25'
python3 -B scripts/tests/early-prerequisites-test.py -q
```

## 9. Baseline test results
| ID | Command | Result |
|---|---|---|
| T1 | 1 | PASS |
| T2 | 2 | FAIL: config 80 checks, timing 4 tests, issue-root pass; panel 2/13 fail |
| T3 | 3 | PASS: 4 tests |
| T4 | 4 | Outputs: 0 running 1; 2 running 2 |
| T5 | 5 | Same two failures |
| T6 | 6 | PASS: 5 tests |

## 10. Existing failures, warnings, and flaky behavior
| ID | Finding |
|---|---|
| F1 | Panel failures: test_live_k3_estimate_and_completed_estimate_are_labeled; test_live_tokens_and_projected_cost. Cause unresolved. |
| F2 | Initial git status: modified CHANGE_REQUEST.md, scripts/from-issue.sh; untracked scripts/tests/issue-project-root-test.sh. |

## 11. Reproduction result for the reported bug, if applicable
T4: empty project, mocked launch.
UNRESOLVED: rendering/driver execution; settle via isolated terminal run.

## 12. Likely change surface
P1, `uncle:572,612`, menu tests.

## 13. Regression-sensitive components
B3, I1/I2 and C1.

## 14. Areas explicitly outside the change
UNRESOLVED: request scope placeholder.

## 15. Unknowns and assumptions
| ID | Unknown; resolution |
|---|---|
| U1 | README/GitHub, empty files, resume: clarify scope. |
| U2 | ASSUMPTION: motivation controls filenames; confirm scope. |
| U3 | F1/platforms unverified; isolate metrics, run native checks. |

## 16. Initial risk assessment
Medium: shared launch/notice paths (P1, B3).
