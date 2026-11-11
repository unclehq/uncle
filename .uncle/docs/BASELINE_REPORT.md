# Baseline: Issue 243 `uncle --revalidate`

Omitted sections: Reproduction (feature, not bug); Existing failures (none documented in repo; driver baseline is authority)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`. Add per-stage input fingerprints and `uncle --revalidate [--dry-run]` that reuses stages with unchanged inputs and re-runs changed ones plus downstream.

## 2. Repository architecture
Shell drivers (`scripts/change-workflow.sh` 5145 lines, `scripts/stagegate.sh` 7176) plus Python helpers in `scripts/lib/`. `uncle` is the CLI entry (1181 lines). Tests: shell suites via `scripts/run-shell-tests.sh`, Python suites `scripts/tests/*-test.py` via `scripts/run-python-tests.sh`; default tier is `scripts/tests/critical-suites.txt`.

## 3. Relevant code paths
**Working tree already holds an uncommitted first draft of this feature** (not in HEAD 5d93294): `scripts/lib/revalidate.py` (315 lines: stage table `_TABLE` l.34-48, `input_hash` l.97, `plan` l.170, `default_runner` l.227, `run` l.247, `main` l.296), `scripts/tests/revalidate-test.py`, `scripts/tests/revalidate-integration-test.py`, `uncle` flag parsing l.261-342 and help l.73,118, `change-workflow.sh` `revalidate_record` l.~580, `UNCLE_REVALIDATE_RESUME` entry l.~3924, gate stop (exit 75), record calls at PLAN/ADVERSARIAL_REVIEW/IMPLEMENT only; `stagegate.sh` `revalidate_record IMPLEMENT` l.~5053; README +11 lines; `critical-suites.txt` +revalidate, revalidate-integration. Existing pieces: green-check fingerprint `change-workflow.sh` l.1185-1214, `scripts/lib/tree_fingerprint.py`, `project_paths.py`, `uncle-verify.py`, approvals `.uncle/workflow/approvals/*.sha256`.

## 4. Current observable behavior (HEAD plus draft)
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle` other startup options | unchanged parsing | uncle l.261-342 | Yes |
| B-2 | green check unchanged tree | skipped via fingerprint | change-workflow.sh l.1201-1214 | Yes |
| B-3 | `uncle verify` | compares attestation/tree, runs nothing | uncle-verify.py | Yes |
| B-4 | `uncle --revalidate` (draft) | prints plan rows, runs changed stages by resuming driver | revalidate.py `run` | Modify/complete |
| B-5 | stage never recorded (draft) | row `skip`, not run | `plan` | UNRESOLVED vs spec: unrecorded stage should count as changed only if run previously |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Approvals/attestation written only by gates/publish | driver gates | shell gate suites | Medium |
| I-2 | Protected verification paths hashed and compared | verification manifest | existing shell suites | Medium |
| I-3 | Unrelated startup flags stay exclusive | uncle l.261-281 | startup-option suites | Medium |

## 6. Contracts
State dir `.uncle/workflow/stage-fingerprints/<STAGE>.json` (draft; fields stage, hash, inputs, status, time). Exit codes: 0 ok, 1 failed/needs-review, 2 no state/no passes; driver exit 75 at reopened gate, 3 blocked.

## 7. Existing automated coverage
Draft suites: revalidate-test.py (fingerprint, plan, run), revalidate-integration-test.py (23 test defs total across both). Registered in critical-suites.txt. Shell and Python runners use separate temp dirs and no shared ports, so they are grouped.

## 9. Baseline test results
Commands from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (documented in CLAUDE/prompt contract). No results run here; driver baseline at `.uncle/workflow/green-check.baseline.tsv` is authority. Some Python suites may already fail on clean checkout.

## 12. Likely change surface
`scripts/lib/revalidate.py`, `uncle`, driver record hooks, tests, README.

## 13. Regression-sensitive components
Startup flag parsing in `uncle`; driver state machine resume and gates in change-workflow.sh; stagegate IMPLEMENT success path.

## 14. Outside the change
`uncle verify`, approval writing, attestation, publish, code rewriting.

## 15. Unknowns and assumptions
- Draft records only 3 stages (PLAN, ADVERSARIAL_REVIEW, IMPLEMENT); others never recorded. Assumed: add record calls for other stage success points where cheap.
- README line in `run` is gated on a `readme` field in records; whether `record` writes it must be confirmed (rec: `record` l.149).
- Assumption: Uncle version change counts via `prompt` input (driver scripts hash).

## 16. Risk
High: false reuse (R-1); medium: resume of driver via state file may mis-order; medium: draft is unreviewed.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- revalidate
bash scripts/run-python-tests.sh -- revalidate-integration
```

