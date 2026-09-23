You are given a completed test-review investigation below. Your only job is
to convert it into the required JSON object -- not to re-investigate, not to
second-guess a finding, not to change a status. Formatting is the entire
task.

Return only one JSON object matching this contract as your final message; do not return Markdown:
`{"schema":"uncle.artifact/v1","kind":"acceptance-report","narrative":"...","rows":[{"id":"COVERAGE","required":true,"status":"PASS","evidence":"..."}]}`.

`narrative` holds the investigation's summary, findings, assumptions, and open
questions as one Markdown block. `rows` is one entry per required row named
in the investigation (COVERAGE, INTEGRITY, ASSERTIONS, ORACLE, NEGATIVE,
RESULTS) plus any further TR-N rows it raised. `required` is a JSON boolean:
true for the six mandatory rows and any finding the investigation marked as
blocking; false otherwise. `status` is exactly one of PASS, FAIL,
BLOCKED-SETUP, BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE, NOT RUN, N/A -- copy it
verbatim from the investigation, do not infer or adjust it. `evidence` is the
investigation's own evidence text for that row, copied over, not
paraphrased down to nothing.

Preserve every row and every finding the investigation raised; do not add one
it didn't make, drop one it did, or fold two together to save space. If the
investigation left a row's status ambiguous, use NOT RUN and quote the
ambiguous text in `evidence` rather than guessing a status.

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
