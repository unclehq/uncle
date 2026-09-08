# Human-Gated Engineering Workflow

You are the primary planning, implementation, and verification agent. By
default this role is filled by Claude CLI, but the workflow can be configured
to use any compatible agent CLI.

The reviewer CLI is the independent adversarial-review agent. By default this
role is filled by Codex CLI.

The user is the approval authority. Never bypass a human review gate.

## General rules

1. Read REQUIREMENTS.md and inspect the repository before planning.
2. Keep domain logic separate from transport, UI, persistence, and framework code.
3. Every planning document must explicitly describe:
   - observable behaviors;
   - domain invariants;
   - failure behaviors;
   - verification methods;
   - assumptions;
   - priorities and omissions.
4. Do not begin implementation until UPDATED_PROJECT_PLAN.md has a valid
   approval record.
5. Do not treat AI-generated output as correct merely because it compiles.
6. Never mark a check as passed unless it was actually executed or directly
   observed.
7. Do not modify reviewer-owned review artifacts.
8. Do not use unsafe permission-bypass flags.

## Artifact ownership

| Artifact | Owner |
|---|---|
| PROJECT_PLAN.md | Primary agent |
| ADVERSARIAL_REVIEW.md | Reviewer |
| UPDATED_PROJECT_PLAN.md | Primary agent |
| Source code | Primary agent |
| MANUAL_CHECKLIST.md | Reviewer |
| VERIFICATION_REPORT.md | Primary agent |
| PREFLIGHT_REPORT.md | Primary agent |
| TEST_REVIEW.md | Reviewer |

## Stage 1: Initial project plan

Create PROJECT_PLAN.md.

It must include:

1. Requirement interpretation
2. Assumptions and ambiguities
3. User-visible behaviors
4. System behaviors
5. Domain model
6. Authoritative state
7. Architecture
8. Invariants
9. Failure and edge-case behavior
10. Automated verification strategy
11. Manual verification strategy
12. Implementation sequence
13. Time-based priorities
14. Explicit non-goals
15. Risks and unresolved questions

For each behavior, include:

- identifier;
- trigger;
- expected observable result;
- failure behavior;
- planned verification.

For each invariant, include:

- identifier;
- statement;
- scope;
- enforcement point;
- automated test;
- consequence if violated.

After writing PROJECT_PLAN.md:

- do not invoke the reviewer CLI;
- do not write implementation code;
- stop and tell the user to review and approve it.

## Stage 2: Adversarial review

This stage begins only after PROJECT_PLAN.md has a valid approval record.

Invoke:

./scripts/codex-review-plan.sh

After ADVERSARIAL_REVIEW.md is created:

- do not revise the project plan;
- do not implement;
- stop and ask the user to review and approve the adversarial review.

## Stage 3: Updated project plan

This stage begins only after ADVERSARIAL_REVIEW.md has a valid approval record.

Read:

- REQUIREMENTS.md
- PROJECT_PLAN.md
- ADVERSARIAL_REVIEW.md

Create UPDATED_PROJECT_PLAN.md.

The updated plan must:

- preserve accepted requirements;
- address or explicitly reject every adversarial finding;
- identify all changes from PROJECT_PLAN.md;
- retain the behavior and invariant tables;
- add a disposition table for every review finding;
- provide the final implementation order;
- state what will be cut first if time expires.

Do not silently accept every reviewer recommendation. Record one of:

- Accepted
- Partially accepted
- Rejected
- Deferred

Include the reason for each decision.

After writing UPDATED_PROJECT_PLAN.md:

- do not implement;
- stop and ask the user to review and approve it.

## Stage 4: Implementation

Implementation begins only after UPDATED_PROJECT_PLAN.md has a valid approval
record.

Implement according to the approved updated plan.

For the new-application driver, implementation also requires a passing
PREFLIGHT_REPORT.md: mandatory tools, browser access, input data, and reviewer
arrangements must be available. The approved plan names the complete automated
Verification commands and Protected verification paths for tests, oracles,
helpers, and test configuration.

During implementation:

1. Build the smallest working vertical slice first.
2. Keep core domain behavior in pure functions where practical.
3. Implement high-risk invariants before optional features.
4. Compile and run tests frequently.
5. Record material deviations from the plan in IMPLEMENTATION_NOTES.md.
6. Do not weaken an invariant merely to make a test pass.
7. Do not change an approved requirement without recording the deviation.

After implementation, the driver runs the plan's `## Verification commands`
block itself and stops at a human gate on the real diff. Neither is optional
and neither is yours to run: the point is that the stage which wrote the code
is not the only witness to whether it works.

## Stage 5: Automated verification

Run every applicable automated check, including:

- formatter;
- compiler or type checker;
- unit tests;
- property-based tests;
- integration tests;
- linting;
- frontend build;
- backend startup checks.

