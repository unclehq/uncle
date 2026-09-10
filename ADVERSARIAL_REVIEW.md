## AR-001: Normal completion cannot reach PR creation

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md:Motivation.1; CHANGE_SPEC.md:AC-1; CHANGE_PLAN.md:§12,P-1,P-5,T-3; scripts/change-workflow.sh:1653,1770 |
| Failure | The planned clean-tree/published-HEAD prerequisite rejects completion with uncommitted implementation and audit files; T-3 accepts that rejection without proving an ordinary workflow can produce the required PR. |
| Fix | Add a resumable commit/publish handoff before PR creation, including feature-branch preparation when starting on the default branch. |
| Verify | Start with a clean default-branch checkout, complete a source edit and audit, and require a PR containing that edit after the handoff. |

## AR-002: Audit eligibility does not bind the PR contents

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md:Motivation.2–3; CHANGE_SPEC.md:I-1,I-6; CHANGE_PLAN.md:§7,§11,P-3,P-5,T-1; scripts/lib/issue-close.sh:155; scripts/change-workflow.sh:380 |
| Failure | A clean, published branch can change after audit or during title entry while FINAL_AUDIT.md retains its hash; the planned gate and checkout lock still permit a PR containing unreviewed code, and T-1 checks only creation/body. |
| Fix | Bind eligibility to the reviewed tree and intended remote head, then revalidate after prompts and before creation. |
| Verify | Replace or advance the branch after audit and during the prompt; require rejection despite an unchanged audit hash and clean tree. |

## AR-003: Completion has no recoverable PR outcome

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_SPEC.md:AC-1; CHANGE_PLAN.md:A-2,§7,§12,R-2,T-3; scripts/change-workflow.sh:504,1782; scripts/from-issue.sh:113 |
| Failure | A failed direct run without STAGEGATE_RUN_ID cannot reclaim its sentinel verdict on retry, while a timeout after server success leaves no distinguishable PR outcome; T-3 lacks recovery sequences for either case. |
| Fix | Persist recoverable ownership and PR identity; reconcile remote outcomes before retrying instead of treating every failure as terminal or every rerun as creation. |
| Verify | Test failure then recovery without injected run IDs, server success followed by timeout, and reruns after success; require one discoverable PR. |

## AR-004: PR repository and fork head are unspecified

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md:Motivation.1,3; CHANGE_PLAN.md:§8,P-5,T-1,M-1; scripts/from-issue.sh:262; [gh_pr_create:--head,--repo](https://cli.github.com/manual/gh_pr_create) |
| Failure | The planned command supplies neither a target repository nor a fork-qualified head, so an upstream issue with work published only to a fork can fail or select the wrong branch; T-1 does not assert repository identity. |
| Fix | Resolve and validate base repository, default branch, head repository, and branch explicitly; pass the corresponding repository and head selectors. |
| Verify | Use upstream and fork branches with identical names but different commits; require the intended base repository and exact fork head. |

## AR-005: Preserved audit tests encode obsolete behavior

| Field | Value |
|---|---|
| Severity | Medium |
| References | CHANGE_SPEC.md:AC-5; BASELINE_REPORT.md:F-1; CHANGE_PLAN.md:P-6,T-2,§17,R-3; scripts/tests/close-flow-test.sh:93,218,694; scripts/change-workflow.sh:1820; scripts/lib/audit-findings.py:121 |
| Failure | Inspection widened to audit-findings.py because F-1 reaches an omitted Python dependency: fixtures omit that helper and blocking findings, while assertions expect the old override path, allowing fixture failures to obscure changed close eligibility. |
| Fix | Repair fixtures and baseline expectations before extraction; explicitly classify the existing per-finding acceptance path that converts NOT_READY to effective READY. |
| Verify | Require isolated tests for EOF, retained blockers, accepted findings, and resulting close/PR eligibility; reject unexplained failures or blanket expectation updates. |

## Blocking findings
AR-001–AR-005: resolve.

## Regression risks
AR-002–AR-005: gate approval.

## Recommended simplifications
AR-003: reconcile through one recovery path.

## Required test additions
AR-001–AR-005: required.

## Overall assessment
Reject pending corrections.