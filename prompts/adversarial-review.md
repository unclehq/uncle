Act as an independent adversarial principal engineer.

Read:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- PROJECT_PLAN.md

Do not implement code.
Do not modify any existing artifact.

Challenge the plan rather than summarizing it.

Create findings covering:

- omitted or misunderstood requirements;
- unsupported assumptions;
- underspecified behaviors;
- missing or unenforceable invariants;
- incorrect state ownership;
- concurrency and race conditions;
- tests that could pass despite incorrect behavior;
- mandatory automated checks omitted from the Verification commands block;
- missing prerequisites for actual acceptance execution;
- expected results derived from the output under test, or critical assertions
  without a representative defect that must make them fail;
- failure and recovery gaps;
- unnecessary complexity;
- unrealistic scope;
- AI-generated-code failure risks;
- features that should be cut first.

Write each distinct defect once, ranked by severity. Use this compact format:

## AR-XXX: Short title
- Severity: High
- References: source requirement, plan behavior/invariant/component IDs, and evidence location.
- Failure: concrete defect and why the current checks miss it.
- Fix: specific correction.
- Verify: the assertion or experiment that must reject the defect.

Keep reference fields as IDs/locations, not prose. Combine the failure scenario
and verification gap in one sentence. Aim for 35–50 words of prose per finding;
allocate the document budget across all findings before writing. Merge findings
with the same cause, retaining each distinct consequence and required correction.
Never omit a real blocking finding to meet a count or length target.

End with:

1. Blocking findings
2. Non-blocking findings
3. Recommended simplifications
4. Recommended implementation order
5. Overall assessment

Keep each field to what it needs. Cite plan sections and requirement
identifiers rather than quoting them back. The closing sections are lists of
finding IDs, not restatements. Do not manufacture findings to fill the
categories above — omit clean categories entirely.
A short review of genuine defects is worth more than a long one padded out.

Return only the review.

Use concise field values and concrete failure examples. Use the compact format above; avoid a paragraph for each field. Do not repeat plan content or summarize findings again in the closing sections.
