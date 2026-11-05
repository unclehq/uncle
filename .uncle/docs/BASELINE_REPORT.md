# Baseline Report (Issue 164)

Omitted sections: Reproduction (feature, not a bug); Baseline test results (driver supplies them, see section 9)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`: delete housekeeping entirely; make the idle home-chat supervisor a tool-enabled agent; keep validated build actions; tool-free supervisor while a build runs.

## 2. Repository architecture
Bash launcher `uncle` parses flags and starts `uncle_tui.py` (8165 lines, one `UncleTUI` class). Domain-ish libs in `scripts/lib/` (Python and bash). Tests in `scripts/tests/` (`*-test.py`, `*-test.sh`). Housekeeping = `scripts/housekeeping-workflow.sh` + `scripts/lib/housekeeping_{config,input,policy,session}.py` + `prompts/housekeeping-plan.md`.

## 3. Relevant code paths
- `uncle`: usage lines 70-125; mutual exclusion 172/224/255/283; `parse_text_option` 162-210 (uses `housekeeping_input.py`); `--housekeeping` case 273; did-you-mean list 337; `UNCLE_HOUSEKEEPING_UNATTENDED` 361; noui message 414; Configure menu item 4 and `housekeeping_disallow_menu` 830-870.
- `uncle_tui.py`: imports 99-101; config section UI 1132, 1354-1414; `_start_housekeeping` 1586; startup action 4230; `_housekeeping_idle/_session/_warm/_close/_turn` 3307-3371; `send_home_chat` 3374; `_apply_housekeeping_reply` 3695; slash commands 6111-6163, 6286, 6297; config screen 7041, 7607-7616, 7687; shutdown 7865-7885. Supervisor: `_supervisor_turn` 3467, `_supervisor_session` 3572, `_apply_home_reply` 3710, `_apply_home_action` 4034, `_home_action` 4090. Project dir: `_project_root()` 180 (env `UNCLE_PROJECT_ROOT`), `_follow_project_root` 2097, title 2003.
- `scripts/lib/housekeeping_session.py`: `build_command` 58 (uses `--allowedTools` and `--disallowedTools` deny list), `HousekeepingSession` 412.
- `scripts/lib/run_duties.py` 134-158 (STARTUP_ACTIONS, driver map); `uncle_headless.py` 314-328; `mode.sh` 93.
- `scripts/lib/home_chat.py` (97 lines), `home_actions.py` (140 lines): action schema and `parse_reply`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Idle home chat, mode housekeeping (default) | Message goes to persistent tool agent with deny list | uncle_tui.py:3307-3380 | No (replaced) |
| B-2 | `/mode supervisor`, or build running | Tool-free supervisor, validated actions | uncle_tui.py:3467, 3710 | Yes |
| B-3 | 'build issue 34' | `github_issue` action started by the app | home_actions.py, uncle_tui.py:4090 | Yes |
| B-4 | hello-world request | brief drafted, `create_app` action | home_actions.py | Yes |
| B-5 | `uncle --housekeeping` | runs housekeeping driver | uncle:273 | No (remove) |
| B-6 | `/housekeeping`, `/mode` | commands exist | uncle_tui.py:6111-6163 | No (remove) |
| B-7 | Configure item 4 | disallow list editor | uncle:830, uncle_tui.py:7041 | No (remove) |
| B-8 | Unknown option | usage plus did-you-mean | uncle:337 | Yes |
| B-9 | Driver moves root | `_follow_project_root` updates UNCLE_PROJECT_ROOT, status and title | uncle_tui.py:2097 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| V-1 | Builds start only via validated action | home_actions.parse_reply, `_home_action` | home-actions-test.py | High |
| V-2 | Supervisor chat is tool-free | supervisor_command flags | supervisor-chat-test.py | Medium |
| V-3 | No permission-bypass flags | convention (CLAUDE.md) | none found | Low |
| V-4 | Unknown flags exit non-zero | uncle did-you-mean | launcher tests | High |

## 6. Interface contracts
CLI flags `--application --issue --change-request --housekeeping`; env `UNCLE_STARTUP_ACTION`; env `UNCLE_HOUSEKEEPING_SESSION`, `HOUSEKEEPING_CHAT_TIMEOUT`, `UNCLE_HOUSEKEEPING_UNATTENDED` (deprecated no-op); config `.uncle/config` key `housekeeping.disallow`; home action JSON `uncle_action`.

## 7. Existing automated-test coverage
Housekeeping-only: `housekeeping-input-test.py`, `housekeeping-launcher-test.sh`, `housekeeping-policy-test.py`, `housekeeping-session-test.py`, `housekeeping-workflow-test.sh`, `tui-housekeeping-test.py`. Mentions in: `run-duties-test.py`, `mode-resolution-test.sh`, `launcher-stdin-text-test.sh` (8), `supervisor-chat-test.py`, `headless-run-test.py`, `home-actions-test.py`, `home-chat-test.py`, `launcher-noui-test.sh`, `chat-test.py`. Shell and Python runners are independent (separate temp dirs, no shared ports), so they run as one parallel group.

## 9. Baseline test results
Not run here by design. Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (repo convention in CLAUDE.md task text). Documented pre-existing failures: none found; the driver baseline in `.uncle/workflow/green-check.baseline.tsv` is authoritative.

## 10. Existing failures/flaky
None documented in the repository.

## 12. Likely change surface
See sections 3 and 7 files; plus `README.md` (9 mentions), `docs/quickstart.md:63`, `docs/UNATTENDED_DEFAULT_MIGRATION.md`, `prompts/housekeeping-plan.md`. `FINAL_AUDIT.md` (root) mentions housekeeping; it is a reviewer-owned artifact and is not edited.

## 13. Regression-sensitive components
`send_home_chat` routing; `_apply_home_reply` action parsing; launcher exclusivity and stdin rules (`parse_text_option`, shared with `--application`); `run_duties.py` startup action table; `_follow_project_root`.

## 14. Outside the change
Build drivers, gates, verification, PR flow, tool-free supervisor internals during a build, other runners' supervision.

## 15. Unknowns
- Whether Claude `-p` surfaces permission denials in the stream-json result (assumed `permission_denials` in the result event; the plan verifies by fake-runner fixture, live check in manual).
- Whether `housekeeping_input.py` is reused by `--application` (uncle:210 passes a label); it must be renamed, not deleted, if so.

## 16. Initial risk
High: 8k-line TUI edit with 77 housekeeping mentions; arbitrary-command agent safety; cwd tracking. Medium: shared stdin helper.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

