# Baseline Report — Issue 180
Omitted sections: Reproduction (not a bug report); Performance/flaky (none known)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (Issue 180): offer `aws-bedrock` in every runner picker with Self hosted parity.

## 2. Repository architecture
- `uncle` (bash): interactive menu + shell-fallback Configure (`configure_stage` uncle:751, `configure_menu` :845, `configure_stages_menu` :867). Config is a flat `.uncle/config` file edited via `config_set/config_clear` (:720/:737).
- `scripts/lib/stage-config.sh`: runner resolution/dispatch. `aws-bedrock` is normalized to `self-hosted` for dispatch (:290, :311); raw value kept by `uncle_raw_stage_runner` (:298); model lookup is Bedrock-aware (:344).
- `scripts/lib/self_hosted.py`: runner implementation + profile CLI (`profile_menu` :1947, `main` :1970 handles `models`, `choose-model`, `set-key`). Keys per profile via `key_file/read_keys/save_keys(config, keys, profile)` (:33/:82/:99); Bedrock keys in `.uncle/aws-bedrock-keys.json`.
- `uncle_tui.py`: full-screen TUI. `AGENT_RUNNERS/REVIEWER_RUNNERS/HTTP_RUNNERS/PROFILES` (:367-376), `selectable_runners` (:731), `_keys_for(runner)` (:1211), `_apply_opencode_to_all_stages` (:1414).

## 3. Relevant code paths
| Path | Lines |
|---|---|
| uncle configure_stage runner prompt / m / a / d | 772-786, 824-831, 788-819, 832-838 |
| uncle configure_menu item 2, stages menu `m` | 852, 887 |
| uncle stage list uses normalized runner | 875 |
| stage-config.sh `uncle_installed_runners` | 248-271 (also used :103, :316) |
| self_hosted.py profile CLI | 1947-1982 |
| uncle_tui.py apply-to-all | 1414-1431 (caller 7989) |
| uncle_tui.py self-hosted migration | 1763-1780 |
| uncle_tui.py status runner alias | 3356 |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Fallback `r`, type `aws-bedrock` | Rejected: "Not a <side> runner" (choices from `uncle_installed_runners`) | uncle:772-785 | No (MODIFY) |
| B-2 | Fallback with Bedrock stage | Shown as `self-hosted` (normalized); `m`/`a` act on Self hosted keys/models | uncle:755,760,789,825 | No (MODIFY) |
| B-3 | `uncle_stage_runner` for `aws-bedrock` | Returns `self-hosted` | stage-config.sh:311; aws-bedrock-dispatch-test.sh | Yes |
| B-4 | TUI runner picker | Lists aws-bedrock; has Configure AWS Bedrock | uncle_tui.py:367,733,1443 | Yes |
| B-5 | TUI apply-to-all on Bedrock stage | "Select Self hosted..." refusal | uncle_tui.py:1418 | No (MODIFY) |
| B-6 | Fallback Configure menu | Only "Configure self hosting"; no Bedrock connection setup | uncle:848-852 | No (ADD item) |
| B-7 | Fallback `d` | Clears stage's self-hosted key only | uncle:837 | Yes for Self hosted; extend |
| B-8 | `uncle_installed_runners` | claude/codex/kimi/self-hosted(opencode) by PATH | stage-config.sh:248 | Yes (unchanged) |
| B-9 | Self-hosted fallback `m`/`a` | Works via self_hosted.py default profile | uncle:824-831 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Bedrock token stored only in aws-bedrock-keys.json; never in Self hosted store or config | key_file :33, save_keys :99 | aws-bedrock-test.py | High |
| I-2 | Non-Bedrock runner dispatch and unknown-runner error unchanged | stage-config.sh | aws-bedrock-dispatch-test.sh | High |
| I-3 | Self hosted state not rewritten by Bedrock features | profile separation | aws-bedrock-test.py (assumed) | Medium |

## 6. Interface contracts
- Config file: `<stage>.runner|model|base_url|effort`. `self_hosted.py models|choose-model <config>`, `set-key <config> <stage>` (stdin = key). Choose-model prints selected model on stdout, prompts on stderr, exit non-zero on invalid.

## 7. Existing automated-test coverage
`scripts/tests/aws-bedrock-dispatch-test.sh` (dispatch vs HEAD stage-config.sh), `aws-bedrock-test.py`, `aws-bedrock-protocols-test.py`. No test drives `configure_stage` or the TUI Bedrock apply-to-all. Runner `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` use separate temp dirs and share no ports, so they are one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (existing runners). Not executed here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout (per workflow notes); not verified by this stage.

## 12. Likely change surface
`uncle`, `scripts/lib/stage-config.sh` (additive helper), `scripts/lib/self_hosted.py` (CLI profile arg), `uncle_tui.py` (apply-to-all), new tests, `docs/aws-bedrock.md`, `README.md`.

## 13. Regression-sensitive components
Self hosted fallback `m`/`a`/`d` behavior; `uncle_installed_runners` (feeds default-runner choice and no-runner error); aws-bedrock-dispatch-test (diffs stage-config.sh against HEAD); config file format.

## 14. Outside the change
Bedrock wire protocols (`bedrock_protocols.py`, `self_hosted_http.py`), model discovery logic, dispatch normalization, workflow drivers (`stagegate.sh`, `change-workflow.sh`: they see `self-hosted` after normalization).

## 15. Unknowns and assumptions
- `uncle` may lack a source guard for sourcing `configure_stage` in tests; implementer checks (plan step 4).
- Whether discovery is reachable from the shell menu: assumed via existing `refresh_models` with the Bedrock profile as the TUI does (uncle_tui.py:1370-1384).

## 16. Initial risk
Low-medium: shell edits in an interactive menu; risk of changing Self hosted behavior or menu numbering.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

