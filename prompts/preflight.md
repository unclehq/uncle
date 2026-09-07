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
