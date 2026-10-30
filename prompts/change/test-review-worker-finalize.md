You are given your own earlier investigation of this acceptance row, written
before the driver's verification run finished. That run has now finished.
Read `.uncle/docs/AUTOMATED_TEST_REPORT.md` and `.uncle/workflow/green-check.md`
for its actual, final results. Your only job now is to decide the row's
status from those real results -- not to re-investigate from scratch, and
not to assume your earlier source-level read was complete.

The investigation below may already note defects it found from source alone;
those stand regardless of execution. But a status of PASS requires the
driver's own results to actually show the relevant check ran and passed --
never infer a pass merely because the source looked correct before the run
finished. If the driver's results show a relevant command failed, or never
ran, the row cannot be PASS no matter what the investigation concluded.

Return exactly one JSON object: `{"schema":"uncle.artifact/v1","kind":"test-review-worker-packet","rows":[{"id":"COVERAGE","status":"PASS","evidence":"..."}]}`.
Return every assigned acceptance row, with PASS, FAIL, BLOCKED-SETUP,
BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE, or NOT RUN. No Markdown or prose.
`evidence` is at most three sentences naming the file, symbol, requirement ID
or command output; do not paste logs or restate the plan.

Do not declare the stage's overall acceptance gate or write
`.uncle/docs/TEST_REVIEW.md` yourself. A separate reviewer reconciles every
worker's packet, verifies the evidence, and owns the only canonical
`.uncle/docs/TEST_REVIEW.md`.

## Your earlier investigation (written before results existed)

