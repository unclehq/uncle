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

Write .uncle/docs/MANUAL_CHECKLIST.md as one JSON object, not Markdown,
matching this contract:

`{"schema":"uncle.artifact/v1","kind":"manual-checklist","checks":[{"id":"MC-1","section":"...","priority":"...","required":true,"related_requirement":"...","related_behavior":"...","related_invariant":"...","prerequisites":"...","needs":"PF-7","exclusive_resources":["port:5173"],"depends_on":[],"exact_action":"...","expected_result":"...","evidence_to_capture":"..."}],"traceability":"..."}`

Give every check a stable unique MC ID. `required` is a JSON boolean:
justify it from requirements rather than inferring it from priority. Leave a
field `null` or omit it only when it genuinely does not apply (for example
`related_invariant` when no invariant covers the check); `exact_action` and
`expected_result` are always required. Omit `status` (the driver writes
`NOT RUN`) unless this environment already cannot perform the check's
action -- then set `status` to `BLOCKED-SETUP`, `BLOCKED-HUMAN`, or
`BLOCKED-IMPOSSIBLE` per the rules below, and put the explanation in
`evidence_of_unavailability`. Never set `status` to anything else; execution
has not happened yet. `traceability` is the closing traceability matrix, as
one Markdown block.

## Parallel execution declarations

`exclusive_resources` and `depends_on` on every check decide whether it may
run alongside another, and they are yours because you are the one who knows
what each check touches:

- `exclusive_resources`: what the check needs to itself while it runs — a port
  (`port:5173`), a browser session, a database, a user account, a build output
  directory, a fixture it mutates. An array of lower-case strings. Use `[]`
  when the check only reads and can safely overlap with anything.
- `depends_on`: the check IDs that must finish before this one starts, as an
  array (`[]` for none). Ordering, not topic: a check that merely covers
  related behavior does not depend on it.

Declare both on every check. The driver derives the execution groups from these
two fields alone and hands them to the stage that runs the checklist, so this is
where the question gets decided — not later, by the agent whose results depend
on the answer. An empty `exclusive_resources` array is scheduled alone, so an
omission costs wall-clock rather than correctness.

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
person -- must cite the preflight id that proved it, in `needs` (for example
`"PF-7"`). A check that needs nothing beyond the repository and its test
tools leaves `needs` empty.

If the cited id is not PASS, the capability was not available here, and the
check cannot pass. Write the check anyway -- a requirement that cannot be
verified must stay visible, and dropping it is the failure this workflow exists
to prevent -- but give it the status that says which kind of unavailable it is:

- `BLOCKED-SETUP` when one action would make it available
- `BLOCKED-HUMAN` when it waits on a person
- `BLOCKED-IMPOSSIBLE` when this environment cannot do it at all

Do not write a check whose action this environment cannot perform and then
leave it looking runnable. A row that reads like a normal check and can only
ever record BLOCKED costs the executing stage a full attempt, teaches the
operator nothing, and cannot be told apart from a check that failed.

If a mandatory requirement can only be verified through a capability marked
BLOCKED-IMPOSSIBLE, say so in Open questions and name what would have to change
-- the requirement, the plan's verification strategy, or the environment. That
is a decision for a human at a gate, not something to bury in a check that
will never run.

Set each check's `section` to one of:

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

`traceability` is the closing traceability matrix.
Cover every mandatory acceptance criterion, even if its prerequisites are
unavailable. Identify any remaining test-review findings and their regression
checks. Do not substitute DOM presence for visibility, emulation for required
interactive behavior, or one browser for another named in the requirements.

Keep it dense. Reference requirements, behaviors, and invariants by identifier
instead of restating them — this checklist is read by two later stages, so
every line you duplicate is paid for repeatedly. One check per real risk; do
not pad a section to make it look complete. If a section has no meaningful
check for this project, include one check in it whose `exact_action` states
"none applicable" and why, rather than omitting the section.

Return only the JSON object.

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
