# Baseline report — Issue 226

Omitted sections: Reproduction result (not executed; static reading shows the path, see 4); Existing failures (none documented; the driver baseline is authoritative)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 226). One unrecognized `supervision.*` key disables all supervision corrections; unattended hosted runs never see the message.

## 2. Repository architecture
Python supervisor library `scripts/lib/supervisor.py` (config, journal, worker), bash glue `scripts/lib/supervision.sh`, hosted-mode helpers `scripts/lib/hosted.py`, TUI `uncle_tui.py` (calls `load_config` at many sites, shows `disabled_reason` at ~5125). Docs: README.md, docs/supervision.md.

## 3. Relevant code paths
- `scripts/lib/supervisor.py:58-75` CONTROLS/KINDS/DEFAULTS.
- `:107-111` parse_value raises ValueError for unknown key.
- `:179-196` Config(values, errors), `disabled_reason` non-empty iff errors.
- `:203-224` load_config appends every ValueError to errors; first occurrence of a key wins.
- `:227-242` _hosted_defaults (runner self-hosted, model from SEREN_MODEL/UNCLE_MODEL; missing model appends an error).
- `:615` note_prompt, `:974-975` Supervisor init status, `:1002-1009` reload_config: all gate on `config.errors`.
- `:1816-1822` supervised-run entry (loads config, decides to supervise); `:1923-1929` CLI `config` action prints disabled_reason to stderr, exit 1 on errors.
- `scripts/lib/hosted.py:4-23` is_hosted (UNCLE_HOSTED==1), OPENAI_BASE_URL/OPENAI_API_KEY/model.
- `scripts/lib/supervision.sh:150` calls note-prompt with stderr discarded.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | config has `supervision.<unknown> v` | ValueError -> errors -> corrections disabled with message `unknown supervision key: supervision.X` | supervisor.py:110, 212, 195 | No (MODIFY) |
| B-2 | recognized key, invalid value | errors -> disabled | supervisor.py:112-149; supervisor-test.py:923-932 | Yes |
| B-3 | valid config | no errors, enabled | supervisor-test.py:914-922 | Yes |
| B-4 | hosted, no runner key | runner self-hosted, hosted model | supervisor.py:227-242; hosted-mode-test.py | Yes |
| B-5 | hosted, no model env | error appended, disabled | supervisor.py:242 | Yes |
| B-6 | CLI `config` with errors | lines on stdout, reason on stderr, exit 1 | supervisor.py:1923-1929 | Yes |
| B-7 | supervised run start with errors | disabled reason only in status/TUI; no stderr line from run entry | supervisor.py:974, 1816 | No (MODIFY for hosted) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Invalid recognized value never substituted with a default limit | load_config leaves value out, errors set | supervisor-test.py:932 | High |
| I-2 | Any config error disables corrections | disabled_reason / `config.errors` gates | supervisor-test.py:934+ | High |
| I-3 | CONTROLS list equals documented keys (AT-9) | CONTROLS comment | supervisor-test.py (AT-9) | Medium |

## 6. Interface contracts
`Config.errors` (list of str), `Config.disabled_reason` (str), `Config.lines`, CLI `supervisor.py config --config PATH`. No schema/persistence.

## 7. Existing automated-test coverage
`scripts/tests/supervisor-test.py` (config roundtrip incl. `('bogus','1')` expecting an error at line 925, 930-932), `hosted-mode-test.py` (:112 load_config in hosted), `supervisor-default-runner-test.py`. `supervisor` is in `scripts/tests/critical-suites.txt`. Shell and Python runners use separate temp dirs and share no ports, so they are one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CLAUDE-documented Uncle runners). No results produced here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`scripts/lib/supervisor.py` (load_config, Config, run entry, CLI config), `scripts/tests/supervisor-test.py`, README.md, docs/supervision.md.

## 13. Regression-sensitive components
TUI uses of `load_config`/`disabled_reason` (uncle_tui.py:5109-5125); `parallel-implement.sh:112` reads `files_allowlist`; reload_config.

## 14. Outside the change
Hosted-mode defaults logic, runner selection, the journal, TUI rendering.

## 15. Unknowns and assumptions
- `.uncle/config.example` is not tracked in this tree (git ls-files empty); the build script writing `supervision.base_url` is not in this repository. Assumption: those two items cannot be changed here.
- Warnings are emitted via stderr; the host failure report reads stderr (per request).

## 16. Initial risk assessment
Low-medium: loosening validation must not hide invalid values of recognized keys; stderr noise must not break callers that parse stdout.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

