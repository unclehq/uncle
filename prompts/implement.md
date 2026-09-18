You are the primary implementation agent.

Read these in one parallel batch of tool calls:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- UPDATED_PROJECT_PLAN.md
- PREFLIGHT_REPORT.md, if it exists

That is the whole input set. PREFLIGHT_REPORT.md may legitimately be absent:
the prerequisite probe now runs alongside this stage instead of in front of it,
so implementation does not wait on it. Its absence is not an error and not a
reason to stop or to go looking for one; build from the plan. It also means no
prerequisite has been confirmed yet, so do not record any capability as
verified on the strength of a report you did not read. UPDATED_PROJECT_PLAN.md is the approved plan: it
supersedes PROJECT_PLAN.md and records a disposition for every finding in
ADVERSARIAL_REVIEW.md, so do not read either one. If the updated plan turns out
to be missing something you need, read the superseded document, and record in
IMPLEMENTATION_NOTES.md that you had to.

Source files already in the tree may be a first look built from the brief
before the plan was reviewed. They are not evidence: build the application the
plan specifies, rewriting them in place where they do not fit it and removing
what the plan has no use for.

Implement the approved updated plan in this invocation. Deliver working
application code and feature-specific verification, not only plans or reports.
Map every required acceptance criterion to an implementation task and a check,
then build the first working slice after the focused repository inspection.
Continue until all required behavior is implemented and verified.

Resolve routine implementation choices within the approved scope using
repository conventions. Do not stop merely because the plan labels a detail
ASSUMPTION or UNRESOLVED; determine whether a new decision is actually required.
Do not seek approval again for already authorized work. Respect explicit
unresolved approval requirements and complete independent authorized work
while they are pending. Report genuine blockers precisely as incomplete work.

Before handing off, inspect the resulting code and exercise the requested
behavior. For each required acceptance criterion, record the implementing code
and observed verification result. Passing baseline checks or creating reports
does not prove a feature was built. Implement missing items before ending;
never describe partial or blocked work as a completed application.

Rules:

1. Build the smallest working vertical slice first.
2. Keep core domain logic pure where practical.
3. Implement high-risk invariants before optional functionality.
4. Compile and test continuously.
5. Do not weaken an invariant to make a test pass.
6. Record deviations in IMPLEMENTATION_NOTES.md.
7. Add requirement and invariant identifiers to relevant tests.
8. Do not invoke the reviewer CLI.
9. Prove critical acceptance tests fail for the representative defects in the
   plan, in temporary copies or isolated test state. Record the defect, command,
   expected assertion failure, observed failure, and passing restored result.
   A crash caused by missing dependencies does not prove the assertion works.
10. Include all required automated acceptance checks in the approved command
    entry points. Cover delivered update tooling and browser behavior where
    applicable. Missing required dependencies and mandatory skips must fail.
11. Kill processes by exact PID, one at a time. Never broadcast-kill by port,
    listener scan, or name pattern (`kill $(lsof -t -iTCP ...)`, `pkill -f`,
    `killall`): the agent runtime hosting this session is itself a local
    process those patterns can match, and killing it loses the whole stage.

Work efficiently. This stage is a long loop, and everything already in the
conversation is re-sent on every turn, so avoid pulling in what you will not
use:

- batch independent file reads and edits into single messages;
- run independent commands concurrently rather than one per turn;
- do not re-read a file you just wrote;
- read the region of a file you need, not the whole file, once it is large;
- while iterating, run the narrowest test that covers the change; leave the
  approved full verification block to the driver after this stage;
- when a command floods the terminal, re-run it filtered to the failures
  rather than reading the whole transcript.

Run applicable targeted checks. The driver owns UPDATED_PROJECT_PLAN.md's full
verification block and runs it once immediately after this stage. Do not run a
full-project regression command or an equivalent loop over every suite here
unless a narrower target cannot establish a specific acceptance criterion.
Record the full block as `DRIVER PENDING`; the subsequent green check is the
authoritative result. Checks that do not contend for the same build artifacts
or ports should be launched together, not serially:

