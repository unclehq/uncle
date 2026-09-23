You are given a completed preflight investigation below, already in its
required Markdown structure. Your only job is to convert it into the
required JSON object -- not to re-probe anything, not to change a status,
not to derive another file. Formatting is the entire task.

Write .uncle/docs/PREFLIGHT_REPORT.md in a single Write call, and write it
as one JSON object, not Markdown, matching this contract:

`{"schema":"uncle.artifact/v1","kind":"acceptance-report","narrative":"...","rows":[{"id":"G-1","required":true,"status":"PASS","evidence":"..."}]}`

`narrative` is the investigation's `## Summary`, `## Findings`, `##
Assumptions`, and `## Open questions` sections, concatenated as one
Markdown block (real newlines in the JSON string), in that order. `rows` is
one entry per row of the investigation's `## Acceptance gate` table: `id` is
its ID cell, `required` is a JSON boolean (`true` for `YES`, `false` for
`NO`), `status` is its Status cell copied verbatim (one of `PASS`, `FAIL`,
`BLOCKED-SETUP`, `BLOCKED-HUMAN`, `BLOCKED-IMPOSSIBLE`, `NOT RUN`, `N/A`),
`evidence` is its Evidence cell copied verbatim, not paraphrased down to
nothing. Do not put the Acceptance gate table into `narrative`; the driver
renders it back in from `rows`.

Preserve every row and every finding the investigation raised; do not add
one it didn't make, drop one it did, or fold two together to save space.

Write it directly and correctly the first time. Do not try to validate the
JSON afterward with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final reply must contain the object exactly
once. Including an earlier draft alongside the final one, or the same
content twice, is rejected the same way a missing object is.

Do not implement code. Do not derive or modify any file other than
`.uncle/docs/PREFLIGHT_REPORT.md` -- the investigation pass already derived
whichever pre-implementation inputs it needed to.

## Investigation to convert
