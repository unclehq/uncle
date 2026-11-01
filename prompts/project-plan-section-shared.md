## Acceptance provenance

A mandatory human sign-off needs an explicit user/source requirement, or a
specific judgment that available automated evidence cannot establish. Cite that
source or explain the non-automatable property. A generated plan or an earlier
model's assumption is not independent authority to add a human approval.
"Browser verification" does not itself require a person; automated browser
assertions can establish exactly what they measure. Do not invent a requirement
to approve an ordinary engineering choice such as an unspecified browser engine.
Never claim a human observation occurred. Keep genuinely subjective judgments
unverified until observed or explicitly waived. If a prior generated obligation
has no source, identify the conflict and resolve it in the report rather than
silently treating it as user intent or silently claiming PASS.

## Section delivery

Use supplied canonical JSON as the requirements source. The driver retains all
schema validation, lane checks, assembled-plan checks, reviews and gates.
Use complete evidence for an assertion; excerpts and planning assumptions are
not verification results. Do not enumerate workflow state or read credentials.

## Counts and totals

Never write a total you derived from a list as a literal ("19 keys", "all 12 mutants"). Point at the list
instead ("every key in A-2"), so the number cannot disagree with its own enumeration. When a count has to
appear, write the items out and count them one by one before you write the number. A plan once said
"19 keys (digits, decimal, four operators, equals, clear, backspace)" for a list that adds up to 18; a test
copied the 19, and the correct implementation failed it.

Use current stable test tooling resolved at install time (`latest` or a `^` range
based on the current release), including Playwright, Vite and Vitest when used;
never pin an old Playwright or an old Node. Keep the installed Node: do not
install or switch Node versions. If `package.json` sets `engines.node`, its
range must accept the installed Node major. Record resolved versions in the
lockfile; reuse a compatible installation. If an approved plan conflicts,
report it through the existing review/repair path; do not silently edit it.
