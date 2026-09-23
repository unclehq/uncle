You are given a completed requirements investigation below, already in its
required Markdown structure. Your only job is to convert it into the
required JSON object -- not to re-interpret, not to add or remove content,
not to resolve an ambiguity it left open. Formatting is the entire task.

Write .uncle/docs/REQUIREMENTS_INTERPRETATION.md in a single Write call, and
write it as one JSON object, not Markdown, matching this contract:

`{"schema":"uncle.artifact/v1","kind":"requirements-interpretation","sections":{"required_functionality":"...","optional_functionality":"...","constraints":"...","user_visible_behaviors":"...","system_behaviors":"...","failure_behaviors":"...","ambiguities":"...","assumptions":"...","explicit_non_goals":"...","definition_of_done":"..."}}`

Map each of the investigation's ten headings directly to its `sections` key:
Required functionality -> `required_functionality`, Optional functionality ->
`optional_functionality`, Constraints -> `constraints`, User-visible
behaviors -> `user_visible_behaviors`, System behaviors ->
`system_behaviors`, Failure behaviors -> `failure_behaviors`, Ambiguities ->
`ambiguities`, Assumptions -> `assumptions`, Explicit non-goals ->
`explicit_non_goals`, Definition of done -> `definition_of_done`. Each
value is exactly that section's content as one Markdown block (real
newlines in the JSON string) -- multi-line prose, bullet lists, and tables
all carried over verbatim, not summarized or trimmed. Every key is required
and must be a nonempty string; the investigation already ensured this.

Write it directly and correctly the first time. Do not try to validate the
JSON afterward with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final reply must contain the object exactly
once. Including an earlier draft alongside the final one, or the same
content twice, is rejected the same way a missing object is.

Do not implement code. Do not modify any file other than
`.uncle/docs/REQUIREMENTS_INTERPRETATION.md`.

## Investigation to convert
