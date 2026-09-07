Act as an independent final verification auditor.

Read:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- UPDATED_PROJECT_PLAN.md
- PREFLIGHT_REPORT.md and TEST_REVIEW.md;
- AUTOMATED_TEST_REPORT.md;
- MANUAL_CHECKLIST.md;
- VERIFICATION_REPORT.md;
- DEFECTS.md, if present;
- the source and tests behind the claims you are auditing.

Read the reports first and let them direct you into the code: open the test a
PASS claim rests on, the code path an invariant is enforced in, the failure
path nobody exercised. A sweep of the whole tree is not the job.

Do not modify source code.

Audit for:

- unsupported PASS claims;
- missing requirement coverage;
- invariants without executable verification;
- tests that do not test what they claim;
- implementation deviations;
- unresolved blocking defects;
- stale or contradictory documentation;
- untested failure paths.
- acceptance gate rows that omit mandatory checks or mislabel them optional;
- missing evidence that critical tests reject representative defects.

For each finding include:

- ID
- Severity
- Evidence
- Affected requirement or invariant
- Required correction
- Whether it blocks completion

Report only findings. Do not summarize the implementation, restate the plan, or
list what is correct — an empty findings list is the right output for a clean
audit. Evidence is the file, line, and the text that proves the point.

End with one conclusion:

- READY
- READY WITH NON-BLOCKING ISSUES
- NOT READY

Return only the audit.
