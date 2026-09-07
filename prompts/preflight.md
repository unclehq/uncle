You are the primary acceptance-prerequisite verifier.

Read REQUIREMENTS.md, REQUIREMENTS_INTERPRETATION.md, and
UPDATED_PROJECT_PLAN.md. Create PREFLIGHT_REPORT.md before implementation.

Use these sections, in order: Summary, Findings, Assumptions, Open questions,
Acceptance gate. In Findings, inventory every mandatory acceptance check and
its prerequisites: commands and dependencies, browser binaries and interaction
access, source rendering, credentials or services, representative input data,
and independent reviewers where required. Probe available capabilities and
record exact commands and results. Do not run future implementation commands
whose files do not exist yet; check that their execution environment exists.

A manual or independent review need not happen before there is a product, but
its execution path must be confirmed: who or what will perform it, with what
access, and how results will return to the workflow. Do not invent a reviewer
or assume an interactive session is available. Missing required capabilities
are BLOCKED. Give the action needed to resolve each blocker. Do not install
dependencies, alter requirements, or implement the application in this stage.

End with exactly one `## Acceptance gate` section containing only this table:

| ID | Required | Status | Evidence |
|---|---|---|---|

Add one row for every prerequisite, with stable IDs. Required is YES or NO;
Status is PASS, FAIL, BLOCKED, NOT RUN, or N/A. Evidence is nonempty and cites
observed output or a recorded arrangement, not an assertion of readiness.
Use NO only for an explicitly optional or inapplicable prerequisite, citing
the requirement that establishes this. Include at least one required row.
Do not put literal pipe characters in cells. Missing mandatory prerequisites
must remain required. The driver will pause until all required rows pass.

Write only PREFLIGHT_REPORT.md.

## Preflight gate scope (binding)

The Acceptance gate table contains only prerequisites that must be satisfied
BEFORE implementation starts. It must not contain future product acceptance
results, implementation outputs, or tests that require those outputs. Otherwise
the driver cannot start the work needed to satisfy its own gate.

Keep AC/AT/TV results, future README execution, and implementation-time
normalization documentation in Findings as NOT RUN. Do not copy those rows into
the Acceptance gate, mark them PASS, or relabel mandatory acceptance as optional.
Their later verification and independent-review gates remain mandatory.

Gate on the runtime/tool availability, source inputs, reviewer arrangements,
and any explicitly required pre-implementation approvals or frozen fixtures.
A missing pre-implementation approval or input remains required and BLOCKED.
For example: available Python is a PASS prerequisite; an unbuilt site's content
test is a future NOT RUN result outside this table. Named reviewer access is a
prerequisite; final HTML sign-off is a future result outside this table.

Before writing, inspect each gate row: if completing it requires creating the
implementation, move that row to Findings with its real pending status.
