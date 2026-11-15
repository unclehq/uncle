## AR-001: The scope-cut permission contradicts mandatory acceptance criteria.

- Severity: HIGH
- References: CHANGE_PLAN.json §21 permits cutting template rendering, DCO sign-off and claimability; CHANGE_SPEC.json AC-6 and AC-7 require these behaviors. Merely documenting their absence in README would let implementation claim completion while failing the approved requirements.
- Failure: The scope-cut permission contradicts mandatory acceptance criteria. Replace it with: "PR template rendering, required DCO sign-off, and claimability checks remain required for completion; deferral requires an explicitly approved specification change."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Resume behavior leaves environment and persisted mode competing.

- Severity: HIGH
- References: CHANGE_SPEC.json INV-1 fixes OSS mode at start and forbids changing it on resume. CHANGE_PLAN.json §1 binds prompts only when UNCLE_OSS=1, while §10 gates behavior on 'env/journal key' without precedence or restoration rules; resuming without the original environment could omit required guidance.
- Failure: Resume behavior leaves environment and persisted mode competing. Add: "On resume, the journal's OSS value is authoritative, with a missing value treated as false; restore both OSS and implied no-footprint behavior before prompt binding or publication, and reject a conflicting --oss flag."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Commit and PR title formatting has no implementation contract despite being required.

- Severity: MEDIUM
- References: CHANGE_SPEC.json OB-6 requires commit and PR titles to follow stated formats. CHANGE_PLAN.json §1 and implementation step 5 cover DCO sign-off and PR body templates only; its AC-6 tests likewise cover rendering and sign-off, allowing title and commit formatting to be omitted.
- Failure: Commit and PR title formatting has no implementation contract despite being required. Add: "Discover explicit commit-message and PR-title formats, apply them to publication output, preserve required DCO trailers, and send incompatible formatting requirements to the existing human gate."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Template rendering lacks a rule for templates that omit required disclosure or contain forbidden vocabulary.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 requires the project's PR template, while §12 says disclosure is already mandatory under no-footprint. CHANGE_SPEC.json AC-8 forbids Uncle vocabulary and OB-7 requires a gate for conflicting guidance; the rendering contract does not specify how these requirements interact, permitting silent omission or template alteration.
- Failure: Template rendering lacks a rule for templates that omit required disclosure or contain forbidden vocabulary. Add: "Preserve required AI disclosure when filling a PR template; if template requirements conflict with disclosure or no-footprint rules, stop at the existing human gate with the conflict listed."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Resume behavior can change an existing run's mode because prompts use the environment while publication may use the jour

- Severity: HIGH
- References: CHANGE_PLAN.json §1 gates the appendix on UNCLE_OSS=1, while §10 gates behavior on env/journal without precedence; CHANGE_SPEC.json INV-1 fixes mode at start and AC-9 preserves non-OSS behavior. Resolve precedence explicitly so resumed OSS runs retain guidance and resumed non-OSS runs cannot acquire OSS behavior.
- Failure: Resume behavior can change an existing run's mode because prompts use the environment while publication may use the journal. Add: “On resume, the recorded OSS mode governs prompts and publication, absent oss means false, and a conflicting --oss flag is rejected before stage execution.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Template rendering leaves preservation of mandatory no-footprint disclosure unspecified.

- Severity: HIGH
- References: CHANGE_PLAN.json §1 introduces render_pr_body(template, summary, testing) and replaces the body with the project's template; §12 assumes disclosure is already mandatory under no-footprint. CHANGE_SPEC.json INV-4 and AC-8 require existing no-footprint protections to survive; define composition and validation order to prevent the replacement body from bypassing them.
- Failure: Template rendering leaves preservation of mandatory no-footprint disclosure unspecified. Add: “Template rendering must retain mandatory AI disclosure, append it when the template has no disclosure field, and pass the complete rendered body through existing no-footprint validation before publication.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan lets the approval gate decide conflicting guidance without excluding AI prohibitions, leaving a path to overrid

