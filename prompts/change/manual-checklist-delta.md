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
