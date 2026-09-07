You are the primary system architect.

Read these in one parallel batch of tool calls, along with any source files you
need to inspect:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md

Create PROJECT_PLAN.md.

Include:

1. Requirement interpretation
2. Architecture
3. Authoritative state
4. Domain model
5. Components and responsibilities
6. Data flow
7. Observable behaviors
8. Domain invariants
9. Failure handling
10. Concurrency model
11. Automated-test strategy, ending in a `## Verification commands` block:
    one fenced block, one runnable command per line, from the repository root
12. Manual-test strategy
13. Requirement traceability
14. Implementation order
15. Time-based priorities
16. Explicit non-goals
17. Risks and unresolved questions

Use this invariant table:

| ID | Invariant | Scope | Enforcement point | Automated test | Violation impact |
|---|---|---|---|---|---|

Use this traceability table:

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|

For each mandatory acceptance criterion, the testing strategy must name the
observable assertion, independently grounded expected result, prerequisites,
and evidence to retain. Plan representative defect injections for critical
assertions: identify the defect and the specific test that must reject it.
Include development/update tooling and input/provenance failures where these
are delivered. Avoid testing only the happy path or copying implementation
logic into the oracle.

The Verification commands block must reach every required automated check,
including browser checks when applicable. Automated local browsers and test
servers are allowed. Commands must run unattended, fail on missing mandatory
dependencies or skipped mandatory checks, and require no live third-party
service unless requirements explicitly demand one. List interactive checks
and unresolved prerequisites separately in the manual-test strategy.
Identify the test, fixture, helper, configuration, and source-oracle paths that
the updated plan will freeze during verification. Keep generated test outputs
outside those protected paths.

Identify independent verification commands that can run concurrently. Commands
sharing ports, writable fixtures, generated outputs, or ordered state must stay
sequential. Use isolated output directories and local test-server ports where
concurrency is appropriate; do not weaken checks to make them parallel.

Write densely. Five later stages read this document, so length here is paid
for repeatedly:

- reference requirements by their REQUIREMENTS_INTERPRETATION.md identifiers
  instead of restating them;
- put structured content in the tables and do not repeat it as prose;
- cover every section, but let a section be one line when that is the honest
  answer for this project;
- no preamble, no summary of what you are about to say, no closing recap.

Do not implement code.
Do not invoke another agent.
Do not draft the plan in chat before writing it.

Write only PROJECT_PLAN.md, in a single Write call, and stop.

Use one canonical row per behavior, invariant, and acceptance obligation. Later strategy and implementation sections reference those IDs instead of repeating the rows. Keep rationale only where it explains a decision or constraint.
