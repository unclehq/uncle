# Baseline report: issue 172

Omitted sections: Current API/schema contracts beyond change-class.json (no external API touched); Reproduction (not a bug)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 172): let the classifier skip adversarial review for `docs`, `test-only`, `small` builds, behind a deterministic floor, with a stub review artifact, fail-closed, an off switch, and both drivers.

## 2. Repository architecture
Shell drivers `scripts/stagegate.sh` (new app) and `scripts/change-workflow.sh` (existing code) run a state machine. Both source `scripts/lib/change-class-stage.sh`, which calls `scripts/lib/change_class.py` (features, floor, profile) after a model call using `prompts/classify-change.md`. Output: `.uncle/workflow/change-class.json`. Review artifacts are canonical JSON at `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`, rendered to `.uncle/docs/ADVERSARIAL_REVIEW.md` by `scripts/lib/adversarial-context.py`.

## 3. Relevant code paths
- `scripts/lib/change_class.py:40` REDUCIBLE; `:87` risk_hits_in; `:113` apply_waivers; `:243` features; `:270` deterministic_class; `:300` profile; `:326` merge; `:332` build; `:355` proposal_from; `:392` PROMPT_FOOTER; `:482` main CLI (`get`, `finish`, `force`, `current`, `recheck`).
- `scripts/lib/change-class-stage.sh:22` classify_change_stage (WORKFLOW_CLASSIFY=0 returns early, removing change-class.json; WORKFLOW_CHANGE_CLASS forces); `change_class_recheck`; `change_class_panel`.
- `scripts/change-workflow.sh:3955-4000` CLASSIFY -> ADVERSARIAL_REVIEW -> VALIDATE_ADVERSARIAL_REVIEW; `:2626` run_adversarial_review_panel; `:670` record_cost.
- `scripts/stagegate.sh:5462` classify (app); `:5472` ADVERSARIAL_REVIEW via run_gated_stage (`:5291`); `:4499` the stage body (panel, fast path, validate+render); `:2446` panel.
- `scripts/lib/adversarial-context.py:119` validate_json: accepts empty `findings`, requires nonempty `overall_assessment`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Plan classified docs/test-only/small | Review panel runs with lenses >= requirements+regression | change_class.py:300-324 | Yes unless skip allowed |
| B-2 | WORKFLOW_CLASSIFY=0 | change-class.json removed; every lens runs | change-class-stage.sh:24-27 | Yes |
| B-3 | Classifier fails/bad answer | deterministic fallback profile; review runs | change-class-stage.sh, change_class.py:482 | Yes |
| B-4 | risk_hits non-empty | class risky, all lenses | change_class.py:271 | Yes |
| B-5 | Review written | Validated then human approval gate | change-workflow.sh:3998; stagegate.sh:5483 | Yes |
| B-6 | Empty-findings review | Passes validate_json | adversarial-context.py:119-140 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Classifier can only raise class, never drop required lenses | merge/profile in change_class.py | Not located (UNRESOLVED: no test file naming change_class found by grep) | Medium |
| I-2 | Classifier failure never stops the run | classify stage subshell, fail-open | not located | Medium |
| I-3 | Review artifact must validate or run stops | VALIDATE_ADVERSARIAL_REVIEW | shell suites | Medium |
| I-4 | Human gate and final audit run for every build | state machines | shell suites | High |

## 6. Interface contracts
`change-class.json` (kind change-class): class, floor_class, source, adversarial_lenses, edit_slice, panels, features.risk_hits, plan_sha. Consumers read via `change_class.py get . <key>`. Adding keys is backward compatible.

## 7. Existing automated-test coverage
Shell suites under `scripts/tests` via `scripts/run-shell-tests.sh`; Python suites `scripts/tests/*-test.py` via `scripts/run-python-tests.sh`. Both use separate temp dirs and no shared ports, so they run as one parallel group (per runner documentation).

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh existing in the repo and the stage instructions. Not run here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout per instructions.

## 10. Existing failures/flaky
None documented in repo docs read; see driver baseline.

## 12. Likely change surface
change_class.py, change-class-stage.sh, prompts/classify-change.md, change-workflow.sh ADVERSARIAL_REVIEW state, stagegate.sh ADVERSARIAL_REVIEW state, new test(s).

## 13. Regression-sensitive components
classify stage (runs both drivers); profile()/build() output consumed by panel selection; plan-gate/envelope checks for review; speculative review in stagegate; updated-plan stage consuming a zero-finding review.

## 14. Outside the change
Final audit, human gates, standard/large/risky classes, test-review/checklist panels.

## 15. Unknowns
- UNRESOLVED: whether stagegate has a cost ledger writer equivalent to change-workflow record_cost; plan records the decision in change-class.json plus a state marker for both and the ledger where available.
- Whether the updated-plan stage accepts zero findings is assumed from validate_json and must be tested.

## 16. Risk
Misjudged skip ships without review (mitigated by floor + human gate); wiring skip into a state machine with envelopes/hash checks.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

