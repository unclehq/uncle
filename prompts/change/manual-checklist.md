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

## Scope boundary (binding)

Keep only checks that trace to a requested behavior, acceptance criterion,
changed component, or explicitly preserved behavior in the approved change
documents. Remove generic repository-health, workflow, supervisor, credential,
GitHub, publishing, commit, and signing checks unless those documents explicitly
place them in scope. They must not block an unrelated project delivery.

Availability of the `claude` command through its normal web-login session is
sufficient. Do not require `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, or
another API token unless the approved change explicitly requires API-key
authentication.

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

## Feasibility: say which kind of unavailable

This pipeline has no preflight stage, so nothing has probed the environment on
your behalf. Before writing a check that needs a capability -- a port, a
browser, a GUI, an account, a person -- establish whether this machine has it,
from BASELINE_REPORT.md's recorded commands or by reasoning about the platform.

A capability that is not available does not mean dropping the check. A
requirement that cannot be verified must stay visible, and hiding it is the
failure this workflow exists to prevent. Write it, and give it the status that
says which kind of unavailable it is:

- `BLOCKED-SETUP` when one action would make it available
- `BLOCKED-HUMAN` when it waits on a person
- `BLOCKED-IMPOSSIBLE` when this environment cannot do it at all

Do not write a check whose action this environment cannot perform and then
leave it looking runnable. A row that reads like a normal check and can only
ever record BLOCKED costs the executing stage a full attempt, teaches the
operator nothing, and cannot be told apart from a check that failed.

If an acceptance criterion can only be verified through a capability marked
BLOCKED-IMPOSSIBLE, say so plainly and name what would have to change -- the
criterion, the plan's verification strategy, or the environment. That is a
decision for a human at a gate, not something to bury in a check that will
never run.

## Output economy

The twenty categories above are search directions, not an output template.

- Emit a check only where there is something specific to verify.
- If a category does not apply to this change, skip it silently.
- One line per field.
- Merge checks that would be executed by the same action against the same
  preconditions. Do not split one action into five near-identical rows.
- Use check IDs MC-001 upward.

Return only the checklist.

## Efficient checklist delivery

Use the driver evidence packet as an index, not as proof of coverage. Preserve
all required acceptance criteria. Where fresh driver evidence already covers an
assertion, keep its checklist mapping and cite the exact command/evidence to
inspect rather than inventing an equivalent manual rerun. Missing or stale
results still require execution. Identify genuinely human judgment separately
from automatable assertions; never invent a human observation.

Each check must have a concrete action, observable expected result, evidence
path, required-for-acceptance flag, exclusive resources, and dependencies. Use
stable unique MC IDs. Before returning, verify all required fields, dependency
references, and absence of dependency cycles. Correct malformed fields in the
current draft; return the complete checklist, not a progress message.

On a delta or repair pass, retain unaffected check IDs and wording. Change only
rows affected by implementation differences, unresolved findings, changed inputs,
or missing coverage. Compare the supplied hashes with the evidence used before
carrying a conclusion forward; if the prior basis is unavailable, recheck that
row. Record why a row was changed or removed. Never delete required checks merely
to reduce count, runtime, or report length. Write the final checklist once.

## Compact first draft

Draft the executable checklist directly in its required structure. Give each
check one stable ID and canonical definition. Preserve its exact action,
observable expected result, required/optional status, requirement and finding
references, prerequisites, exclusive resources and dependencies. Use complete
concise fields or table rows; never substitute a summary of what checks exist.
Traceability and section summaries reference check IDs rather than repeat them.
Do not duplicate checks already satisfied by applicable current evidence, but
retain every genuinely unverified obligation and independent validation needed.
Do not claim execution or PASS while only designing a check.

Batch independent evidence reads. Before finalizing, check coverage, IDs,
prerequisites, expected results and dependency consistency once. Correct real
gaps without repeated narrated compliance sweeps. Base and delta variants must
still respect their original scope, evidence restrictions and merge contract.

Return the complete requested artifact, not a filename, progress message or
bullet summary saying the checklist was written. Execute-checklist must be able
to run each check from this document without inventing actions or expectations.
In advisory-budget mode, do ZERO size-only compaction passes. Preserve mandatory
content even above the guide; do not repeatedly count bytes or trim whitespace.
The driver measures the artifact. Enforced budgets retain the two-pass limit
and preservation rules. All format and completeness checks still apply.
