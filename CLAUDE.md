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
4. Do not begin implementation until .uncle/docs/UPDATED_PROJECT_PLAN.md has a valid
   approval record.
5. Do not treat AI-generated output as correct merely because it compiles.
6. Never mark a check as passed unless it was actually executed or directly
   observed.
7. Do not modify reviewer-owned review artifacts.
8. Do not use unsafe permission-bypass flags.

## Artifact ownership

| Artifact | Owner |
|---|---|
| .uncle/docs/PROJECT_PLAN.md | Primary agent |
| .uncle/docs/ADVERSARIAL_REVIEW.md | Reviewer |
| .uncle/docs/UPDATED_PROJECT_PLAN.md | Primary agent |
| Source code | Primary agent |
| .uncle/docs/MANUAL_CHECKLIST.md | Reviewer |
| .uncle/docs/VERIFICATION_REPORT.md | Primary agent |
| .uncle/docs/PREFLIGHT_REPORT.md | Primary agent |
| .uncle/docs/TEST_REVIEW.md | Reviewer |

## Stage 1: Initial project plan

Create .uncle/docs/PROJECT_PLAN.md.

It must include:

1. Assumptions and ambiguities
2. User-visible behaviors
3. System behaviors
4. Domain model
5. Authoritative state
6. Architecture
7. Invariants
8. Failure and edge-case behavior
9. Automated verification strategy
10. Manual verification strategy
11. Implementation sequence
12. Explicit non-goals
13. Risks and unresolved questions

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

After writing .uncle/docs/PROJECT_PLAN.md:

- do not invoke the reviewer CLI;
- do not write implementation code;
- stop and tell the user to review and approve it.

## Stage 2: Adversarial review

This stage begins only after .uncle/docs/PROJECT_PLAN.md has a valid approval record.

Invoke:

./scripts/codex-review-plan.sh

After .uncle/docs/ADVERSARIAL_REVIEW.md is created:

- do not revise the project plan;
- do not implement;
- stop and ask the user to review and approve the adversarial review.

## Stage 3: Updated project plan

This stage begins only after .uncle/docs/ADVERSARIAL_REVIEW.md has a valid approval record.

Read:

- REQUIREMENTS.md
- .uncle/docs/PROJECT_PLAN.md
- .uncle/docs/ADVERSARIAL_REVIEW.md

Create .uncle/docs/UPDATED_PROJECT_PLAN.md.

The updated plan must:

- preserve accepted requirements;
- address or explicitly reject every adversarial finding;
- identify all changes from .uncle/docs/PROJECT_PLAN.md;
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

After writing .uncle/docs/UPDATED_PROJECT_PLAN.md:

- do not implement;
- stop and ask the user to review and approve it.

## Stage 4: Implementation

Implementation begins only after .uncle/docs/UPDATED_PROJECT_PLAN.md has a valid approval
record.

Implement according to the approved updated plan.

For the new-application driver, implementation also requires a passing
.uncle/docs/PREFLIGHT_REPORT.md: mandatory tools, browser access, input data, and reviewer
arrangements must be available. The approved plan names the complete automated
Verification commands and Protected verification paths for tests, oracles,
helpers, and test configuration.

During implementation:

1. Build the smallest working vertical slice first.
2. Keep core domain behavior in pure functions where practical.
3. Implement high-risk invariants before optional features.
4. Compile and run tests frequently.
5. Record material deviations from the plan in .uncle/docs/IMPLEMENTATION_NOTES.md.
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

Save command results in .uncle/docs/AUTOMATED_TEST_REPORT.md.

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

In the new-application driver, .uncle/docs/TEST_REVIEW.md first reviews assertion quality,
coverage, oracle provenance, protected file scope, and defect-injection evidence.
Failing review or acceptance rows return to a bounded repair stage. Repairs
repeat driver checks, human diff approval, independent test review, and checklist
execution. Missing prerequisites pause the run; they cannot become passes.

After implementation and automated checks, invoke:

./scripts/codex-create-checklist.sh

The reviewer CLI must inspect the requirements, plans, source code, and
automated-test report before creating .uncle/docs/MANUAL_CHECKLIST.md.

## Stage 7: Manual verification

Execute every feasible critical item in .uncle/docs/MANUAL_CHECKLIST.md.

Checks may be run concurrently, but which checks may overlap is not the
executing agent's call. The reviewer declares `Exclusive resources` and
`Depends on` per check; the driver turns those into ordered groups in
`.uncle/workflow/checklist-groups/`, where each group is a consecutive run of
the checklist that shares no declared resource. Finish a group before starting
the next. A checklist that declares nothing, or whose declarations do not
parse, runs one check at a time — never on a grouping the executing agent
invented, because two checks fighting over a port produce a FAIL that reads
like a product defect.

Write .uncle/docs/VERIFICATION_REPORT.md containing:

- checklist identifier;
- action performed;
- expected result;
- actual result;
- PASS, FAIL, BLOCKED-SETUP, BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE, or NOT RUN;
- evidence;
- defect reference when applicable.

Never convert a blocked or NOT RUN check into PASS.

