# Baseline Report

Omitted sections: Reproduction (feature, not a bug); Parallel-group independence beyond section 7 (stated there)

## 1. Change-request summary
Issue 148 (.uncle/docs/CHANGE_REQUEST.md): add `--housekeeping` / `/housekeeping` and a new short driver `scripts/housekeeping-workflow.sh` for non-code tasks, gated by an allowlist plus an editable disallow list.

## 2. Repository architecture
- `uncle` (bash launcher, 781 lines): arg parsing, usage, did-you-mean, startup action env (`UNCLE_STARTUP_ACTION/TEXT/TEXT_FILE`), TUI launch, line-menu fallback.
- `uncle_tui.py` (7892 lines): curses TUI, slash commands, Configure screens, startup actions.
- `scripts/*.sh` drivers (`change-workflow.sh` 4977 lines, `workflow.sh`, `from-issue.sh`); shared libs in `scripts/lib/` (state.sh, gates.sh, stage-config.sh, document-layout.sh, change_request_stdin.py, ...).
- Tests: `scripts/tests/*-test.sh` (run by `scripts/lib/shell_suites.py`) and `*-test.py` (via `scripts/run-python-tests.sh`); 414 files.

## 3. Relevant code paths
- `uncle:57-105` usage; `uncle:108-190` arg loop; `uncle:122` `--unattended`; `uncle:123-141` `--change-request` (mutual-exclusion via `UNCLE_STARTUP_ACTION`, python3 stdin validator); `uncle:142-190` `--application`, `--issue`; `uncle:198` did-you-mean option list; `uncle:219` export of startup env; `uncle:233-263` TUI lock; `uncle:276-289` startup-action TUI launch; `uncle:394-463` unattended relaunch loop.
- `uncle:612-632` line-menu `configure_menu`, option 3 Miscellaneous uses `config_get`/`config_set` (`misc.*` keys).
- `uncle_tui.py:980` reads `UNCLE_STARTUP_ACTION`; `:4022-4058` `_handle_startup_action` (create_app, github_issue, change_request); `:4062` `_start_change_request`; `:1292-1295` `_config_items` (Miscellaneous entry); `:1686` `save_config`; `:5914-5949` `_slash_choices`/command table; `:6016,6081,6361` slash handling and help strings.
- `scripts/lib/change_request_stdin.py`: stdin validation (CAP 1048576, UTF-8, control-char regex, empty check).
- `.uncle/workflow/driver.lock` (flock) is the per-checkout driver lock (`uncle:233`).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle --change-request < f` | Validated text becomes CHANGE_REQUEST.md, change flow starts in TUI | uncle:123-141 | Yes |
| B-2 | two of --application/--issue/--change-request | `Error: ... mutually exclusive`, exit 1 | uncle:124,144,162 | Yes (extend message) |
| B-3 | unknown flag | did-you-mean from fixed list | uncle:198 | Yes (add flag to list) |
| B-4 | `--unattended` | forwarded to driver, gates auto-satisfied and recorded | uncle:122,406-463 | Yes |
| B-5 | TUI slash commands | `/issue /change /triage ...` only | uncle_tui.py:5915 | Yes |
| B-6 | Configure > Miscellaneous | TUI Markdown viewer etc.; line menu auto_mode/approval_name | uncle_tui.py:1295, uncle:617 | Yes |
| B-7 | second driver on same checkout | refused by driver.lock | uncle:233 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| V-1 | Start modes mutually exclusive | `UNCLE_STARTUP_ACTION` non-empty check | launcher tests (not individually verified) | Medium |
| V-2 | stdin request: UTF-8, <=1048576 B, no control chars, non-empty | change_request_stdin.py | change-request-exists-prompt-test.sh and siblings | Medium |
| V-3 | One driver per checkout | flock driver.lock | launcher-tui-lock-test.sh | Medium |
| V-4 | Drivers never bypass human gates except via --unattended, recorded | gates libs | gate suites | Medium |

## 6. Current API, schema, and interface contracts
- CLI flags/usage text above; env `UNCLE_STARTUP_ACTION` values `create_app|github_issue|change_request`; TUI raises ValueError on unknown action (uncle_tui.py:4056).
- `.uncle/config`: flat dotted keys (`stage.runner`, `misc.*`, `supervision.*`) accessed by `config_get/config_set/config_clear` (bash) and `save_config` (TUI). Exact on-disk syntax not inspected; implementation must reuse the helpers. UNRESOLVED only as to syntax, not as to approach.
- Workflow state/records under `.uncle/workflow/`; docs under `.uncle/docs/`.

## 7. Existing automated-test coverage
- Shell suites (`scripts/tests/*-test.sh`) and Python suites (`*-test.py`) cover launcher, TUI config, gates, locks (e.g. tui-config-test.sh, launcher-tui-lock-test.sh, tui-hotkeys-test.py).
- Shell and Python runners use separate temp dirs and bind no shared ports, so they run as one parallel group (per runner docs: shell ~297 s, Python ~196 s, both at once ~297 s).
- No housekeeping tests exist. Some existing tests may assert exact usage text, did-you-mean list or slash-command help strings; not individually checked.

## 8. Exact build and test commands
See `verification_commands` field.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (Uncle's documented runners). Not run here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Per runner docs, some Python suites already fail on a clean checkout.

## 10. Existing failures, warnings, flaky behavior
Some Python suites fail on a clean checkout (documented in stage instructions); specifics deferred to the driver baseline. UNRESOLVED: which ones.

## 12. Likely change surface
`uncle`, `uncle_tui.py`, new `scripts/housekeeping-workflow.sh`, new `scripts/lib/housekeeping_*.py`, new prompt file, new tests, docs (README/usage).

## 13. Regression-sensitive components
Launcher arg loop and mutual-exclusion logic; did-you-mean list; TUI startup-action dispatch and slash table; Configure item numbering (`_config_items`); config read/write helpers; existing tests asserting usage/help text.

## 14. Areas explicitly outside the change
`change-workflow.sh`, `workflow.sh`, `from-issue.sh`, gate libs (reused, not edited), `change_request_stdin.py`, other drivers' stage plumbing.

## 15. Unknowns and assumptions
- Exact `.uncle/config` serialization and TUI list-editing widgets (assume reusable helpers; reuse rather than invent).
- Whether existing tests pin usage text.
- Assume agent runner invocation for the plan stage can reuse `stage-config.sh` lookups.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Policy bypass via parser gaps (safety boundary in unattended mode) | High |
| Breaking launcher arg parsing / existing tests | Medium |
| TUI edit flow complexity in a 7.9k-line file | Medium |
| Verify step reporting false pass | Medium |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

