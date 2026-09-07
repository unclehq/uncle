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

Use this format for every finding:

## AR-XXX: Finding title

- Severity:
- Affected requirement:
- Affected behavior:
- Affected invariant:
- Failure scenario:
- Why current verification may miss it:
- Recommended correction:
- Proposed verification:

End with:

1. Blocking findings
2. Non-blocking findings
3. Recommended simplifications
4. Recommended implementation order
5. Overall assessment

Keep each field to what it needs. Cite plan sections and requirement
identifiers rather than quoting them back. The closing sections are lists of
finding IDs, not restatements. Do not manufacture findings to fill the
categories above — a category with nothing real in it gets one line saying so.
A short review of genuine defects is worth more than a long one padded out.

Return only the review.