A blocked check must say which kind of blocked it is, because the three are
not the same problem and the driver acts on them differently:

- `BLOCKED-SETUP` -- one action would make it available; name the action. The
  driver lists these and pauses so they can be done and the stage rerun.
- `BLOCKED-HUMAN` -- it waits on a person; name who and for what. This is what
  a human-gated workflow is for, not a fault, so the run continues to its
  audit rather than stopping. It still cannot complete on an unsigned required
  check.
- `BLOCKED-IMPOSSIBLE` -- this environment cannot perform it as specified, and
  no effort will change that; name the limit. The driver stops and points at
  the plan, because the fix is to amend the plan or the requirement.

A bare `BLOCKED` is read as `BLOCKED-SETUP`, which claims the problem is
arrangeable. Do not leave it unclassified when it is not.

Checks that cannot be performed here should be caught at preflight, where the
plan is still cheap to change: the driver publishes what preflight proved to
`.uncle/workflow/preflight-capabilities/`, and the checklist must cite the id
behind any capability its checks need.

A required check marked BLOCKED-IMPOSSIBLE stops the run. If it genuinely
cannot be verified in this environment, the operator may record a waiver --
a typed reason kept with the run -- and the run continues to its audit. A
waiver never turns the check into a PASS; the report still says it was not
performed.

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
6. Preserve backward compatibility unless `.uncle/docs/CHANGE_SPEC.md` permits otherwise.
7. Do not weaken tests to accommodate the implementation.
8. For reproducible bugs, add a regression test before the fix where practical.
9. Record every material deviation from the approved `.uncle/docs/CHANGE_PLAN.md`.
10. Never claim a check passed unless it was executed. The driver re-runs
    `.uncle/docs/BASELINE_REPORT.md`'s command list independently and compares it against
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

## Stages

### Stage 1: Change plan

In a single runner, establish the baseline and create the change plan.

1. Establish a reproducible baseline: run all verification commands and record
   results in .uncle/docs/BASELINE_REPORT.md
2. Analyze existing code
3. Create .uncle/docs/CHANGE_SPEC.md describing the change
4. Create .uncle/docs/CHANGE_PLAN.md with implementation strategy

After .uncle/docs/CHANGE_PLAN.md is created:

- do not implement;
- stop and ask the user to review and approve the plan.

### Stage 2: Adversarial review

This stage begins only after .uncle/docs/CHANGE_PLAN.md has a valid approval record.

Invoke:

./scripts/codex-review-plan.sh

After .uncle/docs/ADVERSARIAL_REVIEW.md is created:

- do not revise the plan;
- do not implement;
- stop and ask the user to review and approve the adversarial review.

### Stage 3: Implementation and verification

This stage begins only after .uncle/docs/ADVERSARIAL_REVIEW.md has a valid approval record.

Read:

- .uncle/docs/BASELINE_REPORT.md
- .uncle/docs/CHANGE_PLAN.md
- .uncle/docs/ADVERSARIAL_REVIEW.md

Revise .uncle/docs/CHANGE_PLAN.md in place to address or explicitly reject every review
finding. Record one of: Accepted, Partially accepted, Rejected, Deferred.

Implement according to the approved plan. During implementation:

1. Build the smallest working vertical slice first.
2. Keep core domain behavior in pure functions where practical.
3. Implement high-risk invariants before optional features.
4. Record material deviations from the plan in .uncle/docs/IMPLEMENTATION_NOTES.md.
5. Do not weaken an invariant merely to make a test pass.
6. Do not change an approved requirement without recording the deviation.

After implementation, the driver runs the plan's verification commands and
stops at a human gate on the real diff.

### Stage 4: Manual verification

After implementation and driver-initiated automated verification, invoke:

./scripts/codex-create-checklist.sh

The reviewer CLI creates .uncle/docs/MANUAL_CHECKLIST.md.

Execute every feasible critical item in .uncle/docs/MANUAL_CHECKLIST.md and write
.uncle/docs/VERIFICATION_REPORT.md.

## Artifact ownership

| Artifact | Owner |
|---|---|
| CHANGE_REQUEST.md | Human |
| .uncle/workflow/IMPLEMENTATION_REVIEW.md | Driver |
| .uncle/workflow/green-check.md | Driver |
| .uncle/docs/BASELINE_REPORT.md | Primary agent (stage 1) |
| .uncle/docs/CHANGE_SPEC.md | Primary agent (stage 1) |
| .uncle/docs/CHANGE_PLAN.md | Primary agent (stage 1, revised in stage 3) |
| .uncle/docs/ADVERSARIAL_REVIEW.md | Reviewer (stage 2) |
| Source changes | Primary agent (stage 3) |
| .uncle/docs/IMPLEMENTATION_NOTES.md | Primary agent (stage 3) |
| .uncle/docs/CHANGE_TEST_REPORT.md | Primary agent (stage 3) |
| .uncle/docs/MANUAL_CHECKLIST.md | Reviewer (stage 4) |
| .uncle/docs/VERIFICATION_REPORT.md | Primary agent (stage 4) |
| .uncle/docs/FINAL_AUDIT.md | Reviewer (stage 4) |

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
