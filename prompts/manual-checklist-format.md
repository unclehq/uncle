You are given a completed manual-checklist investigation below. Your only
job is to convert it into the required JSON object -- not to re-investigate,
not to second-guess a check, not to change a status or a field. Formatting
is the entire task.

Return only one JSON object matching this contract as your final message; do not return Markdown:
`{"schema":"uncle.artifact/v1","kind":"manual-checklist","checks":[{"id":"MC-1","section":"...","priority":"...","required":true,"related_requirement":"...","related_behavior":"...","related_invariant":"...","prerequisites":"...","needs":"PF-7","exclusive_resources":["port:5173"],"depends_on":[],"exact_action":"...","expected_result":"...","evidence_to_capture":"..."}],"traceability":"..."}`.

`checks` is one entry per `## MC-N: ...` block in the investigation, in the
same order. Map each block's fields directly: Section, Priority, Required
(as a JSON boolean), Related requirement/behavior/invariant, Prerequisites,
Needs, Exact action, Expected result, Evidence to capture. Leave a field
`null` or omit it only when the investigation itself left it blank or said
"(none)". `exclusive_resources` and `depends_on` are JSON arrays: split the
investigation's comma-separated Exclusive resources and Depends on text into
array entries; `[]` when it said "(none)" or was empty. If the investigation
set Status on a check, copy it verbatim as `status` (one of BLOCKED-SETUP,
BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE) and copy Evidence of unavailability
verbatim; otherwise omit both -- do not invent a status the investigation
did not give. `traceability` is the investigation's `## Traceability`
section as one Markdown block.

Preserve every check the investigation raised; do not add one it didn't
make, drop one it did, merge two together, or reorder them. If a field's
value is ambiguous in the investigation, copy the ambiguous text through
rather than guessing.

Write it directly and correctly the first time. Do not try to validate the
JSON beforehand with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct, not
yours to verify in advance. If you reconsider your answer partway through,
revise silently -- the final reply must contain the object exactly once.
Including an earlier draft alongside the final one, or the same content
twice, is rejected the same way a missing object is. Do not narrate your
plan for it, name the file it covers, or summarize what you are about to
write -- any of that as your final message is treated as no document at all
and rejected. Skip straight to the JSON object; it is the only acceptable
reply.

## Investigation to convert
