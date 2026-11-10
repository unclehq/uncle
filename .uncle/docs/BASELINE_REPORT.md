# Baseline: Supervision menu tooltips

Omitted sections: Reproduction (feature, not a bug); Flaky behavior (none documented in repo)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 81): show a hint for every Supervision option, not only the highlighted one, and explain each value-picker choice; reuse `SUPERVISION_DESC` as single text source.

## 2. Repository architecture
Single-file curses TUI `uncle_tui.py` (class `UncleTUI`); supervision config schema in `scripts/lib/supervisor.py` (imported as `supervision_lib`). Python suites in `scripts/tests/*-test.py`, shell suites `*-test.sh`.

## 3. Relevant code paths
| Symbol | Location |
|---|---|
| `supervision_lib.CONTROLS` (13 tuples incl. `files_allowlist`), `DELEGATIONS`, `KINDS`, `DEFAULTS` | scripts/lib/supervisor.py:55-74 |
| `SUPERVISION_DESC` (13 keys) | uncle_tui.py:772-786 |
| `_picker_rows` | uncle_tui.py:1739-1778 |
| `_picker_current` | uncle_tui.py:1794 |
| `_open_picker` | uncle_tui.py:1814 |
| `items()` -> `_supervision_items` | uncle_tui.py:1361, 1660, 5070 |
| `_supervision_desc`, `_supervision_enter` | uncle_tui.py:5081, 5087 |
| `_draw_config_desc` | uncle_tui.py:8336 |
| `_title` (picker titles) | uncle_tui.py:8269 |
| `_draw_picker` | uncle_tui.py:8377 |
| Existing TUI test (`TuiHostTests`) | scripts/tests/supervisor-test.py:1016, asserts `_supervision_items()[0].startswith('enabled')` at :1214 |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Open Configure -> Supervision | One row per CONTROLS key: `key(ljust 26)  value` or `value  (default)`; extra `! reason` row when config invalid | uncle_tui.py:5070-5079; test :1214 | Yes (row prefix `key`) |
| B-2 | Highlight a row | Full `SUPERVISION_DESC` + "Enter edits..." shown in right panel (>=18 cols free) else strip below list | :5081, :8336-8375 | Yes |
| B-3 | Enter on bool (`enabled`) | Toggles true/false, no picker | :5092 | Yes |
| B-4 | Enter on `effort`/`runner`/`model` | Picker lists bare values (effort: EFFORTS none/low/medium/high + Custom; runner: installed supported runners; model: catalog) | :1744-1778 | Yes (values/order) |
| B-5 | Enter on `delegate_gates` and numeric keys | `_open_picker` -> picker_kind unrecognised -> only `Custom...` free-text row; no none/routine choices | :1778, :1814 | Choice list is MODIFIED; free-text validation preserved |
| B-6 | Picker row render | `> value  <label>  <current>`; label only for models | :8388-8402 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Documented control key list equals `CONTROLS` (AT-9) | DocsTests | supervisor-test.py:1750 | High |
| I-2 | Values are validated by supervision_lib before use; invalid disables corrections | `load_config` | ConfigTests :903 | High |
| I-3 | Drawing never raises on tiny terminals (curses.error swallowed) | try/except in draw funcs | none found | Medium |

## 6. Interface contracts
No external API/schema. Internal: `items()` returns list[str] consumed for selection/width; `_picker_rows()` returns (kind,text) with kind in header/option/model/custom; `.uncle/config` keys unchanged.

## 7. Existing automated-test coverage
supervisor-test.py covers config, docs and TUI host wiring but nothing on `SUPERVISION_DESC` content, `_draw_config_desc`, or `_picker_rows` (grep found only :1214). No test draws a picker. Parallel commands use separate temp dirs (shell and python runners per CLAUDE.md guidance).

## 9. Baseline test results
Not run by the analyst. Commands are from scripts/run-shell-tests.sh and scripts/run-python-tests.sh. Command 3 names a suite (`supervision-tooltips`) that does not exist at baseline; it is expected to fail/not-found pre-change and is added by the change. Driver baseline is authoritative.

## 12. Likely change surface
uncle_tui.py (SUPERVISION_DESC area, `_picker_rows`, `_picker_current`, `_title`, `_draw_picker`, `_supervision_items`, `_draw_config_desc`); new test file scripts/tests/supervision-tooltips-test.py; possibly README/.uncle/config.example only if wording drift is found.

## 13. Regression-sensitive components
Model/runner/effort pickers of stage config (same `_picker_rows`/`_draw_picker` shared); `items()` width drives side-panel vs strip layout; `_picker_filtered` typing filter; custom-entry flow.

## 14. Outside the change
Supervisor engine, CONTROLS semantics/defaults, config parsing, stage (non-supervision) config menus' text, gate logic.

## 15. Unknowns and assumptions
- `files_allowlist` has a description but is a 13th CONTROLS key (issue says 12); all 13 get hints.
- Picker choice rendering for non-supervision targets must stay unchanged.
- Picker-apply path for a `delegate` kind not yet read; plan step 3 reads it.

## 16. Initial risk assessment
Medium-low: UI-only, but shared picker code and curses width handling. Main risk is changing `items()` width and degrading the side panel.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- supervisor supervisor-default-runner supervision-tooltips
python3 -B -m py_compile uncle_tui.py
```

## Parallel verification groups

```text
1 2
```

