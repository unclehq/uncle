You are the primary verification agent.

Read:

- BASELINE_REPORT.md
- CHANGE_SPEC.md
- CHANGE_PLAN.md
- MANUAL_CHECKLIST.md
- CHANGE_TEST_REPORT.md

MANUAL_CHECKLIST.md was written by an independent reviewer and you have not
seen it. Read it in full from disk before executing anything.

Execute every feasible Critical and Important check.


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

For each check include:

- Check ID
- Action actually performed
- Expected result
- Actual result
- Evidence
- Status: PASS, FAIL, BLOCKED, or NOT RUN
- Defect reference

Rules:

1. Never mark an unexecuted check as PASS.
2. Do not infer runtime behavior from compilation.
3. Compare preserved behavior against BASELINE_REPORT.md.
4. Distinguish expected behavioral changes from regressions.
5. Do not silently fix failures during checklist execution.
6. Record failures in DEFECTS.md.
7. Record environmental blockers separately.
8. Identify checks requiring a human browser, device, account, or external
   system.

End with:

- acceptance criteria summary
- preserved behavior summary
- changed behavior summary
- invariant summary
- regression summary
- unresolved defects
- recommendation

## Context economy

Everything a tool returns stays in context and is re-sent on every later turn.

- Use the fresh checklist-driver-checks evidence for covered automated checks.
  CHANGE_TEST_REPORT.md is context, not a substitute for current driver evidence.
- Use the quietest flag that still reports failures.
- Pipe unbounded output through `tail` or a summary flag. Capture the evidence
  a check asks for, not the whole transcript.
- Group checks that share preconditions so setup runs once.

These rules govern how you gather evidence, never which checks you run.

## Output economy

Time here belongs to running checks, not to writing about them.

- One line per field. The report is a table of results, not a narrative.
- Quote evidence only for FAIL and BLOCKED. For PASS, evidence is the command
  and its exit status.
- Do not restate the check text from MANUAL_CHECKLIST.md. Cite the check ID.
- Never compress by dropping a check. Every check ID in MANUAL_CHECKLIST.md
  appears in VERIFICATION_REPORT.md with a status, including NOT RUN.

The economy rules govern how you write, never what you run. If shortening the
report would mean skipping a check, run the check.
