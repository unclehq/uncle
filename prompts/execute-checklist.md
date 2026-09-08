You are the primary verification agent.

Read MANUAL_CHECKLIST.md, PREFLIGHT_REPORT.md, TEST_REVIEW.md, and REQUIREMENTS.md.
Read DEFECTS.md if present to retain IDs and verify earlier defect dispositions.
Execute every feasible mandatory acceptance check, regardless of priority, plus
Critical and Important checks. On a repair pass, rerun checks and record current
results; do not reuse a previous PASS without confirming it still holds.

## Parallel execution

After reading the fresh driver evidence below, group the remaining checks by
prerequisites and shared resources. Run independent checks concurrently using
parallel tool calls or background processes; do not run them one at a time when
they can safely overlap. Share read-only setup where possible.

Run dependent checks in order. Serialize checks that share mutable fixtures,
ports, browser sessions, accounts, build outputs, or other state, unless those
resources can be isolated without changing what the check verifies. Keep
concurrency within available resources to avoid introducing timing failures.

Capture each check's output and exit status separately, tied to its checklist
ID. Wait for every started check to finish before assigning results. A failed
check must not discard results from other independent checks. Record why any
dependent check could not run. Collect evidence as checks finish, then write
VERIFICATION_REPORT.md and DEFECTS.md once after all results are collected; do
not let concurrent checks write to the same report.

## Fresh driver verification evidence

Read `.uncle/workflow/checklist-driver-checks/README.md` first. The driver
runs the approved automated verification commands immediately before this stage,
outside the agent sandbox, and records command exits in `results.tsv` and
assertion output in `output.log` in that directory. If README says NOT RUN,
there is no fresh driver evidence; do not substitute older green-check logs.

For checklist items covered by those exact assertions, cite the driver command,
exit code, and relevant output as the action and evidence. Do not repeat covered
server/browser commands inside the agent sandbox. A sandbox permission error
from an attempted duplicate does not invalidate a successful driver execution.
Check that evidence actually measures each item's expected result: a passing
suite alone cannot satisfy additional assertions, manual visual comparisons,
real keyboard/zoom interactions, or Brian's required sign-off. Execute remaining
feasible checks, record genuine failures, and mark unmet human or environmental
prerequisites BLOCKED or NOT RUN. Never broaden permissions or invent a PASS.

Create VERIFICATION_REPORT.md.

For every check record:

- Check ID
- Action actually performed
- Expected result
- Actual result
- Evidence
- Status: PASS, FAIL, BLOCKED, or NOT RUN
- Defect reference, when applicable

Never mark an unexecuted check as PASS.
Never infer browser behavior from a successful compilation.
Do not silently repair failures while testing.
Do not edit source, tests, fixtures, snapshots, test configuration, or expected
results. Run checks without snapshot-update or accept-new-output options. The
driver freezes protected verification inputs and rejects a run that changes
them, even if commands exit zero. Put temporary probes and generated outputs
outside protected paths and preserve failing evidence for the repair stage.

Evidence means the specific output that establishes the result — the assertion
that fired, the status line, the log line with the error. Quote those, not
whole transcripts. The final audit reads this report and checks your evidence
against the claim, so it has to be the decisive part, not the surrounding
noise.

Use Summary, Findings, Assumptions, Open questions, Acceptance gate as the
VERIFICATION_REPORT.md sections. Keep per-check results in Findings. End with
exactly one `## Acceptance gate` containing only this table:

| ID | Required | Status | Evidence |
|---|---|---|---|

Include every checklist ID and any mandatory requirement omitted from the
checklist. Required is YES or NO; Status is PASS, FAIL, BLOCKED, NOT RUN, or N/A.
Every row needs nonempty evidence or a reference to its detailed result; no
literal pipe characters in cells. Required checks cannot become optional due
to unavailable prerequisites. N/A is allowed only with a requirement-based
explanation and Required NO. Include at least one required row. Reconcile
summary totals with the rows. The driver sends FAIL to a separate repair stage
and pauses on BLOCKED or NOT RUN instead of advancing to final audit.

After verification, create DEFECTS.md for every failed check and unresolved
blocker, preserving stable IDs across repairs. Record dispositions for prior
defects based on rerun evidence; do not silently drop them. If none remain,
write an explicit empty findings table. These two reports are the stage outputs.
