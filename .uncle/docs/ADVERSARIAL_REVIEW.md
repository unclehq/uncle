## AR-001: Optional recording hooks conflict with the requirement to fingerprint every passing stage, leaving stages outside select

- Severity: HIGH
- References: CHANGE_PLAN.json §21 permits cutting record hooks beyond PLAN/ADVERSARIAL_REVIEW/IMPLEMENT, while CHANGE_SPEC.json AC-1 and RB-1 require records for each passing stage. With D-2 skipping unrecorded stages, cutting these hooks silently omits completed stages from revalidation.
- Failure: Optional recording hooks conflict with the requirement to fingerprint every passing stage, leaving stages outside selective verification. Add: "Record input fingerprints on every stage's successful completion; hooks beyond PLAN, ADVERSARIAL_REVIEW, and IMPLEMENT are required scope."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: D-2 does not distinguish never-run stages from legacy stages that ran without fingerprint records.

- Severity: HIGH
- References: CHANGE_PLAN.json §9 D-2 says an unrecorded stage is skipped and only a previously recorded stage without inputs is changed. CHANGE_SPEC.json RB-9 requires stages that previously ran without a recorded hash/pass to count as changed; AC-7 separately prohibits execution when no recorded passes exist.
- Failure: D-2 does not distinguish never-run stages from legacy stages that ran without fingerprint records. Add: "Skip only stages with no execution history; stages with prior execution but missing fingerprints are changed and must rerun when at least one recorded pass exists."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Excluding all Markdown from app/test inputs can reuse stages after actual application or test inputs change.

- Severity: HIGH
- References: CHANGE_PLAN.json §9 D-1 says Markdown files are never app/test inputs. CHANGE_SPEC.json AC-3 exempts README-only changes, while AC-1, AC-4, and RI-1 require fingerprinting actual inputs and rerunning their consumers; Markdown fixtures and application content expose the conflict.
- Failure: Excluding all Markdown from app/test inputs can reuse stages after actual application or test inputs change. Add: "Exclude the root README.md from stage inputs, but fingerprint other Markdown files whenever they are application, test, protected, or approved-document inputs."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Resuming the driver at the first invalidated stage does not specify how later reusable stages avoid execution.

- Severity: HIGH
- References: CHANGE_PLAN.json §1-3 specifies resuming at the first invalidated stage via UNCLE_REVALIDATE_RESUME, but gives no execution contract for subsequent reusable stages. CHANGE_SPEC.json AC-4 requires exactly the changed stages and their dependents to rerun, with all others reused.
- Failure: Resuming the driver at the first invalidated stage does not specify how later reusable stages avoid execution. Add: "Pass the complete per-stage action plan to the resumed driver; execute only stages marked run, skip reused and unrecorded stages, and stop before any needs-review stage or reopened gate."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Flag exclusivity can be read as rejecting explicitly supported modifiers.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §2-4 explicitly supports --revalidate [--noui] [--attended] [--dry-run], while RB-12 says --revalidate is exclusive with other startup options. CHANGE_PLAN.json step 2 calls for flag exclusivity without resolving which modifiers remain legal, allowing incompatible CLI implementations and tests.
- Failure: Flag exclusivity can be read as rejecting explicitly supported modifiers. Add: "Allow --revalidate with --noui, --attended, and --dry-run; reject other startup modes, and reject --dry-run without --revalidate."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: D-1 excludes all Markdown from app/test inputs, allowing changes to Markdown application content or test fixtures to reu

- Severity: HIGH
- References: CHANGE_PLAN.json §9 D-1 excludes Markdown categorically, while CHANGE_SPEC.json AC-1, AC-4 and RI-1 require fingerprints for consumed inputs and reruns when those inputs change. AC-3 grants the README-only exception, not an exception for all Markdown.
- Failure: D-1 excludes all Markdown from app/test inputs, allowing changes to Markdown application content or test fixtures to reuse stale results. Replace it with: "Exclude only the project-root README.md from app/test inputs; hash other Markdown files whenever a stage consumes them, including protected verification files."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Resuming the existing driver at the first invalidated stage does not specify how later reusable stages remain skipped, r

