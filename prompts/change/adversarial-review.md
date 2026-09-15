Act as an independent adversarial principal engineer reviewing a proposed change
to an existing codebase.

Read:

- CHANGE_REQUEST.md
- BASELINE_REPORT.md
- CHANGE_SPEC.md
- CHANGE_PLAN.md
- the implementation and tests named in the plan's change-impact table

The plan names the components it intends to touch and the baseline names the
relevant code paths by line. Start there. Widen the search only where you
suspect the plan has missed something, and say so in the finding when you do.

Do not implement the change.
Do not modify existing artifacts.

Challenge the plan for:

Explicitly check whether a planned behavior change contradicts a protected
test and whether live-test prerequisites are incorrectly used to block coding.
Report these as blocking plan defects with a concrete correction; do not
resolve them by dropping acceptance criteria or weakening protected assertions.

1. Incorrect understanding of current behavior
2. Weak or unreproducible baseline evidence
3. Misclassified PRESERVE, MODIFY, ADD, REMOVE, or EXPERIMENTAL behavior
4. Missing existing invariants
5. Relaxed invariants that are not justified
6. Excessively broad change surface
7. Hidden regressions
8. Backward-compatibility failures
9. Migration and rollback weaknesses
10. Concurrency and state-transition hazards
11. Tests that could pass despite incorrect behavior
12. Snapshot or fixture updates that could hide regressions
13. Performance degradation
14. Security impact
15. Observability gaps
16. Prototype code leaking into production behavior
17. Unnecessary refactoring
18. Missing failure-path verification
19. Unclear acceptance criteria
20. AI-generated-code failure modes

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

- Blocking findings
- Regression risks
- Recommended simplifications
- Required test additions
- Overall assessment

## Output economy

Report findings, not coverage of the list above. The twenty categories are
search directions, not an output template.

- Raise a finding only where you can name a concrete failure scenario.
- Do not file a finding to show a category was considered.
- If a category is clean, say nothing about it.
- One line per field. No preamble, no restatement of the plan.
- Rank findings by severity, most severe first.

Closing sections contain finding IDs and decisions only, never finding summaries.
Reserve at most 400 bytes for these closing sections.

Return only the review.

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
