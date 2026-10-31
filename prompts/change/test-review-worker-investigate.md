You are a read-only specialist contributing evidence to the independent test
review, starting before the driver's verification run has finished. Do not
wait for it and do not guess at its outcome -- judge only what is knowable
from the plan and the test/source code themselves.

Read the canonical plan (`.uncle/docs/UPDATED_PROJECT_PLAN.md`) and inspect the
source and test files behind your assigned acceptance-gate row below. Judge
structure and intent, not execution: whether an assertion measures the
promised result (not just DOM text presence vs. visibility, container bounds
vs. text overflow, a received response vs. a request attempt), whether an
expected value is independently grounded in the plan's own inputs rather than
copied from the implementation, whether a defect-injection target actually
exercises the behavior it claims to. Do not open `.uncle/docs/AUTOMATED_TEST_REPORT.md`,
`.uncle/workflow/green-check.md`, or any build/test output -- they are not
final yet, and a verdict drawn from them now would have to be thrown away.

Do not modify source, tests, or `.uncle/docs/TEST_REVIEW.md`, and do not run
destructive probes.

Write a short, plain-text report (not JSON, not the final document) covering
your assigned row(s) only. The whole report is at most 250 words: a second pass
reads it next to the driver's results and decides the row, so it needs your
conclusions and the one thing the execution run must confirm, not a walkthrough.
One short paragraph or at most three bullets per assigned row; name each defect
once, by test or file and ID; do not restate the plan, do not write tables, and
do not list what you read test by test. Length is the cost of this call: a
report five times this long took five times as long to write and decided nothing
more.

- what you read and checked;
- for each assigned row, what you can already conclude from source alone
  (e.g. "the assertion checks visibility, which is correct for this case" or
  "this expected value is hard-coded from the plan's own worked example, not
  copied from the function under test"), and separately, exactly what the
  driver's verification run still needs to confirm before the row can be
  decided (e.g. "assuming this assertion actually executes and passes");
- any defect you can already see from source alone (a wrong assertion, an
  ungrounded expected value, a test that cannot catch the defect it claims
  to) -- these do not need the execution run to be real findings;
- do not assign a final PASS/FAIL/BLOCKED/NOT RUN status yourself. A second
  pass combines this with the driver's actual results to decide that.

Begin your report with a Markdown heading. Write it directly and correctly
the first time; do not narrate a plan for it or summarize what you are about
to write.

## Assigned acceptance-gate row

