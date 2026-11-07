# Change Spec — Issue 180
Omitted sections: Performance (none); Security beyond I-N (no new surface); Migration (none); Prototype isolation (n/a)

## 1. Change type
Feature / consistency fix.

## 2. Problem statement
`aws-bedrock` is selectable in the TUI but not in the `uncle` shell-fallback Configure, which also lacks model choice, apply-to-all and connection setup for it. Baseline B-1, B-2, B-5, B-6.

## 4. Desired behavior
Every runner picker offers `aws-bedrock` beside claude, codex, kimi, self-hosted. Selecting it gives model choice from Bedrock-configured models and apply-to-all using the Bedrock connection and `aws-bedrock-keys.json`. A selection made in one surface reads correctly in the other (shared config file).

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | MODIFY | Fallback `r`, enter `aws-bedrock` (agent or reviewer stage) | Rejected | Accepted; `<stage>.runner aws-bedrock` written; stage's model kept | AC-1 shell test |
| BH-2 | MODIFY | Fallback shows a Bedrock-configured stage | Shown as `self-hosted`, Self hosted prompts | Shown as `aws-bedrock` with Bedrock prompts (`Set [r]unner [m]odel, [a]pply AWS Bedrock to all stages...`) | AC-2 |
| BH-3 | MODIFY | Fallback `m` on Bedrock stage | No model choice (or Self hosted list) | Lists models from `aws-bedrock-keys.json`; selection written to `<stage>.model`; invalid choice leaves config unchanged | AC-2 |
| BH-4 | MODIFY | Fallback `a` on Bedrock stage | Refused | All stages get `runner aws-bedrock`, model, base_url; Bedrock token copied in `aws-bedrock-keys.json` to every stage; self-hosted-keys.json untouched | AC-2, AC-3 |
| BH-5 | MODIFY | TUI apply-to-all on Bedrock stage | Refused | Same effect as BH-4, using Bedrock key store | AC-3 py test |
| BH-6 | ADD | Fallback Configure menu | No Bedrock connection setup | Item "Configure AWS Bedrock" (URL, hidden token, model discovery) writing `aws-bedrock-keys.json` | AC-4 |
| BH-7 | MODIFY | Fallback `d` on a Bedrock stage | Clears self-hosted key | Also clears that stage's Bedrock key; Self hosted behavior unchanged | AC-2 |
| BH-8 | PRESERVE | Self hosted/claude/codex/kimi fallback flows; `uncle_stage_runner`; TUI Bedrock picks | B-3, B-4, B-8, B-9 | Unchanged | existing suites + AC-5 |
| BH-9 | MODIFY | Fallback runner prompt text | Lists installed runners only | Lists installed runners plus `aws-bedrock` | AC-1 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | Bedrock token only in aws-bedrock-keys.json; Self hosted store never read/written for Bedrock actions and vice versa | key stores | self_hosted.py key_file/save_keys | AC-3 test compares self-hosted-keys.json hash |
| INV-2 | EXISTING | Shell dispatch maps aws-bedrock to self-hosted; others unchanged | stage-config.sh | stage-config.sh:311 | aws-bedrock-dispatch-test.sh |
| INV-3 | EXISTING | `uncle_installed_runners` reflects PATH binaries only | stage-config.sh | :248 | AC-5 |
| INV-4 | NEW | Fallback and TUI write identical config for equal Bedrock selections | config file | shared config keys | AC-6 |
| INV-5 | EXISTING | Token never written to `.uncle/config` or printed | config/stdout | save_keys, getpass/stdin | AC-3 test greps |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Config file format unchanged. Self hosted menu semantics unchanged. Configure menu: Bedrock inserted as item 3 and Miscellaneous becomes 4 (matches TUI order). TUI behavior for existing runners unchanged.

## 8. Error behavior
Unknown runner still rejected with the existing message. Missing/empty Bedrock model list: `m` prints a Bedrock-worded message pointing to Configure AWS Bedrock and writes nothing. `a` without a Bedrock-selected stage prints "Select AWS Bedrock and configure its connection first." and writes nothing.

## 10. Security
Token read hidden, never echoed or placed in config/argv; key file mode 0600 and gitignored via existing `save_keys`.

## 12. Rollback
Revert the commit; no persisted format changes.

## 14. Non-goals
Bedrock wire protocols, discovery logic, dispatch normalization, changing `uncle_installed_runners`, workflow drivers.

## 15. Assumptions
Audit of `self-hosted` special cases is recorded in CHANGE_PLAN (audit table). Menu renumbering is acceptable (assumption; flagged in plan risks).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `aws-bedrock` is accepted at the `uncle` shell-fallback Runner prompt for both an agent stage and a reviewer stage, writes `<stage>.runner aws-bedrock`, and the prompt lists it; invalid names are still rejected. | New shell test drives configure_stage with piped input in a temp config; asserts config contents and rejection message. |
| AC-2 | In the fallback, a Bedrock stage shows as aws-bedrock, `m` chooses a model from `aws-bedrock-keys.json` (invalid choice changes nothing), and `d` clears the stage's Bedrock key. | Same shell test with a fixture aws-bedrock-keys.json containing `__opencode_models__`. |
| AC-3 | Apply-to-all works for Bedrock in the fallback and the TUI: every stage gets runner aws-bedrock, model, base_url and the Bedrock token from aws-bedrock-keys.json; self-hosted-keys.json is byte-identical afterwards; token never appears in `.uncle/config` or output. | Shell test (fallback) plus Python test calling TUI `_apply_opencode_to_all_stages` on a minimal instance; hash and grep assertions. |
| AC-4 | The fallback Configure menu offers a Configure AWS Bedrock item that stores URL/token in aws-bedrock-keys.json via the Bedrock profile, without touching Self hosted keys. | Python test of `self_hosted.py models\|choose-model\|set-key` with the aws-bedrock profile argument; manual fallback walkthrough. |
| AC-5 | Existing Self hosted, claude, codex, kimi behavior is unchanged: aws-bedrock-dispatch-test.sh and all existing shell and Python suites pass; `uncle_installed_runners` output unchanged. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh compared with baseline. |
| AC-6 | A grep audit of `self-hosted` special cases is recorded in the plan with each site marked extended or intentionally Self-hosted-only, and a Bedrock selection made in the fallback is displayed as aws-bedrock by the TUI loader (and vice versa). | Audit table in CHANGE_PLAN; Python test loads a config written by the fallback test into the TUI config reader and asserts stage_runner == aws-bedrock. |
| AC-7 | `docs/aws-bedrock.md` and README runner lists mention aws-bedrock and the shell-fallback Configure path. | grep for aws-bedrock in README.md and docs/aws-bedrock.md. |

