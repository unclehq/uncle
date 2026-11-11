## AR-001: The replay source is ambiguous when executed files include untracked changes or copy rewrites, so replay can test differ

- Severity: HIGH
- References: CHANGE_PLAN.json §2-3 D-4 selects git archive; CHANGE_SPEC.json AC-7 selects the attested tree, while AC-3 permits the executed copy's hash to differ from inputs.artifact. These do not define reproduction of the actual checked files; adopt the snapshot rule and bind its digest to the record.
- Failure: The replay source is ambiguous when executed files include untracked changes or copy rewrites, so replay can test different inputs. Add: “Rerun restores the immutable executed-file snapshot, including untracked files and recorded rewrites, without requiring a project commit or clean working tree.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The environment allow-list is not finite: “Uncle-set variables” could include credentials, contradicting the no-credenti

- Severity: HIGH
- References: CHANGE_SPEC.json §15 A1 includes all Uncle-set variables, while §10 leaves PATH handling unresolved; CHANGE_PLAN.json R-1 promises no credential recorded. Specify the complete list and whether PATH is omitted so implementation and absence tests enforce the same boundary.
- Failure: The environment allow-list is not finite: “Uncle-set variables” could include credentials, contradicting the no-credential restriction. Add: “Capture values only for explicitly enumerated variable names; prefixes and setter provenance never grant inclusion, and credential-bearing variables are excluded.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Final audit requires a rerun result although rerun is optional, leaving ordinary completion undefined.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-8 and SB-8 require the rerun result as audit input, but §14 and CHANGE_PLAN.json D-2 make rerun opt-in. Define the absent-result state and its audit treatment rather than letting audit wiring silently make rerun mandatory.
- Failure: Final audit requires a rerun result although rerun is optional, leaving ordinary completion undefined. Add: “When rerun was not requested, final audit receives a structured not-requested result and may complete without executing rerun; requested reruns supply their actual outcome.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Replaying every recorded command conflicts with excluding browsers when a recorded check launches one.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-7 requires rerunning recorded commands and passing only on full match, while §14 excludes running browsers in rerun. Define how browser-dependent commands are identified and handled so implementations cannot silently skip them and report success.
- Failure: Replaying every recorded command conflicts with excluding browsers when a recorded check launches one. Add: “If any recorded command requires browser execution, rerun reports unavailable with a nonzero exit and does not claim a full match.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The archive-based rerun does not specify how modified and untracked verified files enter the replay tree, risking stale

- Severity: HIGH
- References: CHANGE_PLAN.json §2-3, D-4 selects `git archive` of the tree; CHANGE_SPEC.json AC-7 requires replaying the attested tree. The user's binding instructions require file hashes and inventories including untracked files, but the plan supplies no mapping from that snapshot to the archived tree.
- Failure: The archive-based rerun does not specify how modified and untracked verified files enter the replay tree, risking stale inputs or a new commit prerequisite. Add: “Capture and replay a file snapshot including modified and untracked inputs; verification never requires a project commit or clean working tree.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Mandatory final-audit rerun input conflicts with opt-in reruns unless the absent-result case is defined, potentially blo

- Severity: HIGH
- References: CHANGE_PLAN.json D-2 makes rerun opt-in, while CHANGE_SPEC.json AC-8 and SB-8 require its result as final-audit input. Neither defines audit behavior when no rerun exists; this leaves implementations free to require reruns or treat their absence as failure.
- Failure: Mandatory final-audit rerun input conflicts with opt-in reruns unless the absent-result case is defined, potentially blocking existing workflows. Add: “When rerun was not requested, final audit receives an explicit not-requested result and retains its existing completion behavior without executing a rerun.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Browser checks have no defined rerun behavior: replaying every command can launch browsers, while skipping them cannot e

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-7 requires rerunning recorded commands and passing only on full match, but §14 excludes running browsers in rerun. The plan defines neither browser-check handling nor an unavailable outcome for this combination, risking unexpected browser launches or false successful replay.
- Failure: Browser checks have no defined rerun behavior: replaying every command can launch browsers, while skipping them cannot establish a full match. Add: “If a recorded check requires a browser, rerun reports unavailable with a nonzero exit before executing commands; ordinary verification remains unchanged.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Rerun environment inheritance is unspecified, so recorded commands could receive the reviewer's credentials despite the

