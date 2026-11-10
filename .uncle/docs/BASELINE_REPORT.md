# Baseline report: issue 231

Omitted sections: Reproduction result (not run; saved plan was deleted with the sandbox, inferred only); Current API/schema contracts (no external interface changes)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 231). A failed project-plan check (`plan-unprotected`) exits 1 with no repair turn; headless runs never start the supervisor. Parser also admits non-path backticked spans in `Owns:`.

## 2. Repository architecture
Bash driver `scripts/stagegate.sh` runs stages; Python helpers in `scripts/lib/` (`plan_context.py` CLI, `plan_model.py` validator/model, `plan_steps.py` Markdown step parser). Tests are `scripts/tests/*-test.py` and `*-test.sh`.

## 3. Relevant code paths
| Path | Role |
|---|---|
| `scripts/lib/plan_steps.py:69-90` | `COMMENT_MARKER` + `paths()`; backticked spans taken unconditionally except comment markers (`:88`); plain tokens must match `[\w./*?\[\]@-]+` (`:80`) |
| `scripts/lib/plan_model.py:474-482` | `validate` rejects invalid/dir `owns` tokens |
| `scripts/lib/plan_model.py:738-749` | `split_list` keeps any string, strips backticks |
| `scripts/lib/plan_context.py:335,358-361` | `plan-unprotected` action; prints `Correct the saved document and resume.` and exits 1 |
| `scripts/stagegate.sh:4636-4643` | PROJECT_PLAN check: on failure prints, `supervision_validation_failed`, `exit 1`; no repair |
| `scripts/stagegate.sh:5696-5700` | UPDATED_PLAN check: same shape, no repair |
| `scripts/stagegate.sh:1708` | `run_initial_planning_agent` (model call) |
| `scripts/stagegate.sh:4598-4604, 4431-4435` | existing spending-stop handling (`$STATE_DIR/spending-stop`, `stop-reason`) |
| `scripts/stagegate.sh:5011-5030` | precedent: format-retry marker file + prompt with appended error |
| `scripts/lib/supervision.sh:43-49`, `scripts/lib/supervisor.py:1204`, `scripts/lib/uncle_headless.py` | supervisor reacts only inside TUI; headless never starts it |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Owns line contains backticked comment marker (`-- EOF-GUARD`, `// end`, `# end`) | Marker dropped, real paths kept | `plan_steps.py:69,88`; `scripts/tests/plan-owns-comment-marker-test.py` | Yes |
| B-2 | Owns line has backticked span that is neither a comment marker nor path-shaped (e.g. `foo bar`) | Kept as path; validate fails `owns: replace ...` | `plan_steps.py:73-74,83-89`; `plan_model.py:480` | No (MODIFY) |
| B-3 | JSON `owns` array holds a non-path string | Kept after stripping backticks; validate fails | `plan_model.py:746` | No (MODIFY) |
| B-4 | PROJECT_PLAN check fails | Error printed to stderr, status event, exit 1, no repair | `stagegate.sh:4636-4643` | No (MODIFY) |
| B-5 | UPDATED_PLAN check fails | Same as B-4 | `stagegate.sh:5696-5700` | No (MODIFY) |
| B-6 | Valid plan | Check passes, flow continues to `ensure_project_plan_json` | `stagegate.sh:4644` | Yes |
| B-7 | Real path/glob spans (`src/**`, `.gitignore`, `.uncle/launch.json`) | Kept | plan-owns-comment-marker-test.py | Yes |
| B-8 | Spending stop in model call | Stage stops cleanly with `stop-reason: spending_limit` | `stagegate.sh:4598-4604` | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Every `owns` token is a valid path/glob and not a directory | `plan_model.validate` `:474-482` | plan-executability / plan-model suites | High |
| I-2 | An invalid saved plan never advances past the check | `exit 1` at `stagegate.sh:4642` | not directly tested | Medium |
| I-3 | A model call stops on a host spending stop | `spending-stop` file checks | `plan-sections-spending-stop-test.sh`, `self-hosted-spending-stop-test.py` | High |

## 6. Existing automated-test coverage
`plan-owns-comment-marker-test.py` (parser markers), `plan-executability-test.py`, `updated-plan-*-test.py`, `plan-disposition-gate-test.sh`, `headless-run-test.py`, spending-stop tests. No test covers a repair turn after a failed plan check, nor backticked non-path spans, nor `split_list` filtering. Shell and Python runners are independent (separate temp dirs), so they form one parallel group.

## 7. Baseline test results (section 9)
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (the repo's documented runners; default tier = `scripts/tests/critical-suites.txt`). Results are supplied by the driver's baseline, not run here. Some Python suites may already fail on a clean tree (documented in the driver instructions).

## 10. Existing failures, warnings, flaky behavior
None observed by reading; driver baseline is authoritative.

## 12. Likely change surface
`plan_steps.py`, `plan_model.py` (owns call sites), `stagegate.sh` (two check sites + helper), `plan_context.py` message, one new prompt, new tests.

## 13. Regression-sensitive components
Plan ingestion for every project (`paths()` is used by three Owns routes); `ensure_project_plan_json` after a repaired plan; spending-stop flow; sectioned-plan flow.

## 14. Outside the change
Supervisor/TUI behavior, `uncle_headless.py`, section-writing workers, the validator rules themselves, other stages' retries.

## 15. Unknowns and assumptions
- The issue says the parser takes every backticked span; the checked-out tree already drops comment markers, so only non-marker junk remains. Assumed the issue text predates that fix.
- Exact resume command text for the headless message is taken from existing stop messages in the driver (implementer to reuse).

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Path-shape filter drops a legitimate path containing a space | Medium (warned, plan then fails validation only if step ends with no owns, which is a warning) |
| Repair turn rewrites more than the error | Medium |
| Loop on repeated failure | Low with marker |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

