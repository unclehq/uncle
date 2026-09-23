Act as an independent release-verification engineer.

Inspect:

- REQUIREMENTS.md
- .uncle/docs/REQUIREMENTS_INTERPRETATION.md
- .uncle/docs/UPDATED_PROJECT_PLAN.md
- .uncle/docs/IMPLEMENTATION_NOTES.md, if present
- .uncle/docs/AUTOMATED_TEST_REPORT.md
- .uncle/docs/PREFLIGHT_REPORT.md and .uncle/docs/TEST_REVIEW.md
- the source code and tests

.uncle/docs/UPDATED_PROJECT_PLAN.md supersedes .uncle/docs/PROJECT_PLAN.md and carries a disposition
for every adversarial finding, so neither of those needs to be read. Read them
only if the updated plan is internally inconsistent, and say so if you do.

Read source selectively: start from the plan's components and traceability
table and open what the checks actually depend on, rather than the whole tree.

Do not modify source code.
Do not claim that any check passed.

Give every check a stable unique MC ID. Justify `required` from requirements
rather than inferring it from priority. Leave a field blank only when it
genuinely does not apply (for example related invariant when no invariant
covers the check); exact action and expected result are always required.
Do not record a status of PASS/FAIL -- execution has not happened yet; only
record BLOCKED-SETUP, BLOCKED-HUMAN, or BLOCKED-IMPOSSIBLE per the rules
below, with the explanation, when this environment already cannot perform
the check's action.

## Parallel execution declarations

Exclusive resources and dependencies on every check decide whether it may run
alongside another, and they are yours because you are the one who knows what
each check touches:

- Exclusive resources: what the check needs to itself while it runs — a port
  (`port:5173`), a browser session, a database, a user account, a build output
  directory, a fixture it mutates. Lower-case tokens, comma-separated. Leave
  empty when the check only reads and can safely overlap with anything.
- Depends on: the check IDs that must finish before this one starts,
  comma-separated (empty for none). Ordering, not topic: a check that merely
  covers related behavior does not depend on it.

Declare both on every check. The driver derives the execution groups from these
two fields alone and hands them to the stage that runs the checklist, so this is
where the question gets decided — not later, by the agent whose results depend
on the answer. Empty exclusive resources means scheduled alone, so an omission
costs wall-clock rather than correctness.

Two checks that would fight over the same port must name the same token, spelled
the same way. A resource token is only as good as that agreement.

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

## Feasibility: cite what preflight proved

Read `.uncle/workflow/preflight-capabilities/README.md` first. It lists one row
per prerequisite that was probed before implementation, with its status and the
observed evidence.

Every check that needs a capability -- a port, a browser, a GUI, an account, a
person -- must cite the preflight id that proved it, in Needs (for example
`PF-7`). A check that needs nothing beyond the repository and its test tools
leaves Needs empty.

If the cited id is not PASS, the capability was not available here, and the
check cannot pass. Write the check anyway -- a requirement that cannot be
verified must stay visible, and dropping it is the failure this workflow exists
to prevent -- but give it the status that says which kind of unavailable it is:

- `BLOCKED-SETUP` when one action would make it available
- `BLOCKED-HUMAN` when it waits on a person
- `BLOCKED-IMPOSSIBLE` when this environment cannot do it at all

Do not write a check whose action this environment cannot perform and then
leave it looking runnable. A check that reads like a normal check and can only
ever record BLOCKED costs the executing stage a full attempt, teaches the
operator nothing, and cannot be told apart from a check that failed.

If a mandatory requirement can only be verified through a capability marked
BLOCKED-IMPOSSIBLE, say so in Open questions and name what would have to change
-- the requirement, the plan's verification strategy, or the environment. That
is a decision for a human at a gate, not something to bury in a check that
will never run.

Set each check's Section to one of:

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

Cover every mandatory acceptance criterion, even if its prerequisites are
unavailable. Identify any remaining test-review findings and their regression
checks. Do not substitute DOM presence for visibility, emulation for required
interactive behavior, or one browser for another named in the requirements.

Keep it dense. Reference requirements, behaviors, and invariants by identifier
instead of restating them — this checklist is read by two later stages, so
every line you duplicate is paid for repeatedly. One check per real risk; do
not pad a section to make it look complete. If a section has no meaningful
check for this project, include one check in it whose exact action states
"none applicable" and why, rather than omitting the section.

## This is an investigation, not the final document

A second, separate pass converts this investigation into the required JSON
document; your only job here is to get every check and the traceability
matrix right. Write your complete checklist as plain Markdown, not JSON, to
`.uncle/workflow/manual-checklist-investigation.md`. Use this exact per-check
format, one block per check:

```
## MC-1: Short label
- Section: 2. User-visible behaviors
- Priority: ...
- Required: true
- Related requirement: R-1
- Related behavior: B-2
- Related invariant: (none)
- Prerequisites: ...
- Needs: PF-7
- Exclusive resources: port:5173
- Depends on: (none)
- Exact action: ...
- Expected result: ...
- Evidence to capture: ...
- Status: (omit unless this environment already cannot perform the action)
- Evidence of unavailability: (omit unless Status is set)
```

End with a `## Traceability` section holding the closing traceability matrix
as Markdown.

Begin the file with a Markdown heading, such as `# Manual checklist
investigation` -- a response with no heading anywhere in it is rejected as
not a document at all, regardless of whether its content is otherwise
correct. Write it directly and correctly the first time. Do not narrate a
plan for it or summarize what you are about to write -- write the
investigation itself, in full, as your final message.

## Efficient checklist delivery

Use the driver evidence packet as an index, not as proof of coverage. Preserve
all required acceptance criteria. Where fresh driver evidence already covers an
assertion, keep its checklist mapping and cite the exact command/evidence to
inspect rather than inventing an equivalent manual rerun. Missing or stale
results still require execution. Identify genuinely human judgment separately
from automatable assertions; never invent a human observation.

Each check must have a concrete action, observable expected result, evidence
path, required-for-acceptance flag, exclusive resources, and dependencies. Use
stable unique MC IDs. Before finishing, verify all required fields, dependency
references, and absence of dependency cycles. Correct malformed fields in the
current draft; write the complete checklist, not a progress message.

On a delta or repair pass, retain unaffected check IDs and wording. Change only
checks affected by implementation differences, unresolved findings, changed
inputs, or missing coverage. Compare the supplied hashes with the evidence used
before carrying a conclusion forward; if the prior basis is unavailable, recheck
that check. Record why a check was changed or removed. Never delete required
checks merely to reduce count, runtime, or report length. Write the final
checklist once.

Batch independent evidence reads. Before finishing, check coverage, IDs,
prerequisites, expected results and dependency consistency once. Correct real
gaps without repeated narrated compliance sweeps. Base and delta variants must
still respect their original scope, evidence restrictions and merge contract.

Do not claim execution or PASS while only designing a check. In advisory-budget
mode, do ZERO size-only compaction passes. Preserve mandatory content even
above the guide; do not repeatedly count bytes or trim whitespace. The driver
measures the artifact. Enforced budgets retain the two-pass limit and
preservation rules. All format and completeness checks still apply.
