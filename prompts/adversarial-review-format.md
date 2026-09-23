You are given a completed adversarial-review investigation below. Your only
job is to convert it into the required JSON object -- not to re-investigate,
not to second-guess a finding, not to change a severity or verdict.
Formatting is the entire task.

Return only one JSON object matching this contract as your final message; do not return Markdown:
`{"schema":"uncle.artifact/v1","kind":"adversarial-review","findings":[{"id":"AR-001","title":"...","severity":"...","references":"...","failure":"...","fix":"...","verify":"..."}],"overall_assessment":"..."}`.

`findings` is one entry per AR-XXX finding in the investigation, in the same
order, with its ID, title, and the five fields (severity, references,
failure, fix, verify) copied over -- not paraphrased down to nothing, not
merged, not dropped. If the investigation reported no findings, `findings`
is an empty array. `overall_assessment` is the investigation's own Overall
assessment section as one string; fold the Blocking findings, Non-blocking
findings, Recommended simplifications, and Recommended implementation order
lists into it, referencing finding IDs the same way the investigation did.

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
