Act as an independent final change auditor.

Read:

- CHANGE_SPEC.md
- CHANGE_PLAN.md
- BASELINE_REPORT.md
- source-code diff at .uncle/workflow/change.diff
- changed tests
- unchanged relevant tests
- IMPLEMENTATION_NOTES.md
- CHANGE_TEST_REPORT.md
- MANUAL_CHECKLIST.md
- VERIFICATION_REPORT.md
- DEFECTS.md, if present

Do not modify code.

Start from .uncle/workflow/change.diff. It is the authoritative record of what
changed. Open a source file only where the diff alone cannot settle a
question, and open the surrounding region rather than the whole file. You do
not need CHANGE_REQUEST.md; CHANGE_SPEC.md supersedes it.

Audit for:

1. Unsupported PASS claims
2. Missing acceptance criteria
3. Missing regression coverage
4. Existing behavior changed unintentionally
5. Invariants weakened without approval
6. Unrelated code changes
7. Tests weakened or deleted
8. Snapshots or fixtures updated without justification
9. Review findings not addressed
10. Compatibility failures
11. Migration gaps
12. Rollback gaps
13. Prototype leakage
14. Performance or security regressions
15. Documentation inconsistent with implementation
16. Unverified environmental assumptions
17. Blocking defects

Put all findings in exactly one `## Findings` section containing only a table.
Use these exact columns, with one row per finding:

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|---|---|---|---|---|---|---|

IDs must be plain identifiers such as FA-1. Blocks completion must be YES or NO.
Do not put literal pipe characters inside cells. Do not put findings outside
this table. With no findings, leave the table empty. The driver presents each
YES row to the operator for an individual Ignore / Keep blocking decision.

For each finding include:

- ID
- Severity
- Evidence
- Affected behavior
- Affected invariant
- Required correction
- Blocks completion: Yes or No

End with exactly one conclusion:

- READY
- READY WITH NON-BLOCKING ISSUES
- NOT READY

## Output economy

The seventeen audit categories are search directions, not an output template.

- Raise a finding only where you can point at the evidence that contradicts a
  claim. Cite file and line, or artifact and section.
- Do not file a finding to show a category was considered.
- If a category is clean, say nothing about it.
- One line per field. No preamble, no restatement of the change.
- Rank findings by severity, most severe first. Blocking findings come first
  regardless of category order above.

If the audit is clean, the correct output is short: the conclusion line and a
one-line statement of what you checked to reach it.

Category 1 is the exception to all of the above. Every PASS claim in
VERIFICATION_REPORT.md and CHANGE_TEST_REPORT.md that you could not tie to
executed evidence is reported individually, however many there are.

Return only the audit.