- Severity: HIGH
- References: CHANGE_PLAN.json §1–3 specifies first-invalidated-stage resume via UNCLE_REVALIDATE_RESUME, but provides no per-stage execution filter; §4 also limits change-workflow.sh edits to record hooks while the impact table requires resume and gate changes. CHANGE_SPEC.json AC-4 requires exactly the affected stages and dependents to rerun, and AC-9 prohibits approval/attestation writes.
- Failure: Resuming the existing driver at the first invalidated stage does not specify how later reusable stages remain skipped, risking unnecessary model calls, tests and reopened gates. Add: "During revalidation, the driver executes only stages marked run in the computed plan, skips reusable and unrecorded stages, and stops before any approval or attestation write."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Optional record hooks combined with skipping unrecorded stages can leave completed workflow stages permanently outside r

- Severity: MEDIUM
- References: CHANGE_PLAN.json §21 allows cutting hooks beyond PLAN/ADVERSARIAL_REVIEW/IMPLEMENT, and §9 D-2 says an unrecorded stage is skipped without distinguishing missing fingerprints from stages never run. CHANGE_SPEC.json AC-1 requires each passing stage to record inputs, and RB-9 requires previously run stages lacking hashes to count as changed.
- Failure: Optional record hooks combined with skipping unrecorded stages can leave completed workflow stages permanently outside revalidation. Add: "Record every passing stage in scope; when a stage previously ran but lacks a fingerprint, classify it as changed using existing workflow history, and reserve skip for stages that never ran."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Snapshot comparison detects approval or attestation writes only after they occur, leaving RI-5 unenforced if a resumed s

- Severity: HIGH
- References: CHANGE_PLAN.json §Restrictions R-5 specifies “snapshot compare + gate stop exit 75”; §4 excludes approval/attestation writers from modification. CHANGE_SPEC.json AC-9 and RI-5 prohibit all such writes, so the plan must identify a pre-write enforcement point that also covers resumed stages which write without reopening a gate.
- Failure: Snapshot comparison detects approval or attestation writes only after they occur, leaving RI-5 unenforced if a resumed stage invokes a writer before reaching a gate. Add: “Revalidation must prevent approval and attestation writes before invoking any resumed stage; snapshot comparison is only a secondary check.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The Markdown exclusion makes the required input-change tests contradictory for Markdown documents and protected tests.

- Severity: HIGH
- References: CHANGE_PLAN.json §9 D-1 excludes all Markdown from app/test inputs, while CHANGE_SPEC.json AC-1 requires hashing docs and protected paths and RI-1 requires every input to remain byte-identical. Specify this boundary so tests cannot pass by excluding a Markdown input that a stage actually reads.
- Failure: The Markdown exclusion makes the required input-change tests contradictory for Markdown documents and protected tests. Add: “Exclude only the root README.md from app/test inputs; hash all declared document and protected inputs regardless of extension.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Missing-record tests lack a defined way to distinguish never-run stages from legacy stages whose fingerprints are absent

- Severity: MEDIUM
- References: CHANGE_PLAN.json §9 D-2 says an unrecorded stage is skipped but a previously recorded stage without inputs is changed; CHANGE_SPEC.json RB-9 instead covers previously run stages without a hash/pass. Define the evidence for this distinction and test both cases alongside AC-7, or legacy-stage fixtures can support incompatible expected results.
- Failure: Missing-record tests lack a defined way to distinguish never-run stages from legacy stages whose fingerprints are absent. Add: “Skip a stage with no fingerprint only when workflow history proves it never ran; otherwise treat it as changed, subject to the no-recorded-passes exit rule.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Stub call counts cannot settle whether resuming the driver executes unchanged downstream stages.

- Severity: HIGH
- References: CHANGE_PLAN.json §§1–3 resumes the driver at the first invalidated stage, while §16–17 specifies stub-runner counts and a two-pass resume test without defining whether the driver runs. CHANGE_SPEC.json AC-4 requires exactly the changed stage and its dependents; require this integration boundary so helper-only tests cannot conceal execution beyond the printed plan.
- Failure: Stub call counts cannot settle whether resuming the driver executes unchanged downstream stages. Add: “An integration test must resume the real driver with model and test commands stubbed and assert that only stages marked run execute, while stages marked reused or skip execute no commands.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
