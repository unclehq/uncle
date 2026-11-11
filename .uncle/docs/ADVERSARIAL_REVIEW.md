## AR-001: Ignored marker failures contradict the unconditional post-commit protection.

- Severity: HIGH
- References: CHANGE_SPEC.json §4 forbids writes after finalize/publish, but §8 and CHANGE_PLAN.json §12 explicitly restore today's behavior on marker-write failure. This permits the original defect after a successful commit or push; resolve the guarantee versus best-effort conflict in both artifacts.
- Failure: Ignored marker failures contradict the unconditional post-commit protection. Add: "If recording the freeze fails, subsequent and resumed workflow operations must suppress .gitignore writes rather than resume normalization."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The tracked-file guarantee exceeds the planned .gitignore guard.

- Severity: HIGH
- References: CHANGE_SPEC.json §4 says no uncle code path writes '.gitignore or any tracked file'; CHANGE_PLAN.json R-1 repeats this scope, while D-1 only guards uncle_gitignore.ensure(). Without additional coverage, implementation and verification can satisfy the mechanism while violating the stated requirement.
- Failure: The tracked-file guarantee exceeds the planned .gitignore guard. Add: "Inventory every uncle writer of tracked files reachable after finalize or publish, and prevent those writes after that boundary."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Permitted scope cuts remove mandatory acceptance behavior.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §18 permits cutting documentation and the stagegate.sh/from-issue.sh freeze calls. CHANGE_SPEC.json AC-3 requires both call sites and AC-5 requires the documentation; the scope-cut instructions and acceptance checklist cannot both govern completion.
- Failure: Permitted scope cuts remove mandatory acceptance behavior. Add: "The finalize and merge freeze calls and the documentation update are required deliverables and cannot be cut without revising the approved acceptance criteria."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The reset boundary is undefined for a reused root, making preservation and renewed normalization ambiguous.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §6-7 says the marker is 'never cleared by uncle' but also that fresh run state resets it; U-3 relies on that reset. CHANGE_SPEC.json S-6 requires reused worktrees after push to remain frozen, so starting a fresh run could either preserve protection or re-enable the prohibited write.
- Failure: The reset boundary is undefined for a reused root, making preservation and renewed normalization ambiguous. Add: "A new run on the same project root preserves the freeze marker; creating fresh run state must not remove it."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: A failed finalize or merge commit leaves normalization permanently disabled, changing retry behavior before any commit s

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 freezes before finalize/merge commits, while §6–7 says the marker is never cleared; CHANGE_SPEC.json S-4 preserves pre-freeze normalization. Neither defines commit failure or cancellation, so a rejected commit can suppress normalization on subsequent retries. Specify recovery and add a failed-commit retry regression test.
- Failure: A failed finalize or merge commit leaves normalization permanently disabled, changing retry behavior before any commit succeeds. Add: "If a commit attempt fails, remove the freeze marker created by that attempt; preserve any marker that existed beforehand."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Symlink refusal does not specify ancestor directories or the marker itself, allowing implementations that write outside

- Severity: HIGH
- References: CHANGE_SPEC.json §10 explicitly refuses only symlinked `.uncle/workflow`, whereas AC-4 requires writes only inside that directory; CHANGE_PLAN.json D-1 merely says "refuses symlinks." A symlinked `.uncle` ancestor or marker leaf can redirect the write, so the plan must define refusal for the entire marker path.
- Failure: Symlink refusal does not specify ancestor directories or the marker itself, allowing implementations that write outside the project. Add: "freeze() refuses symlinks at .uncle, workflow, and gitignore-frozen, and creates the marker without following links or truncating an existing target."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: An unwritable marker leaves post-publish tracked-file writes enabled despite the stated security guarantee.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §4 promises no uncle tracked-file writes after finalize/publish, but §8 and CHANGE_PLAN.json §12 explicitly restore today's behavior on marker-write failure. Permission errors or a refused symlink therefore bypass the protection; revise the failure policy and specify how subsequent processes preserve it.
- Failure: An unwritable marker leaves post-publish tracked-file writes enabled despite the stated security guarantee. Add: "If freeze persistence fails, later ensure calls must remain read-only; inability to persist the marker must not restore tracked-file writes."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Source-order checks cannot establish that publishing or finalizing actually freezes the correct root.

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json §16 and CHANGE_SPEC.json AC-3 prescribe source-order checks plus a separate freeze()/ensure() fixture. Those checks can pass for unreachable calls, incorrect roots, or calls executed after failed pushes; replace source ordering as the primary AC-3 oracle with execution tests.
- Failure: Source-order checks cannot establish that publishing or finalizing actually freezes the correct root. Add: "Disposable-fixture integration tests execute each freeze call site with mocked publishing and signing, verify the target root is frozen, and verify a failed push creates no marker."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The missing-file case has no valid SHA-256 oracle, and the plan leaves its assertion ambiguous.

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_SPEC.json AC-1 includes missing-file cases but specifies before/after SHA-256 comparisons; CHANGE_PLAN.json §16 likewise promises SHA-256 equality for missing files. Hashing an absent path fails, while treating absence as empty bytes can miss erroneous creation of an empty file; define separate existence and content assertions.
- Failure: The missing-file case has no valid SHA-256 oracle, and the plan leaves its assertion ambiguous. Add: "For an initially absent .gitignore, assert it remains absent after each frozen API and CLI invocation; for existing files, compare bytes against the unchanged pre-invocation snapshot."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