- Severity: HIGH
- References: CHANGE_PLAN.json §12 says both "Conflicting guidance ... approval gate decides" and "Policy prohibits AI ... rerun after the human decision"; CHANGE_SPEC.json INV-2 requires a detected prohibition to block PR creation. Specify precedence so conflicting policies cannot turn mandatory refusal into an approval-dependent choice.
- Failure: The plan lets the approval gate decide conflicting guidance without excluding AI prohibitions, leaving a path to override the mandatory publication block. Add: "Any detected AI prohibition takes precedence over permissive guidance and cannot be waived by plan approval."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Resume behavior does not specify which mode wins when the environment disagrees with the journal, allowing an OSS run to

- Severity: HIGH
- References: CHANGE_PLAN.json §10 says "Gated on env/journal key" and §1 enables no-footprint through launcher exports; CHANGE_SPEC.json INV-1 fixes OSS mode in the journal across resumes. Define the precedence and restoration behavior so resuming without --oss cannot bypass either safeguard.
- Failure: Resume behavior does not specify which mode wins when the environment disagrees with the journal, allowing an OSS run to lose its publication safeguards. Add: "On resume, the stored OSS mode overrides the environment and enables both the policy check and no-footprint enforcement before any publication write."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Repository-only discovery lacks a rule for guidance symlinks that resolve outside the repository, potentially exposing l

- Severity: MEDIUM
- References: CHANGE_SPEC.json §10 requires discovery to read only repository files; CHANGE_PLAN.json §1 defines discover(root) as returning text and source locations but provides no symlink boundary rule. Specify resolved-path containment so an untrusted checkout cannot make discovery read and reproduce external files.
- Failure: Repository-only discovery lacks a rule for guidance symlinks that resolve outside the repository, potentially exposing local files through guideline text. Add: "Discovery must reject guidance paths whose resolved targets lie outside the repository root and report them as unknown without reading their contents."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Policy unit tests cannot establish that publication refuses before side effects.

- Severity: HIGH
- References: CHANGE_PLAN.json §16 specifies policy cases but no publication-entry-point assertion; CHANGE_SPEC.json AC-4 requires refusal before any branch, commit, push or gh call. A correctly failing helper can coexist with a publish caller that checks too late or ignores failure.
- Failure: Policy unit tests cannot establish that publication refuses before side effects. Add: "Run the publication entry point against a prohibiting fixture with recording git/gh shims; assert failure, the policy source, and zero branch, commit, push or gh invocations."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Claimability and prompt assertions cannot verify the required gate-stop.

- Severity: HIGH
- References: CHANGE_SPEC.json AC-7 requires a gate-stop and makes silent default selection impossible; CHANGE_PLAN.json §12 describes warnings and §16 lists claimability tests. Neither specifies a behavioral test of the gate, so advisory output could satisfy the planned checks without stopping execution.
- Failure: Claimability and prompt assertions cannot verify the required gate-stop. Add: "Exercise conflicting guidance and unclaimable issues through the workflow with approval withheld; assert listed reasons and no stage advancement, including when a default choice is available."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Resume behavior lacks a testable precedence rule for conflicting environment and journal values.

- Severity: MEDIUM
- References: CHANGE_SPEC.json INV-1 fixes OSS mode at start; CHANGE_PLAN.json §10 says only 'Gated on env/journal key,' while §1 gates the appendix on UNCLE_OSS=1. AC-1 verification covers wiring and journal creation without specifying resume cases, allowing tests and implementation to choose different precedence.
- Failure: Resume behavior lacks a testable precedence rule for conflicting environment and journal values. Add: "On resume, journal OSS mode governs prompts and publication regardless of the current flag or environment; a missing key means false, and tests cover both mismatch directions and legacy journals."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Rendering helpers can pass while publication drops DCO trailers or template content.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-6 verifies publication-facing behavior using only unit tests of render functions; CHANGE_PLAN.json §16 likewise lists sign-off and rendering cases without asserting their integration. The planned tests would not detect a caller that continues using the existing message or body.
- Failure: Rendering helpers can pass while publication drops DCO trailers or template content. Add: "For a DCO-required fixture with a PR template, exercise publication using recording shims and assert that the actual commit message and submitted PR body contain the required trailer and populated template."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
