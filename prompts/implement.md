You are the primary implementation agent.

Read these in one parallel batch of tool calls:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- UPDATED_PROJECT_PLAN.md
- PREFLIGHT_REPORT.md

That is the whole input set. UPDATED_PROJECT_PLAN.md is the approved plan: it
supersedes PROJECT_PLAN.md and records a disposition for every finding in
ADVERSARIAL_REVIEW.md, so do not read either one. If the updated plan turns out
to be missing something you need, read the superseded document, and record in
IMPLEMENTATION_NOTES.md that you had to.

Implement the approved updated plan.

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
- while iterating, run the narrowest test that covers the change; run the full
  suite when the slice is complete, not after every edit;
- when a command floods the terminal, re-run it filtered to the failures
  rather than reading the whole transcript.

Run all applicable checks. Checks that do not contend for the same build
artifacts or ports should be launched together, not serially:

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
