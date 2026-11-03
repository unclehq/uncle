# Agentic.md

## The agentic contract

This repository is a governance layer for AI-generated code. It exists because
an agent left alone will eventually ship something that is subtly wrong, and
the cost of that wrongness compounds faster than the speed saved by removing
the human.

The contract is simple:

- Agents propose; humans approve.
- Agents implement; agents review adversarially.
- Approved artifacts are frozen; no one silently changes them.
- Speed comes from speculative execution, not from skipping gates.

## Why a separate approval layer

Most agent tools optimize for removing humans. They run until they hit a
problem, then ask for help, or worse, they do not ask at all. That works for
demos and disposable scripts. It does not work for production code, where the
failure modes are:

- A requirement is misunderstood but the implementation compiles.
- A test is weakened until it passes.
- A security invariant is silently relaxed.
- A "small cleanup" changes behavior outside the requested scope.
- An agent hallucinates a dependency or API and no one checks it.

The approval layer makes these failures expensive to reach. Every plan, every
review, and every updated plan stops and waits for a human. The human does not
need to read every line of generated code; they only need to read the document
that authorizes it.

## The three-gate model

Every significant change passes through three gates:

1. **Plan gate.** The primary agent proposes what to build and why. The human
   approves or rejects the plan.
2. **Review gate.** An independent reviewer audits the plan adversarially. The
   human acknowledges the review.
3. **Updated-plan gate.** The primary agent revises the plan in light of the
   review. The human approves the final plan.

Implementation may not begin until the updated plan is approved. This is the
load-bearing rule. It prevents the agent from coding its way out of a bad
plan.

## Artifact freezing

Every approved artifact is hashed with SHA-256. Downstream stages re-verify the
hash before running. If an artifact changed after approval, the pipeline stops.
This is not paranoia; it is the only way to ensure that what is implemented is
what was reviewed.

There are two kinds of artifacts:

- **Primary-agent artifacts.** Owned by the agent that implements the change.
- **Reviewer artifacts.** Owned by the independent reviewer. The primary agent
  must never edit them.

This separation is what makes the review independent.

## Adversarial review

The reviewer is not a helper. It is instructed to find what is wrong, missing,
ambiguous, or risky. Its findings are not orders; they are input to the
updated-plan stage. The human decides which findings to accept, reject, or
defer.

A good adversarial review focuses on:

- Requirements that are omitted or misunderstood
- Behaviors that are underspecified
- Invariants that are missing, weak, or untestable
- Failure modes and edge cases
- Security and operational risks
- Tests that could pass despite incorrect behavior
- Scope creep and unnecessary complexity

## Speculative execution

Speculative execution is off by default. When enabled with `WORKFLOW_SPECULATE=1`,
the driver starts the next stage in the background while a human reads a gated
document; the result is adopted only if the document is byte-identical when
approved, and otherwise the work is discarded and the stage replays.

It is off because it did not pay for itself: an unattended gate is open for 0.0
seconds, so there is nothing to overlap, and the speculative plan stages ended
with no artifact, which made the real stage wait and then run again. The checklist
draft written beside implementation is a separate mechanism and is unaffected.

## Human authority

The human is the only entity that can:

- approve a plan;
- approve an updated plan;
- approve a relaxed or removed invariant;
- decide that a finding is non-blocking;
- ship the result.

Agents record, implement, verify, and audit. They do not decide.

## Extending the workflow

The workflow is intentionally modular. A new stage is:

1. A prompt file in `prompts/` or `prompts/change/`.
2. A state transition in the driver.
3. An approval check, if the stage produces a gated artifact.
4. An ownership rule in `CLAUDE.md`.

New stages should preserve the invariant: a reviewer-owned artifact is never
edited by the primary agent, and an approved artifact is never consumed without
a hash check.

## When not to use this workflow

Do not use this workflow when:

- The problem is trivial and the cost of a wrong answer is near zero.
- The only acceptable outcome is immediate automation.
- No human is available to read and approve the gates.
- The codebase is not under version control.

Use this workflow when the cost of a silent mistake exceeds the cost of waiting
for a human to say yes.
