Act as an independent release-verification engineer.

A base verification checklist was written from the approved specification while
the implementation was still in progress. The implementation is now complete.
Your job is to reconcile the two and emit the final checklist.

Read:

- .uncle/workflow/MANUAL_CHECKLIST.base.md
- CHANGE_SPEC.md
- CHANGE_PLAN.md
- IMPLEMENTATION_NOTES.md
- CHANGE_TEST_REPORT.md
- .uncle/workflow/change.diff
- changed source files
- relevant unchanged source files

Do not modify source code.
Do not claim any check passed.

## What to do

1. Resolve every check marked `NEEDS-DETAIL`. Replace the placeholder action
   with the exact action against the code as built.
2. Add checks for anything the implementation did that the specification did
   not anticipate: recorded deviations, files changed that
   CHANGE_PLAN.md did not list, and new failure modes visible in the
   diff.
3. Add checks for any gap CHANGE_TEST_REPORT.md leaves open, including every
   item it marked `NOT RUN`.
4. Delete checks that the diff makes provably inapplicable. For each deletion,
   record the check ID and the reason in a `Removed checks` section. Never
   delete a check merely because it looks hard to run.
5. Update `Exclusive resources` and `Depends on` on any check whose real
   dependencies are only now visible. The base checklist was written while the
   implementation was still in progress, so a check that could not know which
   port it would bind may have declared nothing and been scheduled alone. New
   checks carry both fields like every other check.
6. Leave every other base check exactly as written. Do not rewrite checks for
   style.

New checks continue the base numbering. Do not renumber existing checks; their
IDs may already be referenced.

## Output

Emit the complete merged checklist, in the same format as the base, so that
MANUAL_CHECKLIST.md stands alone. Do not emit a patch.

Directly under the title, write one line:

`Base checks: <n>; resolved: <n>; added: <n>; removed: <n>`

End with:

- acceptance-criteria traceability
- preserved-behavior coverage
- changed-behavior coverage
- invariant coverage
- regression coverage
- removed checks

## Output economy

- One line per field.
- Do not restate IMPLEMENTATION_NOTES.md or the diff. Cite the file and line.
- Merge checks executed by the same action against the same preconditions.

Return only the checklist.

## Efficient checklist delivery

Use the driver evidence packet as an index, not as proof of coverage. Preserve
all required acceptance criteria. Where fresh driver evidence already covers an
assertion, keep its checklist mapping and cite the exact command/evidence to
inspect rather than inventing an equivalent manual rerun. Missing or stale
results still require execution. Identify genuinely human judgment separately
from automatable assertions; never invent a human observation.

Each check must have a concrete action, observable expected result, evidence
path, required-for-acceptance flag, exclusive resources, and dependencies. Use
stable unique MC IDs. Before returning, verify all required fields, dependency
references, and absence of dependency cycles. Correct malformed fields in the
current draft; return the complete checklist, not a progress message.

On a delta or repair pass, retain unaffected check IDs and wording. Change only
rows affected by implementation differences, unresolved findings, changed inputs,
or missing coverage. Compare the supplied hashes with the evidence used before
carrying a conclusion forward; if the prior basis is unavailable, recheck that
row. Record why a row was changed or removed. Never delete required checks merely
to reduce count, runtime, or report length. Write the final checklist once.
