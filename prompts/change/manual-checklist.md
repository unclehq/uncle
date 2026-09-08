Act as an independent release-verification engineer.

Read:

- CHANGE_REQUEST.md
- BASELINE_REPORT.md
- CHANGE_SPEC.md
- ADVERSARIAL_REVIEW.md
- CHANGE_PLAN.md
- IMPLEMENTATION_NOTES.md
- CHANGE_TEST_REPORT.md
- changed source files
- relevant unchanged source files
- automated tests

Do not modify source code.
Do not claim any check passed.

Create MANUAL_CHECKLIST.md.

Verify:

1. Requested behavior
2. All MODIFY behaviors
3. All ADD behaviors
4. All REMOVE behaviors
5. Representative PRESERVE behaviors
6. Existing invariants
7. New or strengthened invariants
8. Boundary conditions
9. Error behavior
10. Failure and recovery behavior
11. Backward compatibility
12. Migration
13. Rollback
14. Restart behavior
15. Observability
16. Performance-sensitive paths
17. Security-sensitive paths
18. Prototype isolation
19. Regression-sensitive paths
20. Requirements not covered by automated tests

Each check must contain:

- Check ID
- Priority
- Behavior classification
- Related behavior
- Related invariant
- Preconditions
- Exclusive resources
- Depends on
- Exact action
- Expected result
- Evidence to capture
- Actual result: blank
- Status: NOT RUN

End with:

- acceptance-criteria traceability
- preserved-behavior coverage
- changed-behavior coverage
- invariant coverage
- regression coverage

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

## Output economy

The twenty categories above are search directions, not an output template.

- Emit a check only where there is something specific to verify.
- If a category does not apply to this change, skip it silently.
- One line per field.
- Merge checks that would be executed by the same action against the same
  preconditions. Do not split one action into five near-identical rows.
- Use check IDs MC-001 upward.

Return only the checklist.
