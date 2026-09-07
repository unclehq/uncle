Act as an independent release-verification engineer.

Inspect:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- UPDATED_PROJECT_PLAN.md
- IMPLEMENTATION_NOTES.md, if present
- AUTOMATED_TEST_REPORT.md
- PREFLIGHT_REPORT.md and TEST_REVIEW.md
- the source code and tests

UPDATED_PROJECT_PLAN.md supersedes PROJECT_PLAN.md and carries a disposition
for every adversarial finding, so neither of those needs to be read. Read them
only if the updated plan is internally inconsistent, and say so if you do.

Read source selectively: start from the plan's components and traceability
table and open what the checks actually depend on, rather than the whole tree.

Do not modify source code.
Do not claim that any check passed.

Create MANUAL_CHECKLIST.md.

For every check include:

- Check ID
- Priority
- Required for acceptance: YES or NO, justified from requirements rather than
  inferred from priority
- Related requirement
- Related behavior
- Related invariant
- Prerequisites
- Exact action
- Expected result
- Evidence to capture
- Actual result: blank
- Status: NOT RUN

Include sections for:

1. Smoke checks
2. User-visible behaviors
3. Domain invariants
4. Boundary conditions
5. Invalid input
6. Failure paths
7. Full-stack integration
8. Restart and recovery
9. Requirements not covered by automated tests
10. Regression checks

End with a traceability matrix.
Cover every mandatory acceptance criterion, even if its prerequisites are
unavailable. Identify any remaining test-review findings and their regression
checks. Do not substitute DOM presence for visibility, emulation for required
interactive behavior, or one browser for another named in the requirements.

Keep it dense. Reference requirements, behaviors, and invariants by identifier
instead of restating them — this checklist is read by two later stages, so
every line you duplicate is paid for repeatedly. One check per real risk; do
not pad a section to make it look complete. If a section has no meaningful
check for this project, write "none applicable" and why.

Return only the checklist.
