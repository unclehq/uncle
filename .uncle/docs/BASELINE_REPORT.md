# Baseline report (issue 145)

Omitted sections: Reproduction (feature, not a bug); Existing failures (none documented in-repo; driver baseline is authority)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md: detect a desktop app (Electron, then Tauri) at the end of a build, offer to launch it, launch with the project's run command, report command/PID/log, and track the process. Web preview behavior must not change.

## 2. Repository architecture
- `uncle_tui.py` (curses TUI, large; grep only) drives the workflow, owns the completion dialog and the web `CompletionPreview`.
- `scripts/lib/completion_preview.py` (417 lines): launch.json reading (`launch_spec` 231, `validate_launch_spec` 240), manifest derivation (`derive_launch_manifest` 108), `CompletionPreview` thread class (268).
- `scripts/lib/process_tree.py`: `group_options` 203, `kill_tree` 279, `launch_command` 159.
- `scripts/lib/preview-build.sh` / `preview_server.py` / `preview_kind.py`: the EARLY preview (before code exists, web/CLI only); not touched here.
- `scripts/change-workflow.sh` / `workflow.sh` are bash drivers; `completion_preview.py --normalize` is called at change-workflow.sh:4321 and 4549.

## 3. Relevant code paths
| Path | Lines | Role |
|---|---|---|
| uncle_tui.py `_offer_support` | ~2240-2280 | runs after workflow exit code 0; unattended path calls `finish_decision` -> `_show_early_preview` + `_quit`; attended creates `CompletionPreview` only when `_workflow_family()=="app"` |
| uncle_tui.py `_poll_completion_preview` | ~2488 | drains preview events into `home_history` |
| uncle_tui.py `_completion_dialog` | ~2511 | sets `prompt_kind` support/finished |
| uncle_tui.py `stop_workflow`, `_quit` | ~2916, ~7386 | both close `completion_preview` |
| uncle_tui.py `_workflow_family`, `_project_root`, `workflow_unattended` | 141, 134, 2121 | family and unattended flag |
| completion_preview.py `launch_spec` | 231 | `.uncle/launch.json` kinds command/webpage/none |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | App-family build completes, attended, launch.json webpage | Server started, readiness polled, browser opened, star dialog | completion_preview.py:268-370; completion-preview-test.py | Yes |
| B-2 | Launch.json kind command | Process streamed in chat, Esc stops | completion_preview.py run(); test_command_streams_and_accepts_input | Yes |
| B-3 | Unattended app-family finish | `_show_early_preview` then quit; no dialog | uncle_tui.py ~2250-2262 | Yes |
| B-4 | Change-family finish | No completion preview at all | uncle_tui.py ~2273 | Yes (for non-desktop) |
| B-5 | Quit / stop_workflow | `CompletionPreview.close` kills process tree | uncle_tui.py 2917, 7387 | Yes |
| B-6 | Electron/Tauri project | Nothing detects it; derive_launch_manifest may treat `npm run dev` as webpage/command | completion_preview.py:108-138 | No (desktop MODIFY) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| E-1 | Launching is not evidence; no test-report row written | CompletionPreview writes no report | completion-preview-test.py | Medium |
| E-2 | Invalid launch metadata launches nothing | `validate_launch_spec` | test_invalid_manifest_does_not_launch | High |
| E-3 | Launch commands are argument arrays, not shell strings | validate_launch_spec 240-262 | launch-manifest-test.py | High |
| E-4 | Preview process is killed on quit | CompletionPreview.close | preview-server-test.py (partial) | Medium |

## 6. Current API/schema/interface contracts
`.uncle/launch.json` shape (command/webpage/none) is a public contract and stays unchanged. `.uncle/config` is whitespace `key value` lines with `#` comments. Env switches use `WORKFLOW_*`.

## 7. Existing automated-test coverage
Python suites in scripts/tests/*-test.py (completion-preview-test.py, launch-manifest-test.py, preview-server-test.py, tui-complete-dialog-test.py, tui-support-test.py) and shell suites run by the two runner scripts. The shell and Python runners use separate temp dirs and no shared ports, so they are one parallel group (per runner documentation in run-python-tests.sh and project convention).

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh. No results were produced here; the driver baseline (.uncle/workflow/green-check.baseline.tsv) is authoritative. No repository-documented failures found.

## 12. Likely change surface
New `scripts/lib/desktop_launch.py`; hook in `uncle_tui.py` `_offer_support`/poll/close; new tests; scripts/README.md note.

## 13. Regression-sensitive components
uncle_tui.py completion/support dialog sequencing (star prompt), CompletionPreview web launch, unattended quit path.

## 14. Outside the change
early preview (preview-build.sh, preview_server.py, preview_kind.py), launch.json schema, packaging/signing, GUI testing, mobile, test-report writers, bash drivers.

## 15. Unknowns and assumptions
- Assumed no existing `WORKFLOW_PREVIEW_DESKTOP` or desktop detection anywhere (grep of scripts/ and uncle_tui.py found none).
- Whether `.uncle/config.example` exists was not checked; docs go in scripts/README.md.
- Windows/Linux display quirks cannot be exercised on this darwin host.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Dialog sequencing in the large TUI regresses star/finished dialogs | Medium |
| Orphaned GUI process | Medium (mitigated by pid file + close hooks) |
| False-positive detection launching GUI | Low (confirmation required, unattended never launches) |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

