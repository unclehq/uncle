You are given a completed final-audit investigation below. Your only job is
to convert it into the required JSON object -- not to re-audit, not to
second-guess a finding, not to change a severity, a Blocks value, or the
verdict. Formatting is the entire task.

Return only one JSON object matching this contract as your final message; do not return Markdown:
`{"schema":"uncle.artifact/v1","kind":"final-audit","findings":[{"id":"FA-1","severity":"...","evidence":"...","affected_requirement":"...","required_correction":"...","blocks":"YES"}],"verdict":"READY"}`.

`findings` is one entry per table row in the investigation's `## Findings`
section, in the same order, with its ID, Severity, Evidence, Affected
requirement / invariant (as `affected_requirement`), Required correction, and
Blocks (as `blocks`, copied verbatim -- exactly `YES` or `NO`) copied over --
not paraphrased down to nothing, not merged, not dropped. If the
investigation's table was empty, `findings` is `[]`. `verdict` is the
investigation's closing conclusion, copied verbatim as exactly one of
`READY`, `READY WITH NON-BLOCKING ISSUES`, `NOT READY`.

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
