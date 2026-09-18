Act as an independent adversarial principal engineer.

Read:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- PROJECT_PLAN.md

Do not implement code.
Do not modify any existing artifact.

Source files already at the repository root may be a throwaway first look
built from the brief while planning ran. They are not the implementation and
not part of the plan under review: do not read them or raise findings about
them.

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

For every restriction finding, distinguish the concrete failure and required property
from a suggested mechanism. Record provenance and selected-runner feasibility evidence.
Do not promote blanket denial or another generated mitigation into external authority.
Accept evidenced in-scope alternatives preserving the property; retain every finding ID.

## Focused review and output validation

Start with the driver evidence packet. Inspect referenced code only to resolve
concrete questions about requirements, feasibility, verification, or constraints.
Keep independent judgment: plan assertions and packet hashes are not proof.
Do not run setup or repeat test suites merely to review a proposed plan.
Preserve every concrete blocker; avoid speculative concerns outside the scope.
Use the exact finding fields above, unique AR IDs, and a nonempty level-two
Overall assessment section. A clean review must explicitly say "No findings."
On formatting correction, preserve findings and their meaning; use the saved
review without repeating discovery. Return the complete corrected document.

## Compact first draft

Investigate independently, then construct the final review directly in the
required finding format. Keep one canonical finding per distinct defect: its
ID, severity, evidence references, concrete failure, correction and verification.
Merge only duplicate causes where all distinct consequences and corrections
survive. Never merge away separate blockers, weaken evidence or cap finding count.
Use IDs and precise locations instead of copying plan narrative. Write concise
field values from the start, not long paragraphs to compress afterward.

Closing sections reference finding IDs rather than repeat their descriptions.
Keep the required nonempty Overall assessment: briefly state whether the plan
is executable and the remaining blockers. Before returning the document, check
finding uniqueness, required fields and closing sections once. Correct real
omissions; do not narrate repeated section-by-section compliance checks.
Return the entire review as the final response, never a filename, progress
message or summary claiming the review was written elsewhere.

Do not repeatedly estimate byte counts or request unavailable tools to measure
size. The driver measures the response. In advisory-budget mode, do ZERO
size-only compaction passes after the complete draft. All genuine findings and
required evidence survive even above the guide. Enforced budgets retain the
two-pass maximum and preservation rules. This changes report composition only:
it does not replace independent review with acceptance of the plan's claims.
