You are given completed implementation notes below, already in their
required Markdown structure. Your only job is to convert them into the
required JSON object -- not to re-implement anything, not to change a file
list, a deviation, or a blocker. Formatting is the entire task. Do not read
or inspect the application code; the notes already say everything you need.

Write `.uncle/workflow/documents/IMPLEMENTATION_NOTES.json` as one JSON object, not Markdown,
matching this contract:

`{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"...","purpose":"...","plan_step":"...","behavior_or_invariant":"..."}],"deviations":[{"file":"...","reason":"..."}],"unresolved_concerns":["..."],"plan_blockers":[{"id":"...","class":"...","requirement_ids":["..."],"restriction_ids":["..."],"evidence":"...","independent_work":"...","question":"...","alternatives":"..."}]}`

Map the notes' `## Changed files` entries to `changed_files` (path, purpose,
plan_step, behavior_or_invariant), `## Deviations` entries to `deviations`
(file, reason), `## Unresolved concerns` bullets to `unresolved_concerns`
(an array of strings; `[]` if the notes said "None"), and `## Plan blockers`
entries to `plan_blockers` (id, class, requirement_ids, restriction_ids,
evidence, independent_work, and -- only for AUTHORITY entries -- question
and alternatives; `[]` if the notes said "None"). Copy every field over
verbatim, not paraphrased down to nothing.

Preserve every file, deviation, concern, and blocker the notes raised; do
not add one they didn't make, drop one they did, or fold two together to
save space.

Write it directly and correctly the first time. Do not try to validate the
JSON afterward with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final reply must contain the object exactly
once. Including an earlier draft alongside the final one, or the same
content twice, is rejected the same way a missing object is.

Do not implement code. Do not modify any file other than
`.uncle/docs/IMPLEMENTATION_NOTES.md` -- the implementation pass already did
that work.

## Implementation notes to convert
