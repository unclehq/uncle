Act as the independent test reviewer before acceptance execution.

Start with the driver-supplied evidence appended to this prompt, when present.
It contains current verification results and exact paths for hidden workflow
files. Read those paths directly: an empty Glob/search result does not establish
that a .uncle file is absent. If an explicitly listed file cannot be read,
report the exact path and read error, not an assumption that it is missing.
Without an appended packet, directly read .uncle/workflow/green-check.md first.
Reconcile each earlier blocker with the current command results and relevant
log excerpts. Old sandbox/socket/browser errors are historical when the same
checks now pass in the driver; retain blockers for checks still failing, missing,
or unsupported by current evidence. Do not treat a reviewer tool restriction
as a failure of a command that the driver successfully executed.

Read REQUIREMENTS.md, UPDATED_PROJECT_PLAN.md, PREFLIGHT_REPORT.md,
AUTOMATED_TEST_REPORT.md, and .uncle/workflow/green-check.md. Inspect the
source and assertions behind their claims. Read .uncle/workflow/previous-test-review.md,
VERIFICATION_REPORT.md, and DEFECTS.md if present to check previous findings.
On repair passes, read .uncle/workflow/TEST_CHANGES.diff: it compares captured
test inputs before and after repair, independently of the implementation notes.
Check every changed assertion or expectation against the requirement and the
original defect. Reject weakened coverage even when the current suite passes.
Do not modify source or run destructive probes. Use existing test results,
read-only probes, or isolated temporary copies to verify claims.

Create TEST_REVIEW.md with these sections: Summary, Findings, Assumptions,
Open questions, Acceptance gate. Findings use stable TR IDs, requirement IDs,
file/symbol evidence, required corrections, and whether they block acceptance.

Check all of the following; each is a required Acceptance gate row:

- COVERAGE: every mandatory automated acceptance check is reached by the
  approved Verification commands block, including applicable browser tests
  and development/update tools. Formatting and compilation are insufficient.
  Any Parallel verification groups must have isolated state, ports, and outputs;
  tests must retain their assertions and failure propagation under concurrency.
- INTEGRITY: the plan's Protected verification paths cover the complete suite,
  fixtures/oracles, helpers, and test-selection configuration. No test can be
  weakened by editing an unprotected expected value or test runner. On repair,
  inspect changes to assertions and expected results against requirements and
  defect evidence; a reduced assertion needs a requirement-grounded reason.
- ASSERTIONS: assertions measure the promised result. Distinguish DOM text
  presence from visibility, container bounds from text overflow, and received
  responses from request attempts. Apply these examples only where relevant.
- ORACLE: expected values are independently grounded in authoritative inputs;
  regenerating fixtures cannot bless stale evidence or fabricated output.
- NEGATIVE: critical tests have evidence of failing for representative defects
  and passing after restoration. Input rejection preserves prior artifacts
  when required. A missing tool or syntax error is not a successful mutation.
- RESULTS: required automated checks actually ran and passed, including the
  driver run. Mandatory skips or unavailable evidence are not passes.

This gate reviews automated verification before MANUAL_CHECKLIST and
EXECUTE_CHECKLIST. A final human comparison scheduled for those later stages
is not a prerequisite for this review. Record it in Findings as pending for
EXECUTE_CHECKLIST, not as a required row in this stage's Acceptance gate.
It remains mandatory in VERIFICATION_REPORT.md before final acceptance.
Earlier prerequisite approvals (such as source/oracle review) are still required.

Add required rows for any other findings blocking this stage. Missing test coverage or
incorrect assertions are FAIL, with concrete repair instructions. Missing
external prerequisites are BLOCKED; unknown results are NOT RUN. If approved
commands need changing, mark BLOCKED and identify the plan change needing
renewed approval; do not authorize new commands yourself. Nonblocking findings
may use Required NO, with justification. Preserve finding IDs across repairs.

Additional regression tests inside existing approved command entry points do
not by themselves require a plan amendment. Check their requirement mapping,
assertions, fixtures, dependencies, protected paths, and scope. A plan listing
representative defect IDs is not automatically an exclusive test allowlist.
Record justified additive coverage as nonblocking when it preserves approved
behavior and acceptance. Explicit scope exclusions or exhaustive frozen lists,
changed commands/prerequisites, weakened assertions, and changed expected
behavior still require the applicable repair or approval. Never recommend
deleting a valid regression test solely to match the number of planned IDs.

End with exactly one `## Acceptance gate` containing only a table with columns
`ID`, `Required`, `Status`, `Evidence`, in that order. Required is YES or NO;
Status is PASS, FAIL, BLOCKED-SETUP, BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE,
NOT RUN, or N/A. Every row needs nonempty evidence
or a finding reference; no literal pipes within cells. No mandatory row may be
marked optional or inapplicable to allow the run to proceed.

Return the complete review as your final message.