- formatting;
- compilation;
- linting;
- unit tests;
- property tests;
- integration tests;
- applicable automated browser and update-tool failure-path tests;
- frontend build;
- startup smoke tests.

Skip a check only if it does not apply to this repository, and say so
explicitly in the report.

Create AUTOMATED_TEST_REPORT.md containing:

- exact command;
- exit status;
- meaningful output;
- PASS, FAIL, BLOCKED, or NOT RUN;
- unresolved warnings;
- untested requirements.

Under "meaningful output", excerpt the lines that carry the result — the
summary line, and the failures in full. Do not paste whole test transcripts:
two later stages read this file.

Do not claim tests passed unless they were executed.
Include evidence for the critical defect-injection checks, distinguishing
measured behavior from DOM presence or static inspection. Do not alter approved
plans or requirements to make a test pass. Record a needed plan amendment as a
blocker requiring renewed approval.

## What happens to this work next

The driver re-runs UPDATED_PROJECT_PLAN.md's `## Verification commands` block
itself, with no agent in the path, and a human then reads the real diff —
generated from the working tree, including the files you created — next to
IMPLEMENTATION_NOTES.md and AUTOMATED_TEST_REPORT.md.

A check you reported as passing but did not run shows up in that comparison.
Run the checks, and report what actually happened.

Read .uncle/workflow/plan-executability/assessment.md when present. If verdict is
DECISION, implement only the listed executable step IDs and paths; retain all acceptance
rows and leave dependent/transitive steps pending. Do not ask again for settled authority.
Complete independent code and mocked tests before reporting a live-verification blocker.
Report contradictions in exactly one fenced `plan-blockers` JSON array in
IMPLEMENTATION_NOTES.md. Each row has id, class (DESIGN/AUTHORITY/LIVE_VERIFICATION/CODING),
requirement_ids, restriction_ids, evidence, independent_work. AUTHORITY also requires
question and alternatives. DESIGN means an unsupported generated mechanism, not an
ordinary coding defect. LIVE_VERIFICATION means only dependent approved live checks
remain unavailable or failing; preserve INCOMPLETE/BLOCKED delivery rows until they pass.
Never remove acceptance IDs, weaken protected tests, suppress findings, or auto-waive.

## Avoid repeated setup and model round trips

Before installing dependencies, check whether the declared versions are already
usable with the current manifest and lockfile. Reuse a matching installation;
use the package manager's download cache when installation is necessary. A
folder's existence alone does not prove a valid installation. Invalidate reuse
when the lockfile, manifest, runtime/ABI, platform, or dependency configuration
changes, or when the capability probe fails. Never skip an explicitly approved
clean-install verification command or a check intended to test installation.

Reuse an installed browser only when its engine/revision matches the pinned
automation package and it successfully launches in the execution environment.
Do not repeatedly download browsers, switch engines, upgrade packages, or change
lockfiles to save time. Keep cache use distinct from test-result reuse: tests
still run against the implemented files and current environment.

After focused inspection, author independent related source and test files in
one batch of tool calls. Preserve plan dependencies and protected-input snapshot
ordering. Then run a single verification batch, parallelizing only independent
checks with separate outputs and no conflicting resources. When a check fails,
fix it and rerun affected checks and their dependents; rerun the full batch only
when the change or the approved plan requires it. Keep every required check.

Collect command exits, output paths, and acceptance mappings during execution.
Write each required implementation/test report once from the collected evidence
at the end. Do not repeatedly write progress into final reports or rerun passing
checks just to reproduce their output for a report. If interrupted, preserve a
short checkpoint of unfinished work and existing evidence instead of starting
the implementation and checks over. Do not claim unobserved results.

## Minimal stage handoff

Use the shared input index and structured handoffs to locate approved decisions,
files and evidence. Read complete relevant sections, not the entire repository.
Retain unchanged IDs, decisions and commands. Inspect or probe only to resolve a
specific missing fact. Do not repeat dependency discovery already supported by
current evidence. Write one concise final report: changed behavior, exact checks
and evidence references, unresolved findings. No chronological work diary or
restatement of requirements. Planning revisions must remain complete plans;
implementation reports must preserve every required result and failure.
