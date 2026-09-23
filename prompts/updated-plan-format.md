You are given a completed updated-plan investigation below, already in its
required Markdown structure. Your only job is to convert it into the
required JSON object -- not to re-plan, not to second-guess a decision, not
to change a disposition. Formatting is the entire task.

Write .uncle/docs/UPDATED_PROJECT_PLAN.md as one JSON object, not Markdown,
matching this contract:

`{"schema":"uncle.artifact/v1","kind":"plan","narrative":"...","verification_commands":"...","protected_verification_paths":"...","dispositions":[{"finding":"AR-001","disposition":"Accepted","reason":"...","plan_change":"..."}]}`

`verification_commands` is the investigation's `## Verification commands`
fenced block, copied verbatim, as plain text with no fence markers and no
surrounding heading -- the driver renders that heading and fence back in.
`protected_verification_paths` is the `## Protected verification paths`
fenced block, copied the same way. `dispositions` is one entry per row of
the `## Adversarial review dispositions` table: `finding` is the row's
Finding cell, `disposition` is its Disposition cell (exactly one of
`Accepted`, `Partially accepted`, `Rejected`, `Deferred`), `reason` and
`plan_change` are its Reason and Exact plan change cells. `narrative` is
everything else in the investigation -- every other section, including any
`## Parallel verification groups` block, which stays as Markdown text
inside `narrative` since the driver does not give it a dedicated field --
copied over completely, not summarized or trimmed. Do not put a
`## Verification commands`, `## Protected verification paths`, or
`## Adversarial review dispositions` heading inside `narrative`; those three
fields are those sections.

Preserve every behavior, invariant, restriction, implementation step, and
disposition the investigation raised; do not add one it didn't make, drop
one it did, or fold two together to save space. If the investigation left
something ambiguous, carry the ambiguity into `narrative` as written rather
than resolving it yourself -- resolving it is a planning decision, not a
formatting one.

Write it directly and correctly the first time. Do not try to validate the
JSON beforehand with a shell command, a linter, node, jq, or any other tool
-- most stages do not have one available, and hunting for one wastes turns.
A syntax mistake is the driver's problem to catch and ask you to correct,
not yours to verify in advance. If you reconsider your answer partway
through, revise silently -- the final file must contain the object exactly
once. Do not narrate a plan for it, describe what you are about to write, or
draft it in chat first -- write the file directly.

Do not implement code. Do not modify `.gitignore` or any file other than
`.uncle/docs/UPDATED_PROJECT_PLAN.md` -- the investigation pass already did
that work.

## Investigation to convert
