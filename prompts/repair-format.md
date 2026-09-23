You are given completed repair notes below, already in their required
Markdown structure. Your only job is to merge them into
`.uncle/docs/IMPLEMENTATION_NOTES.md` -- not to re-repair anything, not to
change a file list, a deviation, or a blocker the notes describe. Do not
read or inspect the application code; the notes already say everything you
need.

First, read the current `.uncle/docs/IMPLEMENTATION_NOTES.md` with your
Read tool. It is one JSON object matching the `implementation-notes` schema
below. Then write the complete updated file as one JSON object, not
Markdown, matching this contract:

`{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"...","purpose":"...","plan_step":"...","behavior_or_invariant":"..."}],"deviations":[{"file":"...","reason":"..."}],"unresolved_concerns":["..."],"plan_blockers":[{"id":"...","class":"...","requirement_ids":["..."],"restriction_ids":["..."],"evidence":"...","independent_work":"...","question":"...","alternatives":"..."}]}`

Merge, do not replace: start from the current file's `changed_files`,
`deviations`, `unresolved_concerns`, and `plan_blockers`, and preserve every
entry this repair pass did not touch -- unrelated dispositions from earlier
passes are still true and still required. Then apply the repair notes below:

- add or update a `changed_files` entry for each file the notes' `## Changed
  files` section lists (update in place if the current file already has an
  entry for that path, add a new entry otherwise);
- add a `deviations` entry for each item in `## Deviations`;
- merge `## Unresolved concerns` into `unresolved_concerns`, without
  duplicating an item the current file already recorded;
- add a `plan_blockers` entry for each item in `## Plan blockers`;
- for each finding named in `## Findings not fixed`, make sure its status is
  reflected honestly somewhere in the merged document (as an
  `unresolved_concerns` entry or a `plan_blockers` entry, matching what the
  notes said) -- do not silently drop it and do not mark it resolved.

Copy every field over verbatim, not paraphrased down to nothing. If either
"None" is stated for a section, that section contributes nothing new, but
the current file's own existing entries for that array are still preserved.

Write it directly and correctly the first time. Do not try to validate the
JSON afterward with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final reply must contain the object exactly
once. Including an earlier draft alongside the final one, or the same
content twice, is rejected the same way a missing object is.

Do not implement code. Do not modify any file other than
`.uncle/docs/IMPLEMENTATION_NOTES.md` -- the repair pass already did that
work.

## Repair notes to merge in
