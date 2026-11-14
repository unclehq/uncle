## AR-001: The permitted scope cuts remove required behavior without changing acceptance criteria.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §21 permits cutting the greenfield prompt, dotnet/stack mappings, and narrative append; §1, D-1, and CHANGE_SPEC.json BH-5/BH-8 require these deliverables. Remove those cuts so implementation and acceptance checks use the same scope.
- Failure: The permitted scope cuts remove required behavior without changing acceptance criteria. Add: “The four prompt updates, all D-1 mappings, and the preflight narrative record are required deliverables and may not be cut without an approved scope revision.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: D-1 gives competing dune package names and an ambiguous OCaml mapping.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 says “ocaml,ocamlfind,ocamlc,ocamlopt” map to “ocaml/ocaml-findlib” and lists both ocaml-dune and dune for dune. Specify one mapping per executable so installer code and argv assertions cannot select different packages.
- Failure: D-1 gives competing dune package names and an ambiguous OCaml mapping. Replace it with: “Map ocaml, ocamlc, and ocamlopt to ocaml; ocamlfind to ocaml-findlib; and dune to ocaml-dune.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Multiple missing tools have no clear aggregate time limit.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-3 specifies “300s per install,” while §22 describes installer delay as a “300s cap.” With several package installs these bounds differ; define one total budget so workflow timing and timeout tests agree.
- Failure: Multiple missing tools have no clear aggregate time limit. Add: “All package-install attempts share one 300-second deadline; each attempt receives only the remaining time, and unattempted packages are recorded as skipped when the deadline expires.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: A failed installation can still leave some requested tools available, but the artifacts prescribe conflicting preflight

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 step 3 requires preflight to reflect installed tools, but §12 says install failure produces Missing runtime; CHANGE_SPEC.json §8 similarly says the check remains missing after nonzero exit or timeout. Specify partial-success behavior so a failed batch does not force successfully installed tools into BLOCKED-SETUP.
- Failure: A failed installation can still leave some requested tools available, but the artifacts prescribe conflicting preflight results. Add: “After every install outcome, preflight checks actual tool availability and reports Missing runtime only for tools still absent.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Regression coverage is ambiguous: the plan requires full runners but says the default runner selects only critical suite

- Severity: MEDIUM
- References: CHANGE_PLAN.json §16 states that the default runner only runs critical-suites.txt; §17 requires full Python and shell runners, while the implementation sequence specifies only baseline commands plus two targeted suites. Implementers could satisfy the command checklist while omitting existing noncritical regression coverage.
- Failure: Regression coverage is ambiguous: the plan requires full runners but says the default runner selects only critical suites. Add: “Run both regression runners with explicit full-suite selection; retain the two targeted new-suite commands as additional checks.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Multiple missing toolchains can exceed the promised 300-second delay because the timeout is defined per install.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-3 specifies “Timeout 300s per install,” but §22 mitigates hosted-run slowdown with a “300s cap”; §1 runs installation synchronously before the background probe. Separate installs for several missing tools could multiply the delay, creating a hosted workflow latency regression.
- Failure: Multiple missing toolchains can exceed the promised 300-second delay because the timeout is defined per install. Add: “All installer subprocesses share one 300-second deadline; when it expires, record remaining packages as skipped and continue to preflight.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The timeout does not define what happens to privileged installer descendants, allowing package changes to continue after

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-3 specifies a 300-second timeout; §12 says timeout is recorded and the run continues; CHANGE_SPEC.json §10 requires a bounded timeout. Neither specifies descendant cleanup: timing out the sudo process alone need not stop apt-get or package scripts, leaving privileged mutations concurrent with verification.
- Failure: The timeout does not define what happens to privileged installer descendants, allowing package changes to continue after preflight resumes. Add: "On timeout, terminate and reap the entire installer process tree, including privileged descendants, before resuming preflight; test this with a persistent child process."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The package map lacks a single expected argv for installer tests.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 gives ocaml-family tools an ambiguous `ocaml`/`ocaml-findlib` mapping and names both `ocaml-dune` and `dune`. AC-4 checks recorded argv, so implementations and tests can choose different packages while each claims compliance; resolve the map before coding.
- Failure: The package map lacks a single expected argv for installer tests. Add: “Map ocaml, ocamlc and ocamlopt to ocaml, ocamlfind to ocaml-findlib, and dune to ocaml-dune; deduplicate packages before installation.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Multiple missing packages have no defined install grouping or total timeout, leaving failure and timing assertions ambig

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-3 specifies “300s per install,” while section 22 promises a “300s cap.” With multiple packages, separate calls can exceed that cap and produce different failure outcomes; define invocation grouping and timeout scope so installer tests have one oracle.
- Failure: Multiple missing packages have no defined install grouping or total timeout, leaving failure and timing assertions ambiguous. Add: “Install all deduplicated mapped packages in one apt-get invocation with a single 300-second timeout; do not retry.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: A malformed line alongside valid commands has no defined recovery scope, so tests could accept either aborting discovery

- Severity: MEDIUM
- References: CHANGE_SPEC.json section 8 says “Unparseable or unmapped tool: skipped with recorded reason,” while CHANGE_PLAN.json section 1 reuses the preflight tokenizer without defining mixed-file recovery. Specify line-level recovery and add a mixed valid/malformed input case to toolchain-install-test.py.
- Failure: A malformed line alongside valid commands has no defined recovery scope, so tests could accept either aborting discovery or installing the remaining tools. Add: “Parse each command line independently; record and skip malformed lines, then continue discovering missing tools from valid lines.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
