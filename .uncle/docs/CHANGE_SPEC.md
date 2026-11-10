# Change spec — Issue 226

Omitted sections: Performance (none); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Bug fix (robustness) with docs.

## 2. Problem statement
A single unrecognized `supervision.*` key disables all corrections; in unattended hosted runs nobody sees why.

## 3. Current behavior
Baseline B-1, B-7.

## 4. Desired behavior
Unknown `supervision.*` keys are ignored with a warning; supervision stays on with remaining valid settings. Recognized keys with invalid values still disable. In hosted (unattended) runs, configuration warnings and errors are printed to stderr at supervised-run start, before the first paid stage. Docs state hosted supervision reads OPENAI_BASE_URL, OPENAI_API_KEY and SEREN_MODEL/UNCLE_MODEL.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | unknown `supervision.X` key | disables all corrections | ignored; warning `ignoring unknown supervision key: supervision.X`; errors empty; enabled | AC-1, AC-2 |
| B-2 | PRESERVE | recognized key, invalid value | disabled | unchanged, also when an unknown key is present | AC-3 |
| B-3 | PRESERVE | valid config | enabled, no errors | unchanged, no warnings | AC-6 |
| B-4 | PRESERVE | hosted defaults / missing model error | as baseline | unchanged | AC-6 |
| B-6 | MODIFY | CLI `config` | stderr reason on errors, exit 1 | additionally prints each warning to stderr; exit 0 when only warnings; lines output unchanged | AC-4 |
| B-7 | MODIFY | supervised run starts with `UNCLE_HOSTED=1` and warnings or errors | silent | each warning and the disabled reason printed once to stderr before the command runs | AC-5 |
| B-8 | ADD | reading docs | no hosted guidance | README.md and docs/supervision.md name OPENAI_BASE_URL, OPENAI_API_KEY, SEREN_MODEL/UNCLE_MODEL and say no supervision.base_url is needed | AC-7 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | invalid value of recognized key never replaced by default | load_config | load_config | AC-3 |
| I-2 | EXISTING | any entry in errors disables corrections | Config | disabled_reason | AC-3 |
| I-5 | NEW | unknown keys never reach errors and never disable supervision | load_config | load_config | AC-1 |
| I-6 | NEW | warnings never alter values or enablement | Config | Config.warnings is informational | AC-2 |

No RELAXED or REMOVED invariants. I-2 is not relaxed: unknown keys are no longer errors; the error set for recognized keys is unchanged.

## 7. Compatibility
Config.errors, disabled_reason, lines keep their types. New `Config.warnings` list defaults to empty (constructor argument optional).

## 8. Error and failure behavior
A typo of a recognized key (e.g. supervision.max_interventons) is now a warning, not a disable; accepted per the request. Duplicate keys: first wins, as before.

## 10. Security
Warnings name the key only, never the value (a value such as an api key must not be echoed).

## 12. Rollback
Revert the commit; no persisted state.

## 14. Non-goals
Supporting base_url/api_key keys; changing hosted defaults; TUI redesign; aborting runs on config errors.

## 15. Assumptions
- `.uncle/config.example` is absent from this tree and the build script is outside this repo; requests 3 (config.example part) and 4 are not deliverable here and are recorded as deviations. Docs go in README.md and docs/supervision.md.
- "Unattended" is detected as UNCLE_HOSTED=1; request option (b) (stderr) is chosen over stopping the run.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | load_config on a file containing an unknown supervision key plus valid keys returns errors == [] and enabled with the valid settings applied; disabled_reason is ''. | supervisor-test.py new test |
| AC-2 | The unknown key is reported in Config.warnings as 'ignoring unknown supervision key: supervision.X' without its value; values equal those of the same file without the key. | supervisor-test.py new test |
| AC-3 | A recognized key with an invalid value still produces an error and disabled_reason (all existing invalid cases except the bogus one), including when an unknown key is also present; no default is substituted. | supervisor-test.py updated roundtrip test |
| AC-4 | `supervisor.py config` with only an unknown key exits 0, prints the lines to stdout and the warning to stderr; with an invalid recognized value still exits 1. | supervisor-test.py CLI test |
| AC-5 | With UNCLE_HOSTED=1, starting a supervised run with a config containing supervision.base_url prints the warning to stderr once before the wrapped command runs and supervision stays enabled; with a recognized invalid value the disabled reason is printed to stderr. | supervisor-test.py hosted run test |
| AC-6 | Valid configs and hosted defaults behave as before: no warnings, existing supervisor, hosted-mode and default-runner suites pass. | bash scripts/run-python-tests.sh and bash scripts/run-shell-tests.sh |
| AC-7 | README.md and docs/supervision.md state that in hosted mode supervision reads OPENAI_BASE_URL, OPENAI_API_KEY and SEREN_MODEL/UNCLE_MODEL and needs no supervision.base_url, and that unknown supervision keys are ignored with a warning. | grep of both files for those names |

