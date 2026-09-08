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
are blocked, in the class that says why. Give the action needed to resolve
each blocker. Do not install
dependencies, alter requirements, or implement the application in this stage.

End with exactly one `## Acceptance gate` section containing only this table:

| ID | Required | Status | Evidence |
|---|---|---|---|

## Probe the capability, not its installation (binding)

A prerequisite is PASS only when you exercised the capability the acceptance
check will actually use, in the environment that stage will run in, and
recorded the output. The presence of a file, binary, package, or application
bundle is not evidence that it can be used.

Concretely, for a prerequisite that later checks depend on:

- a browser: launch the system default browser against a local URL and
  capture the result -- `open` on macOS, `start` on Windows, `xdg-open`
  on Linux. Record which browser answered: that setting is per-user, so
  the report has to say what the checks will actually run in rather than
  assume. A browser binary existing at some path is not a PASS, and
  neither is a headless run standing in for a check that needs a real
  window.
- a specific browser or automation protocol: prove that browser is
  installed here, not that some browser is. Chrome is a download on every
  platform, Safari does not exist off macOS, and CDP-based or headless
  harnesses drive only Chrome, Chromium, and Edge -- Safari needs
  `safaridriver` (admin, one-time) and Firefox needs `geckodriver`. If a
  planned check names an engine this machine does not have, that row is
  BLOCKED now, at preflight, where it is cheap.
- a local server or any check that serves the product: bind the port the check
  will use and record the bind succeeding. Sandboxed stages are denied network
  access -- including loopback binds -- unless the stage sets `network true` in
  `.uncle/config`, so a bind that works in a shell can still fail in the stage.
- a GUI, windowed, or interaction-dependent check: confirm the session can
  actually drive it. If no GUI automation is available, the row is
  BLOCKED-SETUP when consent or an install would provide it, and
  BLOCKED-IMPOSSIBLE when the platform cannot do it at all.
- a human sign-off: an unsigned approval file is BLOCKED-HUMAN, not PASS.

Any capability that cannot be exercised now is blocked, and which kind of
blocked is the most useful thing this report can say:

- `BLOCKED-SETUP` -- one action would make it available. Name the action:
  `safaridriver --enable` (admin), granting Accessibility consent, committing
  the tree, installing a browser.
- `BLOCKED-HUMAN` -- it waits on a person. Name who and for what.
- `BLOCKED-IMPOSSIBLE` -- this environment cannot do it as specified, and no
  effort will change that. Say what the limit is: a browser that will not size
  a window below 500 CSS px cannot show a real 320px viewport; a protocol that
  does not exist for an engine cannot drive it.

That distinction is what later stages are held to. A row marked
BLOCKED-IMPOSSIBLE tells the checklist not to write a check that depends on it
and tells the operator to amend the plan or the requirement, which is cheap
now and expensive after implementation. A bare `BLOCKED` is read as
BLOCKED-SETUP, so leaving it unclassified claims the problem is arrangeable.

Add a row for every capability the planned checks will need, not only the ones
that worked. A capability nobody probed is a capability the checklist has no
evidence for, and the checklist is required to cite these ids.

Add one row for every prerequisite, with stable IDs. Required is YES or NO;
Status is PASS, FAIL, BLOCKED-SETUP, BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE,
NOT RUN, or N/A. Evidence is nonempty and cites
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
A missing approval or input remains required and blocked, and which class it
gets decides whether the run may implement:

- `BLOCKED-SETUP` when the next stage cannot proceed without it -- an input
  file that has to exist before the code can be written against it. Name the
  action. This stops the run here, which is the point of this gate.
- `BLOCKED-HUMAN` when a person's sign-off is consumed later, at verification.
  Implementation does not read a signature, so the run continues past it and
  the verification gates block on it instead. Say who owes what.

Do not mark a signature BLOCKED-SETUP to force an early stop, and do not mark
a missing input BLOCKED-HUMAN to slip past this gate.
For example: available Python is a PASS prerequisite; an unbuilt site's content
test is a future NOT RUN result outside this table. Named reviewer access is a
prerequisite; final HTML sign-off is a future result outside this table.

Before writing, inspect each gate row: if completing it requires creating the
implementation, move that row to Findings with its real pending status.