- Severity: HIGH
- References: CHANGE_PLAN.json §4 says rerun needs “no live credentials”; CHANGE_SPEC.json SI-2 limits environment capture, while §10 specifies only a temporary checkout and timeout for execution. Capture filtering does not prevent subprocesses from inheriting secrets; adopt a separate execution-environment policy.
- Failure: Rerun environment inheritance is unspecified, so recorded commands could receive the reviewer's credentials despite the capture allow-list. Add: “Launch reruns with a fresh environment containing only explicitly permitted execution variables; never inherit credential variables.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Recorded cwd has no relocation or containment rule, allowing replay to run outside its temporary checkout.

- Severity: HIGH
- References: CHANGE_SPEC.json AC-1 requires recording cwd, and AC-7 requires rerunning commands in the attested tree; CHANGE_PLAN.json D-4 selects a temporary directory. Neither defines how an original absolute cwd or an escaping path is handled, risking execution against the reviewer's real checkout or other directories; specify containment.
- Failure: Recorded cwd has no relocation or containment rule, allowing replay to run outside its temporary checkout. Add: “Store cwd relative to the executed root, resolve it inside the rerun root, and reject absolute paths, traversal, or symlink resolution outside that root before executing any command.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: “Uncle-set variables” leaves credential capture open to incompatible interpretations.

- Severity: HIGH
- References: CHANGE_SPEC.json §15 A1 defines the allow-list as “Uncle-set variables plus” named variables, whereas CHANGE_PLAN.json R-1 promises “no credential recorded” and D-3 specifies a constant. A prefix or provenance interpretation could admit future Uncle credentials; replace the open-ended category with an explicit list.
- Failure: “Uncle-set variables” leaves credential capture open to incompatible interpretations. Add: “Enumerate every permitted environment-variable name in the constant; do not select variables by prefix or provenance, and exclude credential-bearing variables even when Uncle sets them.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Environment comparison lacks a defined oracle, so match and env-diff tests can enforce incompatible behavior.

- Severity: HIGH
- References: CHANGE_SPEC.json AC-2, AC-7 and assumptions A1–A2 require environment capture and mismatch reporting, but do not define comparison fields, normalization, or whether execution proceeds after a difference. CHANGE_PLAN.json §16–17 promises match/mismatch/env-diff tests; specify this decision before implementing those assertions.
- Failure: Environment comparison lacks a defined oracle, so match and env-diff tests can enforce incompatible behavior. Add: "Compare every recorded environment field exactly before execution; missing tools or differing values produce a nonzero environment-mismatch result without running commands."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The rerun timeout option has no precedence rule against recorded timeouts, leaving timeout tests without a single expect

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 introduces --rerun-timeout S, while CHANGE_SPEC.json AC-7 requires recorded constraints and AC-1 records each command's timeout. Neither document defines overrides or invalid values; adopt an explicit rule and test omitted, shorter, longer, zero, negative, and malformed values.
- Failure: The rerun timeout option has no precedence rule against recorded timeouts, leaving timeout tests without a single expected result. Add: "The effective timeout is the lesser of the recorded timeout and a positive --rerun-timeout value; omission preserves the recorded timeout, and invalid values fail before execution."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Legacy attestations have no specified rerun exit code, so compatibility tests can accept contradictory CLI behavior.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §7 says legacy --rerun reports unavailable, not failure of base verification; AC-7 says rerun passes only on full match, and §8 specifies nonzero only for mismatches. Define the process exit separately from base-verification status and assert both in the legacy fixture.
- Failure: Legacy attestations have no specified rerun exit code, so compatibility tests can accept contradictory CLI behavior. Add: "For a valid legacy attestation without a command record, --rerun reports unavailable and exits nonzero while preserving the successful base-verification result."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Final-audit tests lack an expected input when rerun was not requested.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-8/SB-8 require the rerun result as audit input, but §14 and CHANGE_PLAN.json D-2 make rerun opt-in. Neither specifies the ordinary no-rerun case; settle that state and cover it in tree-attested-final-audit-test.sh.
- Failure: Final-audit tests lack an expected input when rerun was not requested. Add: "When rerun is not requested, final audit receives a structured unavailable result with reason 'not requested'; it must not infer a rerun pass from the transcript or launch rerun implicitly."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
