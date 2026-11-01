# Project brief

## Summary
Uncle is a human-gated engineering workflow tool: a set of shell/Python
drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`, and
supporting scripts) that run an AI planning/implementation/review loop for
both new applications and changes to existing repositories, with mandatory
human approval gates between stages.

## Problem
Unsupervised AI coding agents can silently fabricate test results, weaken
assertions to force a pass, or skip adversarial review. Teams need a
repeatable process that forces independent planning, independent
adversarial review, and independent verification, with a human approving
each hand-off, instead of trusting a single agent's self-report.

## Scope
A CLI-driven workflow covering: initial project planning, adversarial plan
review, an updated/reconciled plan, implementation, automated verification,
an independently generated manual checklist, and manual verification -- for
both greenfield projects and changes to existing codebases. Includes
issue-import tooling (`scripts/from-issue.sh`) to seed a workflow run from a
GitHub issue.

## Non-goals
Not a general-purpose CI system, not a replacement for a human code
reviewer, and not a guarantee that AI-generated code is correct -- only
that specific gates were executed and recorded.

## Functional requirements
- Drive a sequence of stages (plan, adversarial review, updated plan,
  implementation, automated verification, manual checklist, manual
  verification) with named owners for each artifact.
- Persist stage artifacts under `.uncle/docs/` and `.uncle/workflow/`.
- Support both a new-application workflow and an existing-code change
  workflow, each with its own stage gates.
- Allow seeding a run from a GitHub issue via `from-issue.sh`, including
  `--new` and `--change` project-root modes.
- Require an external reviewer CLI (default Codex CLI) for adversarial
  review and manual-checklist creation, run by the drivers
  (`stagegate.sh` and `change-workflow.sh`) as independent reviewer panels.

## User-visible behavior
A user runs the launcher, the tool creates or resumes workflow state, and
at each gate the user is asked to review and approve a generated document
before the next stage proceeds. Blocked or failed checks are reported with
an explicit classification (BLOCKED-SETUP, BLOCKED-HUMAN,
BLOCKED-IMPOSSIBLE, PASS, FAIL, NOT RUN) rather than being silently skipped.

## Domain rules and invariants
- No stage may begin before its prerequisite artifact has a valid approval
  record.
- A check is never marked PASS unless it was actually executed or directly
  observed.
- Reviewer-owned artifacts are never modified by the primary agent.
- A RELAXED or REMOVED invariant always requires explicit human approval.

## Data and state
Workflow state lives on disk under `.uncle/workflow/` (driver-owned,
machine state) and `.uncle/docs/` (human-reviewed documents). State is
resumable across process restarts; a driver must be able to detect and
recover from an interrupted run.

## Interfaces
A bash/Python CLI only; no network service. External dependencies are the
primary agent CLI (default Claude CLI) and the reviewer CLI (default Codex
CLI), invoked as subprocesses.

## Constraints
Must run on macOS default bash (3.2) as well as modern bash; no
associative arrays or bash-4-only syntax in shared scripts. Must not use
unsafe permission-bypass flags when invoking agent CLIs.

## Failure behavior
A missing prerequisite pauses the run rather than silently treating it as a
pass. An unparseable or malformed review/report document halts at the
stage that was about to consume it rather than being guessed at or
swallowed as non-blocking.

## Verification
Each stage's automated verification commands are captured in a report
(e.g. `.uncle/docs/AUTOMATED_TEST_REPORT.md`,
`.uncle/docs/BASELINE_REPORT.md`) with command, exit status, and relevant
output recorded for every check.

## Definition of done
A workflow run reaches completion only when acceptance criteria are
satisfied, no blocking final-audit findings remain, no unexplained
regressions exist, approved invariants remain enforced, and required
manual checks were executed (or explicitly and validly waived).

## Open questions
None tracked at this time; see `.uncle/docs/` artifacts for any
in-progress run's open questions.
