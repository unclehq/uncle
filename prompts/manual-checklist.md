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
- Exclusive resources
- Depends on
- Exact action
- Expected result
- Evidence to capture
- Actual result: blank
- Status: NOT RUN

## Parallel execution declarations

Two fields on every check decide whether it may run alongside another, and they
are yours because you are the one who knows what each check touches:

- `Exclusive resources`: what the check needs to itself while it runs — a port
  (`port:5173`), a browser session, a database, a user account, a build output
  directory, a fixture it mutates. Comma-separated, lower case. Write `none`
  when the check only reads and can safely overlap with anything.
- `Depends on`: the check IDs that must finish before this one starts, or
  `none`. Ordering, not topic: a check that merely covers related behavior does
  not depend on it.

Declare both on every check. The driver derives the execution groups from these
two fields alone and hands them to the stage that runs the checklist, so this is
where the question gets decided — not later, by the agent whose results depend
on the answer. A check with no `Exclusive resources` line is scheduled alone, so
an omission costs wall-clock rather than correctness.

Two checks that would fight over the same port must name the same token, spelled
the same way. A resource token is only as good as that agreement.

If the checklist is a table, head those two columns `Excl` and `Deps`. Both
spellings are read, but a column headed something else is not read at all, and
an unread declaration silently costs the concurrency it was written to enable.

For a browser or desktop resource, declare the system default browser
(`browser:system`) unless the requirements name a specific one, in which case
name that (`browser:safari`). The check's action drives it through the
platform's opener -- `open` on macOS, `start` on Windows -- rather than a
hardcoded application path, so the same checklist runs on either.

Do not name a browser the preflight report has not shown to be installed.
Chrome is a download on every platform, Safari does not exist off macOS, and a
headless or CDP-based harness can only drive Chrome, Chromium, or Edge -- so a
row naming one of those is a row that records BLOCKED on a machine without it.

The default browser is a per-user, per-machine setting, so `browser:system`
resolves to different engines for different operators. That is the right
default for a requirement written about "the user's browser", but it means the
check's Evidence must record which browser it actually used. A result that does
not say what it ran in cannot be reproduced or trusted, and a second engine
needs its own row naming that engine.

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
