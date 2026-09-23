You are given a completed project-plan investigation below, already in its
required Markdown structure. Your only job is to convert it into the
required JSON object -- not to re-plan, not to second-guess a decision, not
to add or remove a step. Formatting is the entire task.

Write .uncle/docs/PROJECT_PLAN.md as one JSON object, not Markdown, matching
this contract:

`{"schema":"uncle.artifact/v1","kind":"plan","narrative":"...","verification_commands":"..."}`

`verification_commands` is the investigation's `## Verification commands`
fenced block, copied verbatim, as plain text with no fence markers and no
surrounding heading -- the driver renders that heading and fence back in.
`narrative` is everything else in the investigation -- every other section,
including the numbered sections, both tables, and the implementation steps
with their `Owns:`/`Depends on:` fields -- copied over completely, not
summarized or trimmed. Do not put a `## Verification commands` heading
inside `narrative`; that field is that section.

Preserve every behavior, invariant, component, and implementation step the
investigation raised; do not add one it didn't make, drop one it did, or fold
two together to save space. If the investigation left something ambiguous,
carry the ambiguity into `narrative` as written rather than resolving it
yourself -- resolving it is a planning decision, not a formatting one.

Write it directly and correctly the first time. Do not try to validate the
JSON beforehand with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final file must contain the object exactly
once. Do not narrate a plan for it, describe what you are about to write, or
draft it in chat first -- write the file directly.

Do not implement code. Do not modify `.gitignore` or any file other than
`.uncle/docs/PROJECT_PLAN.md` -- the investigation pass already did that
work.

## Investigation to convert