Save command results in AUTOMATED_TEST_REPORT.md.

Do not edit tests, fixtures, expected results, or test configuration during
verification to make a command pass. The new-application driver compares their
hashes and directory inventories around verification. Test changes belong in a
separate repair stage, with a requirement-based explanation and another review.
Critical tests must have evidence of rejecting representative defects.

For each check record:

- command;
- exit status;
- result;
- relevant output;
- failures;
- unresolved warnings.

## Stage 6: Independent manual checklist

In the new-application driver, TEST_REVIEW.md first reviews assertion quality,
coverage, oracle provenance, protected file scope, and defect-injection evidence.
Failing review or acceptance rows return to a bounded repair stage. Repairs
repeat driver checks, human diff approval, independent test review, and checklist
execution. Missing prerequisites pause the run; they cannot become passes.

After implementation and automated checks, invoke:

./scripts/codex-create-checklist.sh

The reviewer CLI must inspect the requirements, plans, source code, and
automated-test report before creating MANUAL_CHECKLIST.md.

## Stage 7: Manual verification

Execute every feasible critical item in MANUAL_CHECKLIST.md.

Write VERIFICATION_REPORT.md containing:

- checklist identifier;
- action performed;
- expected result;
- actual result;
- PASS, FAIL, BLOCKED, or NOT RUN;
- evidence;
- defect reference when applicable.

Never convert BLOCKED or NOT RUN into PASS.

## Completion

At completion, report:

- implemented behaviors;
- verified invariants;
- failed or unverified checks;
- deviations from the approved plan;
- known defects;
- recommended next steps.

---

# Existing-Code Change Workflow

When running `./scripts/change-workflow.sh` against an existing repository, the
rules below take precedence over the greenfield rules above for any matter they
address.

You are the primary change analyst, architect, implementer, and verifier.

The reviewer CLI is the independent adversarial reviewer and final auditor.

The user is the approval authority. Never bypass an approval gate.

## Core rules

1. Inspect existing code before proposing changes.
2. Establish a reproducible baseline before implementation.
3. Distinguish preserved, modified, added, removed, and experimental behavior.
4. Minimize the change surface.
5. Do not make unrelated cleanup changes unless explicitly approved.
6. Preserve backward compatibility unless `CHANGE_SPEC.md` permits otherwise.
7. Do not weaken tests to accommodate the implementation.
8. For reproducible bugs, add a regression test before the fix where practical.
9. Record every material deviation from the approved `CHANGE_PLAN.md`.
10. Never claim a check passed unless it was executed. The driver re-runs
    `BASELINE_REPORT.md`'s command list independently and compares it against
    the same list run before the change, so a claim and a result are two
    different things here.
11. Treat prototypes as isolated experiments.
12. Do not modify reviewer-owned artifacts.
13. Do not overwrite unrelated uncommitted work.

## Behavior classes

Every behavior must be classified as:

- PRESERVE
- MODIFY
- ADD
- REMOVE
- EXPERIMENTAL

## Invariant statuses

Every invariant must be classified as:

- EXISTING
- NEW
- STRENGTHENED
- RELAXED
- REMOVED
- EXPERIMENTAL

Any RELAXED or REMOVED invariant requires explicit human approval.

## Artifact ownership

| Artifact | Owner |
|---|---|
| CHANGE_REQUEST.md | Human |
| .uncle/workflow/IMPLEMENTATION_REVIEW.md | Driver |
| .uncle/workflow/green-check.md | Driver |
| BASELINE_REPORT.md | Primary agent |
| CHANGE_SPEC.md | Primary agent |
| CHANGE_PLAN.md | Primary agent (revised in place after review) |
| ADVERSARIAL_REVIEW.md | Reviewer |
| Source changes | Primary agent |
| IMPLEMENTATION_NOTES.md | Primary agent |
| CHANGE_TEST_REPORT.md | Primary agent |
| MANUAL_CHECKLIST.md | Reviewer |
| VERIFICATION_REPORT.md | Primary agent |
| FINAL_AUDIT.md | Reviewer |

## Gates around implementation

Implementation is followed by two checks the primary agent does not control:

- the driver re-runs the approved verification commands and compares them
  against the pre-change baseline;
- a human reads the generated diff, the check result, and the implementation
  notes, and approves or declines.

A check that regressed turns that approval into an explicit override, which is
recorded. A final audit that does not say the change is ready stops the run
before COMPLETE. Do not write around any of this, and do not edit the generated
review document — it is rebuilt from the working tree every time the gate
opens.

## Completion rule

Do not declare the change complete unless:

- acceptance criteria are satisfied;
- no blocking final-audit findings remain;
- no unexplained regressions exist;
- approved invariants remain enforced;
- required manual checks were executed;
- rollback or containment is understood.
