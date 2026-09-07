You are the primary system architect.

Read these in one parallel batch of tool calls:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- PROJECT_PLAN.md
- ADVERSARIAL_REVIEW.md

Create UPDATED_PROJECT_PLAN.md.

For every adversarial finding, record:

| Finding | Disposition | Reason | Plan change |
|---|---|---|---|

Allowed dispositions:

- Accepted
- Partially accepted
- Rejected
- Deferred

Do not blindly accept every recommendation.

Retain and update:

- behaviors;
- invariants;
- architecture;
- traceability;
- testing strategy;
- failure handling;
- implementation order;
- time-based priorities;
- explicit non-goals.

Clearly identify changes from PROJECT_PLAN.md.

Include a section titled exactly:

## Verification commands

Under it, one fenced block and nothing else, holding the commands that
demonstrate the build is working — formatter, type checker, linter, tests,
build, startup smoke — one per line, run from the repository root.

The driver runs this block itself after implementation, and the operator sees
the result next to the diff before anything downstream reads either. It is the
one part of this plan that is executed rather than read, so:

- no prompt prefixes, no comments, no prose, no placeholders;
- no command that needs interactive human input; automated browsers and local
  test servers are allowed and required when they establish acceptance;
- no live third-party dependency unless the requirements demand it and the
  prerequisite and failure behavior are explicitly documented;
- nothing that only the implementing agent's machine could run.

In the testing strategy, map every mandatory automated acceptance check to a
command in this block. Include browser checks and delivered update-tool
failure paths where applicable; do not substitute compilation or source
inspection. Missing dependencies or skipped mandatory checks must fail the
verification entry point. Carry forward observable assertions, independent
expected results, representative defect injections that prove critical tests
fail, and prerequisites for both automated and manual acceptance. Missing
capabilities remain blockers rather than becoming optional checks.

Approving this plan approves those commands.

Optionally add `## Parallel verification groups` with a fenced block of
one-based positions from the Verification commands block. Each line is a group
of at least two consecutive command numbers, for example `2 3`. Groups must be
ordered and disjoint. Only group checks proven independent: no shared ports,
writable fixtures, outputs, or prerequisite ordering. Explain that independence
in the testing strategy. The driver limits concurrency with WORKFLOW_VERIFY_JOBS
(default 2, maximum 8), preserves per-command outcomes and integrity checks,
and runs unlisted commands sequentially. Omit this section when none qualify.

Include `## Protected verification paths` with one fenced block of literal
repository-relative file or directory paths, one per line. List all tests,
expected results and fixtures, test helpers, and configuration that determines
which tests run. Prefer complete test directories so new tests cannot be
silently added during verification. Include authoritative source inputs when
they are test oracles. No globs, symlinks, parent traversal, or workspace-state
paths. Paths must exist after implementation. Put generated test outputs in
temporary directories outside these scopes. Python bytecode caches are ignored.
The driver hashes these inputs before running verification and rejects changed,
added, or deleted inputs. Repairs may edit them, but require a fresh diff review
and independent test review. Explain the scope in the testing strategy.

This document is the sole plan input to implementation, checklist creation, and
the final audit — none of them will read PROJECT_PLAN.md or
ADVERSARIAL_REVIEW.md. So it must stand alone. Standing alone means every
normative row survives, not every sentence:

- carry forward every behavior, invariant, and traceability row, updated — a
  reader must never need the superseded plan to know what to build or what must
  hold;
- drop the narrative around those rows: rationale that no longer drives a
  decision, alternatives considered and rejected, and restated background;
- in the disposition table, cite each finding by its AR-XXX identifier and give
  the reason in a sentence; do not restate the finding;
- reference requirements by identifier rather than restating them;
- no preamble and no closing recap.

Keep the implementation contract compact: target 12,000 UTF-8 bytes, subject to
the driver budget appended below. Preserve complete normative rows and exact
commands. Do not copy the original plan or review narrative. Supporting evidence
stays in its original artifact, cited by file and finding ID; implementation must
not need that evidence to discover an obligation.

Do not implement code.
Do not invoke another agent.
Do not draft the plan in chat before writing it.

Write only UPDATED_PROJECT_PLAN.md, in a single Write call, and stop.
