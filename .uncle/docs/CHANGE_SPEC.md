# Change Spec — Issue 185

Omitted sections: Performance, Security, Migration (no impact); Prototype isolation (not a prototype)

## 1. Change type
Feature / configuration default change.

## 2. Problem statement
The Claude runner's picker and defaults offer outdated models, and the default literal is duplicated across TUI and shell drivers with a stale comment.

## 3. Current behavior
See baseline B-1, B-2.

## 4. Desired behavior
Claude picker lists exactly 12 models (see AC-1) in the stated order; the single Claude default is `claude-sonnet-5-5` in TUI, `stagegate.sh`, `reviewer-claude.sh`; the stale "opus" comment is corrected.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | Claude picker opened | 3 entries | Exactly the 12 (label,id) pairs, in order, no others | New catalog test |
| SB-2 | MODIFY | Stage with no stored model, TUI | `claude-sonnet-5` | `claude-sonnet-5-5`, label "Claude Sonnet 5.5" | New test |
| SB-3 | MODIFY | Shell driver defaults | `claude-sonnet-5` | `claude-sonnet-5-5` in stagegate.sh and reviewer-claude.sh | New agreement test |
| SB-4 | MODIFY | Reading the DEFAULT_MODEL_FOR_RUNNER comment | Says "opus" tier alias | Accurately describes the current default | Inspection / test of no "opus" tier claim |
| SB-5 | PRESERVE | Codex/Kimi picker and defaults | Unchanged | Unchanged | Existing suites |
| SB-6 | PRESERVE | Model override env vars; non-Claude fallback | Override wins; fallback warns | Unchanged | Existing suites |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | Every Claude catalog id matches `claude*|opus*|sonnet*|haiku*` | MODEL_CATALOG_CLAUDE | New test reading the allowlist from reviewer-claude.sh | New test |
| SI-2 | NEW | TUI claude default == stagegate.sh DEFAULT_MODEL == reviewer-claude.sh DEFAULT_MODEL | Claude default | New test parsing the scripts | New test |
| SI-3 | NEW | Claude default is a member of the Claude catalog | Claude default | New test | New test |
| SI-4 | EXISTING | Codex ids are not in the codex blanked-tier set | Codex catalog | Unchanged | Existing coverage (none found); unchanged |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Stored per-stage model values (including old ids such as `claude-sonnet-5`) are not migrated or rejected; they still pass the allowlist. Env overrides keep precedence.

## 8. Error and failure behavior
Unchanged: non-Claude ids to reviewer-claude.sh warn and use the default.

## 12. Rollback
Revert the three source edits and the new test file.

## 14. Non-goals
Changing Codex/Kimi lists; validating ids against the live API; migrating stored configs; changing the allowlist; adding grouping/sub-headers to the picker.

## 15. Assumptions
The catalog stays a single group named "Claude". The order in the request is the display order.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | MODEL_CATALOG_CLAUDE contains exactly these (label,id) pairs in order and no others: Claude Haiku 5.5/claude-haiku-5-5; Claude Sonnet 5.5/claude-sonnet-5-5; Claude Opus 5.5/claude-opus-5-5; Claude Fable 5.1/claude-fable-5-1; Claude Fable 5/claude-fable-5; Claude Opus 4.8/claude-opus-4-8; Claude Opus 4.7/claude-opus-4-7; Claude Sonnet 4.6/claude-sonnet-4-6; Claude Opus 4.6/claude-opus-4-6; Claude Opus 4.5/claude-opus-4-5-20251101; Claude Haiku 4.5/claude-haiku-4-5-20251001; Claude Sonnet 4.5/claude-sonnet-4-5-20250929. | New Python test asserts the flattened catalog equals this list. |
| AC-2 | DEFAULT_MODEL_FOR_RUNNER['claude'], stagegate.sh DEFAULT_MODEL and reviewer-claude.sh DEFAULT_MODEL fallback are all `claude-sonnet-5-5`, and that id is in the Claude catalog. | New Python test imports uncle_tui and parses both scripts, asserting equality. |
| AC-3 | Every Claude catalog id passes reviewer-claude.sh's allowlist `claude*\|opus*\|sonnet*\|haiku*`. | New test extracts the case pattern from reviewer-claude.sh and matches each id (fnmatch), also running the script's pattern via bash case for each id. |
| AC-4 | The comment above DEFAULT_MODEL_FOR_RUNNER no longer claims the Claude default is the "opus" tier alias and describes the actual default. | Inspection of uncle_tui.py comment; test asserts no 'opus" is the tier alias' wording. |
| AC-5 | Existing tests pass and Codex/Kimi catalogs and defaults are unchanged. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh compared with driver baseline. |

