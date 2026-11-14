# Baseline report — issue 267

Omitted sections: Reproduction result (not run; cause is deterministic from code and the request's log); API/schema contracts (only one internal exit-code contract, in section 6).

## 1. Change-request summary
CHANGE_REQUEST.md (issue 267): an updated plan stops with `updated-plan: writer attempts exhausted` although every writer succeeded. The merge refuses because the plan names no test files by name; `scripts/check-*.sh` and `scripts/run-defects.sh` are not recognised. Three fixes requested: (1) derive protected paths from files the verification commands execute when none are named; (2) the single-pass Markdown project-plan fallback produces `protected_verification_paths`; (3) a merge refusal gets its own stop reason.

## 2. Repository architecture
Shell drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`) call Python helpers in `scripts/lib/`. Updated-plan writers produce edit packets; `updated_plan_ops.py merge` combines them; `model-jobs.sh` holds shared stop helpers. Tests: `scripts/tests/*-test.py` (runner `scripts/run-python-tests.sh`) and `scripts/tests/*-test.sh` (runner `scripts/run-shell-tests.sh`); both default to the tier listed in `scripts/tests/critical-suites.txt`.

## 3. Relevant code paths
| Path | Lines | Role |
|---|---|---|
| scripts/lib/updated_plan_fast_path.py | 65-109 | `PATH_TOKEN`, `TEST_DIRS`, `NOT_CODE`, `TEST_NAME`, `is_test_path`, `derive_protected_paths` (name/dir recognition only) |
| scripts/lib/updated_plan_ops.py | 696-714, 936-950, 954-960, 1281-1283 | `owned_protected_paths`; merge raises `Conflict` at 947 when derivation empty; `main` maps Conflict/PlanError/ValueError/OSError to exit 1 |
| scripts/lib/updated_plan_edits.py | 767 | second `Conflict('no writer supplied protected_verification_paths')` in the edits merge |
| scripts/lib/publish_agent_artifact.py | 140-200 | updated-plan publish also calls `derive_protected_paths`, then falls back to base plan, then raises ValueError |
| scripts/stagegate.sh | 2984, 3117, 3119 | merge failure -> `workflow_writer_exhausted updated-plan` |
| scripts/lib/model-jobs.sh | 186, 210-214 | `workflow_terminal_failure` keys on `updated-plan-writers-exhausted` flag; `workflow_writer_exhausted` writes flag, `stop-reason` `<stage>: writer attempts exhausted`, stderr line |
| scripts/lib/plan_context.py | 95-112 | Markdown plan -> payload; protected paths only read from a fenced block when `protected=True` |
| scripts/stagegate.sh | 4864 | project-plan falls back to single-pass Markdown plan |
| scripts/change-workflow.sh | 3057 | change-workflow's own writers-exhausted block (not the merge path in the request) |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Plan names test files by name/dir | Those are derived as protected paths | fast_path 81-109; tests ops-test:160-180 | Yes |
| B-2 | Derivation empty, no writer paths | `Conflict` -> merge exit 1 | ops 946-947 | No (modify) |
| B-3 | Merge exit nonzero | stop-reason `updated-plan: writer attempts exhausted`, flag file created | stagegate 3119; model-jobs 210 | Partly: genuine writer exhaustion unchanged |
| B-4 | Writer attempts truly exhausted | same stop-reason | stagegate 2984 | Yes |
| B-5 | Derived paths filtered to those a step `Owns:` | kept; broad fallback if none owned | ops 696-720 | Yes |
| B-6 | Paths ending .json/.lock, dot/abs/`..`/build dirs | excluded | fast_path 98-100 | Yes |
| B-7 | Markdown project-plan fallback | JSON payload has no `protected_verification_paths` | request cause 1; plan_context 108 | No (modify) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Protected paths are repository-relative, no `..`, no generated/build dirs | fast_path 98-100; artifact_json 65-83 | updated-plan-ops-test | High |
| I-2 | A protected path is owned by an implementation step (when any are owned) | ops 696; publish_agent_artifact 185-195 | updated-plan-ops-test | Medium |
| I-3 | A merge/publish never silently emits an updated plan with empty protected paths | ops 947; edits 767; publish 198 | updated-plan-ops-test | Medium |
| I-4 | Terminal stop on writer exhaustion is recognised via flag file | model-jobs 186 | updated-plan-writer-retries-test | Medium |

## 6. Interface contracts
`updated_plan_ops.py merge` exit codes: 0 ok, 3 needs resolution, 5 bad groups (check), 1 any refusal/error. `stop-reason` file in `$STATE_DIR` is a one-line human string read by the TUI/relay; no schema.

## 7. Existing automated-test coverage
`scripts/tests/updated-plan-ops-test.py` (derive_protected_paths, merge), `updated-plan-fast-path-test.py`, `updated-plan-writer-retries-test.py` and `updated-plan-nested-section-test.py` (the last two are in critical-suites.txt; ops and fast-path are NOT in the default tier and must be named explicitly). 62 shell suites; `cancel-stop-reason-test.sh` covers a different stop reason. Python and shell runners use separate temp dirs and no shared ports, so they may run in parallel (parallel group 1 2).

## 8. Exact build and test commands
See `verification_commands` field.

## 9. Baseline test results
Sources: `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh` (documented in the stage instructions and the scripts themselves). Not executed here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Known pre-existing failures: some Python suites already fail on a clean checkout (per runner notes); not enumerated here. The three per-suite commands name suites outside the default tier; two of them (the new suites) do not exist in the baseline tree and are expected to report no such suite until the change lands.

## 10. Existing failures/flakiness
None documented beyond section 9.

## 12. Likely change surface
fast_path.py, ops.py, edits.py (line 767), publish_agent_artifact.py (inherits via derive), plan_context.py or the project-plan fallback ingest, stagegate.sh merge call sites, model-jobs.sh, tests.

## 13. Regression-sensitive components
B-1/B-5/B-6 derivation (a broader derivation could protect files that steps do not own); the writer-exhausted flag consumed by `workflow_terminal_failure`; plan JSON validators (`artifact_json.py:414`) if the project-plan payload gains a field.

## 14. Outside the change
Writer prompts, resolver logic, plan schema for typed JSON path, change-workflow.sh's own exhausted message, approval gates.

## 15. Unknowns and assumptions
- A1: Python runner accepts `-- <name>` per command; shell runner likewise (usage text confirms `-- suite ...`; suite-name form without `-test.sh` assumed from Python convention).
- A2: whether `artifact_json.py` accepts `protected_verification_paths` on a project-plan payload is unverified; implementer must check (risk R-B).
- A3: change-workflow.sh has no equivalent merge call for this refusal (3057 is the writer failure branch); implementer greps once to confirm.

## 16. Initial risk assessment
Low-medium. Derivation heuristic may over- or under-include; stop-reason string is read by external relays, so keep the `updated-plan:` prefix.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- updated-plan-ops
bash scripts/run-python-tests.sh -- updated-plan-fast-path
bash scripts/run-python-tests.sh -- plan-context-protected
bash scripts/run-shell-tests.sh -- updated-plan-merge-conflict
```

## Parallel verification groups

```text
1 2
```

