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
- .uncle/workflow/implementation-completion.txt, if present
- matching records under .uncle/workflow/waivers/, if present

Waivers permit review of partial delivery; they do not implement missing behavior
or make a check pass. Identify waived acceptance rows and the operator's reasons
in the audit, and assess the remaining delivery honestly.

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
YES row to the operator for an individual Skip / Human reviewed — OK / Keep blocking decision.

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

If the audit is clean, return the Findings heading, the required table header
and separator with no finding rows, then READY. Do not omit the empty table.

Category 1 is the exception to all of the above. Every PASS claim in
VERIFICATION_REPORT.md and CHANGE_TEST_REPORT.md that you could not tie to
executed evidence is reported individually, however many there are.

Return only the audit.

Read .uncle/workflow/plan-executability/assessment.md, plan-recovery.json and
 delivery-summary.tsv under .uncle/workflow when present. Compare archived evidence
and live verification results against delivery claims. A WAIVED row permits only
explicitly scoped workflow advancement, never implemented-and-verified delivery.
Report completion with waivers as "workflow complete with waived acceptance".

## Evidence and retry economy

Use the driver evidence packet to locate current results and changed inputs.
Hashes establish identity, not correctness. Match each PASS to its exact
assertions and execution evidence. Rerun only checks with missing, stale,
contradictory, or insufficient evidence; do not repeat an entire suite merely
because this is a new review stage. Human observations cannot be inferred.
Before returning, verify the Findings table fields, unique IDs, YES/NO blocking
values, and final verdict. Return the complete audit once, without progress text.

## Compact first audit

Start with the dedicated audit-evidence JSON index supplied by the driver. It
contains reported claim rows, literal references, command/result records and
explicit missing/empty-file statuses. It does not prove any claim. Use source
line numbers to inspect the exact assertions and raw execution evidence. Claims
not extractable as table rows still require review in the source reports.

Audit each acceptance claim once. Resolve its requirement, assertion, executed
command and current evidence; batch independent reads. Do not repeatedly glob
for files already inventoried as absent or reopen unchanged reports just to
confirm they were read. Recheck only after an input change or a concrete gap.
Missing or header-only records are not successful delivery evidence. Keep every
unsupported PASS finding; do not skip a claim because its evidence is inconvenient.
Rerun a check only for missing, stale, contradictory or insufficient evidence,
not to repeat a complete passing suite at the audit boundary.

Construct the required Findings table directly, one row per distinct defect,
with exact evidence, required correction and YES/NO blocking value. Refer to IDs
instead of repeating plan prose. Preserve every blocker and waiver scope. End
with the required verdict; do not append a narrative of clean checks or a recap.
Perform one consistency check between findings and verdict before returning the
complete audit. In advisory-budget mode do ZERO size-only compaction passes;
preserve mandatory findings even above the guide. The driver measures size.
Enforced budgets retain the two-pass limit. Independent judgment, evidence
verification and all acceptance gates remain mandatory.
