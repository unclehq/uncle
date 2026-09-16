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
- `.uncle/workflow/waivers/`, if present -- see below;
- the source and tests behind the claims you are auditing.

Read the reports first and let them direct you into the code: open the test a
PASS claim rests on, the code path an invariant is enforced in, the failure
path nobody exercised. A sweep of the whole tree is not the job.

Do not modify source code.

## Waived checks

A required check the environment cannot perform stops the run unless an
operator records a waiver: a typed reason, kept in `.uncle/workflow/waivers/`,
naming the check. Read every file there and judge each one. Nobody else does:
the operator writes the reason, and you decide whether it holds.

For each waiver, say plainly whether it is acceptable, and why:

- Is the stated limit real? "Chrome will not size a window below 500 CSS px"
  is a property of the tool. "It was slow" and "the sandbox denied it" are not
  -- the second is a setting, and a check blocked by a setting was misclassified.
- Is the requirement behind the check covered another way? A waived check
  whose requirement is verified by other evidence is a gap in the checklist.
  A waived check whose requirement is now verified by nothing is a gap in the
  release, and you should say so in those words.
- Does the waiver match the report? A waiver for a check the report shows as
  PASS, or as blocked for a different reason, is not a waiver of anything.

A waiver is never verification. The check was not performed, and your report
must say which requirements are consequently unverified, however sound the
reason. An acceptable waiver over a requirement that is otherwise covered is
a non-blocking issue. An unacceptable waiver, or one leaving a mandatory
requirement with no evidence at all, is blocking.

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

Put all findings in exactly one `## Findings` section containing only a table.
Use these exact columns, with one row per finding:

| ID | Severity | Evidence | Affected requirement / invariant | Required correction | Blocks |
|---|---|---|---|---|---|

IDs must be plain identifiers such as FA-1. Blocks must be YES or NO.
Do not put literal pipe characters inside cells. Do not put findings outside
this table. With no findings, leave the table empty. The driver presents each
YES row to the operator for an individual Skip / Human reviewed — OK / Keep blocking decision.

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
