# Baseline Report — Issue 185

Omitted sections: Reproduction (not a bug); Current API/schema contracts (no schema; ids are plain strings)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 185): replace the Claude picker catalog with a 12-entry list and move the Claude default from `claude-sonnet-5` to `claude-sonnet-5-5` in the TUI and both shell drivers; fix a stale comment; add tests.

## 2. Repository architecture
Python curses TUI (`uncle_tui.py`) plus bash drivers (`scripts/*.sh`) and Python/shell test suites under `scripts/tests/`. TUI and shell duplicate the default model as separate literals; nothing links them.

## 3. Relevant code paths
- `uncle_tui.py:443-449` MODEL_CATALOG_CLAUDE (3 entries, one group "Claude").
- `uncle_tui.py:468-471` MODEL_LABELS derived from catalogs.
- `uncle_tui.py:475-486` stale comment + DEFAULT_MODEL_FOR_RUNNER (`claude` = `claude-sonnet-5`).
- `uncle_tui.py:1455` default display uses DEFAULT_MODEL_FOR_RUNNER + MODEL_LABELS.
- `uncle_tui.py:1687`, `uncle_tui.py:8870` other consumers of the catalogs (picker static list; custom-id dedupe).
- `scripts/stagegate.sh:282` `DEFAULT_MODEL="claude-sonnet-5"`; used at `:968` as stage_model fallback.
- `scripts/reviewer-claude.sh:37` `DEFAULT_MODEL=${WORKFLOW_REVIEWER_CLAUDE_MODEL:-claude-sonnet-5}`; allowlist `claude*|opus*|sonnet*|haiku*` at `:89-96`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Open model picker for Claude runner | Lists Opus 5, Sonnet 5, Haiku 4.5 | uncle_tui.py:443-449 | No (MODIFY) |
| B-2 | Stage with no stored model, claude runner | Shows/uses `claude-sonnet-5` | uncle_tui.py:483, stagegate.sh:282, reviewer-claude.sh:37 | No (MODIFY) |
| B-3 | Codex/Kimi pickers and defaults | Own catalogs/defaults | uncle_tui.py:451-486 | Yes |
| B-4 | reviewer-claude.sh given non-Claude model | Falls back to DEFAULT_MODEL with warning | reviewer-claude.sh:89-96 | Yes |
| B-5 | WORKFLOW_REVIEWER_CLAUDE_MODEL / per-stage overrides set | Override wins over default | reviewer-claude.sh:37; stagegate.sh:960-975 | Yes |
| B-6 | `execute-checklist` stage fallback | `kimi` | stagegate.sh:970 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Every catalog id passes the reviewer-claude allowlist | Comment only (uncle_tui.py:438-442) | None found | Low |
| I-2 | TUI and shell Claude defaults agree | Convention only | None found | Low |
| I-3 | Codex ids are not in agent-codex.sh blanked set | Comment only | Not examined | Low |

## 7. Existing automated-test coverage
No suite found referencing MODEL_CATALOG_CLAUDE, DEFAULT_MODEL_FOR_RUNNER or `claude-sonnet-5` as a default (grep over scripts/tests). `attestation-test.py` uses `claude-opus-5` only as fixture data (lines 49, 95, 127, 145) and is unaffected by catalog changes. `aws-bedrock-configure-test.py:28` shows the pattern for importing `uncle_tui.py` via importlib. Shell and Python runners use separate temp dirs and ports, so they are independent and run as one parallel group.

## 9. Baseline test results
Not run in this stage; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh`. Some Python suites may already fail on a clean checkout; the driver baseline records which.

## 10. Existing failures, warnings, flaky behavior
None documented in repository files inspected. UNRESOLVED until the driver baseline lands.

## 12. Likely change surface
`uncle_tui.py` (catalog, default, comment), `scripts/stagegate.sh:282`, `scripts/reviewer-claude.sh:37`, one new Python test `scripts/tests/claude-model-defaults-test.py`.

## 13. Regression-sensitive components
Picker rendering with a 12-entry list (scrolling/filter at uncle_tui.py:1687); custom-model dedupe (:8870); default label display (:1455); any test asserting the old 3-entry catalog (none found).

## 14. Outside the change
Codex and Kimi catalogs/defaults; reviewer allowlist logic; agent-*.sh shims; attestation fixtures; docs not naming the old default.

## 15. Unknowns and assumptions
- Docs/READMEs may mention `claude-sonnet-5`; grep outside .uncle found none beyond listed files.
- Assumed ids in CHANGE_REQUEST.md are authoritative and need no external validation.

## 16. Initial risk assessment
Low. Risks: duplicated literal drifting again (mitigated by new test); picker UX with 12 entries.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

