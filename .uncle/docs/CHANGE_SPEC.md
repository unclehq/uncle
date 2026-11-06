# Change spec: issue 172

Omitted sections: Migration (none), Prototype isolation (n/a), Performance (saved work is the point; no limits)

## 1. Change type
Feature.

## 2. Problem
Every build pays for an adversarial review panel, even docs-only, test-only or small builds (baseline B-1).

## 3-4. Current / desired
Current: review always runs. Desired: the classifier may answer `review: skip` for docs/test-only/small; a deterministic floor can veto; a visible zero-finding stub review replaces the review and goes through the normal gate.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Classifier returns review: skip for docs/test-only/small, no risk hits, class not raised, path rule satisfied | Review runs | No panel or primary reviewer runs; stub review written with text `skipped: class <class>, no risk hits`, zero findings | Python unit tests; shell stub test |
| SB-2 | ADD | Skip answered but any floor condition fails | n/a | Full review runs; reason recorded | Python unit tests per condition |
| SB-3 | PRESERVE | Classifier failure, bad answer, WORKFLOW_CLASSIFY=0, forced class | Full review | Full review (B-2,B-3) | Unit + shell test |
| SB-4 | ADD | WORKFLOW_SKIP_REVIEW=0 | n/a | Full review, even when classifier says skip | Unit test |
| SB-5 | ADD | Skip taken | No record | Decision recorded in change-class.json, a run-state marker and the cost ledger (change-workflow) | Test reads files |
| SB-6 | MODIFY | Stub reaches review gate | Real review shown | Gate shows the skip reason; human can decline | Manual + shell test |
| SB-7 | PRESERVE | Class standard/large/risky | Full review | Skip never accepted (class not REDUCIBLE) | Unit test |
| SB-8 | ADD | Stub invalid | n/a | Run stops as a bad review does | Test with corrupted stub |
| SB-9 | PRESERVE | Plan changes after classification | n/a | Skip is honored only if stored plan_sha matches the current plan; else full review | Unit test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | No skip when risk_hits is non-empty | both drivers | change_class.py build | unit test |
| SI-2 | NEW | A skipped review is always visible at the gate and recorded | both drivers | stub text + change-class.json + marker | test |
| SI-3 | EXISTING | Human plan approval and final audit unchanged | both drivers | state machines | shell suites |
| SI-4 | NEW | Any uncertainty (failure, bad answer, disabled, forced, stale plan) runs full review | both drivers | build + driver read | unit/shell |
| SI-5 | NEW | Skip only for REDUCIBLE classes and only when the floor did not raise the model's class | change_class.py | build | unit test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Additive keys in change-class.json; existing consumers unaffected. Stub conforms to adversarial-review schema.

## 8. Failure behavior
Full review on any uncertainty; invalid stub stops the run.

## 10. Security
Security-critical words never skip (SI-1). Raw (unwaived) risk hits count, so a model waiver cannot enable skip.

## 12. Rollback
WORKFLOW_SKIP_REVIEW=0 restores prior behavior; code revert is a self-contained diff.

## 14. Non-goals
Skipping final audit, human gates, or standard/large/risky reviews.

## 15. Assumptions
Updated-plan stage accepts an empty-findings review (to be proven by test). New `small` apps: judgment plus floor; human plan gate remains.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | change_class.py build returns review=skip only when the model answered review: skip, source is model, class is docs/test-only/small, the final class equals the model's class, raw risk_hits is empty, and for docs/test-only every owned file is doc/test respectively. | New Python test with one case per floor condition asserting skip vs full. |
| AC-2 | Skip is rejected (full review) for standard/large/risky, when risk_hits is non-empty even if waived, when the floor raised the class, and when the plan sha is stale. | Python test cases. |
| AC-3 | A classifier failure, unusable answer, WORKFLOW_CLASSIFY=0 or forced class yields a full review. | Python test of finish/fallback/force output plus shell test of classify stage. |
| AC-4 | WORKFLOW_SKIP_REVIEW=0 makes every case produce a full review. | Python test with env set. |
| AC-5 | A skipped review writes canonical ADVERSARIAL_REVIEW.json with zero findings and an overall_assessment containing `skipped: class <class>, no risk hits`, which passes validate_json and renders to .uncle/docs/ADVERSARIAL_REVIEW.md. | Python test running adversarial-context.py --validate-json and --render-json on the stub. |
| AC-6 | Both stagegate.sh and change-workflow.sh, when skip is decided, do not launch the review panel or primary reviewer, write the stub, and proceed through their normal validation and approval gate; otherwise they run the review as before. | Shell test with stubbed runner asserting no reviewer invocation on skip and invocation on non-skip, in both drivers. |
| AC-7 | The skip decision is recorded in change-class.json, a state marker, and the cost ledger row (change-workflow). | Test inspects files after skip. |
| AC-8 | A corrupted stub stops the run like a bad review; final audit and human approval gates are untouched. | Shell test with corrupted stub; existing suites remain green. |
| AC-9 | The updated-plan stage accepts a zero-finding stub review. | Test running the updated-plan validation/input path on the stub review. |
| AC-10 | prompts/classify-change.md documents the optional `review` field and its limits; existing shell and Python suites still pass. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh. |

