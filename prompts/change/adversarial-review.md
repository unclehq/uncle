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
