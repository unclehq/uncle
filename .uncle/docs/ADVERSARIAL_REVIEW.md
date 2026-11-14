## AR-001: D-1 requires an automated project commit before building, contradicting the binding requirement for commit-free completi

- Severity: HIGH
- References: CHANGE_PLAN.json D-1 and section 6 require a seed commit and its SHA as the hand-off base; CHANGE_SPEC.json AC-1 mandates that commit. The user's Git signing instructions explicitly prohibit baseline commits as build prerequisites; amend AC-1 and the component exclusions to permit a commit-free hand-off design.
- Failure: D-1 requires an automated project commit before building, contradicting the binding requirement for commit-free completion. Replace D-1 with: "Capture the starting tree using file hashes and a path inventory including untracked files; build, verification, and completion must not create or require a project commit."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: HEAD existence does not establish that a PR or attestation was written, so D-2 can retain the misleading success claim i

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-2 and CHANGE_SPEC.json AC-4 select PR/attestation wording solely by whether HEAD resolves. Neither requires successful artifact creation, and the specified hand-off path produces handoff.json rather than a PR; replace the HEAD-only condition with actual artifact outcomes.
- Failure: HEAD existence does not establish that a PR or attestation was written, so D-2 can retain the misleading success claim in hand-off mode or after export failure. The plan should say: "Completion text names only artifacts confirmed written for this run; otherwise it points to FINAL_AUDIT.md."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: AC-3 requires NOT_READY and draft true for every initially commit-less unattended build, while BH-2 limits that outcome

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-3 has no audit-result precondition, whereas BH-2 explicitly specifies a NOT_READY audit and section 4 says draft:true when not READY. CHANGE_PLAN.json T-2 must explicitly arrange a NOT_READY audit so implementation and tests do not force that result for successful audits.
- Failure: AC-3 requires NOT_READY and draft true for every initially commit-less unattended build, while BH-2 limits that outcome to a NOT_READY audit. The plan should say: "AC-3 applies to a NOT_READY audit; other audit outcomes retain their existing verdict and draft mapping."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The scope-cut instruction permits dropping mandatory AC-5 behavior and its test without changing acceptance requirements

- Severity: MEDIUM
- References: CHANGE_PLAN.json section 21 says to cut D-3 wording and the AC-5 test first under time pressure, but CHANGE_SPEC.json AC-5 requires truthful hand-off failure output and unchanged exit status. Remove this unilateral scope cut so the implementation checklist and acceptance contract agree.
- Failure: The scope-cut instruction permits dropping mandatory AC-5 behavior and its test without changing acceptance requirements. The plan should say: "D-3 and AC-5 verification remain required unless the user explicitly approves a revised scope."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: D-1 introduces an automatic real-project commit during ordinary build startup, contradicting the commit-free workflow re

- Severity: HIGH
- References: CHANGE_PLAN.json D-1 and section 6 require a synthetic commit as the hand-off base; CHANGE_SPEC.json AC-1 mandates its creation. The binding user instructions prohibit baseline commits as build/completion prerequisites and say a generated plan does not authorize committing; amend AC-1 and the scope restrictions to permit a commit-free implementation.
- Failure: D-1 introduces an automatic real-project commit during ordinary build startup, contradicting the commit-free workflow requirement. Replace it with: "Unborn-HEAD builds use a file inventory and hashes including untracked files; completion and hand-off require no project commit."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The exclusion pathspec does not remove already staged `.uncle/` files, so the proposed commit can expose workflow state

- Severity: HIGH
- References: CHANGE_PLAN.json D-1 stages with `git add -A -- . ':(exclude).uncle'` and then commits the entire index; CHANGE_SPEC.json INV-3 says the seed never contains `.uncle/` state. T-1 mentions exclusion but does not specify the already-staged case, allowing a test that passes while this regression remains.
- Failure: The exclusion pathspec does not remove already staged `.uncle/` files, so the proposed commit can expose workflow state despite INV-3. Add: "Snapshot construction excludes all `.uncle/` paths even when already staged, preserves the user's index, and has a regression test for pre-staged workflow state."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: A failed seed can leave all project files staged while the workflow reports a warning and continues, changing the user's

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 performs `git add -A` before committing, while section 12 specifies only warning and continuation on failure. CHANGE_SPEC.json section 8 and T-1/T-2 provide no index-preservation contract or failure-after-staging assertion; define recovery so a failed startup does not silently change staged selections.
- Failure: A failed seed can leave all project files staged while the workflow reports a warning and continues, changing the user's subsequent Git operations. Add: "If snapshot creation fails, preserve the exact pre-run index and working-tree contents, continue with the warning, and test failure after staging succeeds."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: D-1 authorizes an unsigned project commit during ordinary build startup, contradicting the user's commit and signing bou

- Severity: HIGH
- References: CHANGE_PLAN.json §1 D-1 invokes git commit --no-gpg-sign in the actual checkout; §15 R-2 applies fixture signing safeguards to that operation. The binding user instructions prohibit automated project commits as build prerequisites and distinguish them from disposable fixture commits; amend D-1 and the dependent seed requirements.
- Failure: D-1 authorizes an unsigned project commit during ordinary build startup, contradicting the user's commit and signing boundaries. Replace it with: “Build completion and hand-off evidence use file snapshots including untracked files; project commits remain an explicitly approved publishing action.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The exclusion pathspec leaves previously staged .uncle files in the index, so the proposed commit can persist private wo

- Severity: HIGH
- References: CHANGE_PLAN.json §1 D-1 runs git add -A -- . ':(exclude).uncle' followed by an unrestricted git commit; CHANGE_SPEC.json INV-3 says the seed never contains .uncle state. Excluding paths from git add does not remove existing index entries; amend the mechanism and T-1 to cover pre-staged .uncle files.
- Failure: The exclusion pathspec leaves previously staged .uncle files in the index, so the proposed commit can persist private workflow state despite INV-3. Add: “Any separately authorized base commit uses an isolated index that excludes all .uncle paths regardless of prior staging and leaves the user's index unchanged.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: T-1 does not define whether `.uncle/` is already staged, so it can pass while missing a violation of INV-3.

- Severity: HIGH
- References: CHANGE_PLAN.json D-1 excludes `.uncle` from git add but commits the existing index; T-1 merely says “excludes `.uncle/`.” CHANGE_SPEC.json INV-3 requires exclusion unconditionally, so the test must cover previously staged state.
- Failure: T-1 does not define whether `.uncle/` is already staged, so it can pass while missing a violation of INV-3. Add: “Test an unborn repository with staged `.uncle/` files and assert that the resulting seed tree contains no `.uncle/` paths.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: T-2 combines successful seeding with messages that require absent HEAD, leaving its setup and assertions ambiguous.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §16-17 assigns handoff.json, D-2 and D-3 assertions to T-2 without defining separate scenarios; D-3 and CHANGE_SPEC.json BH-4 require HEAD to remain absent. A successful seed cannot exercise that branch.
- Failure: T-2 combines successful seeding with messages that require absent HEAD, leaving its setup and assertions ambiguous. Add: “Use separate successful-seed and injected-seed-failure cases; assert handoff artifacts in the former and both no-HEAD messages plus unchanged exit status in the latter.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Disabling signing in fixtures does not demonstrate that inherited signing settings cannot invoke a signer.

- Severity: HIGH
- References: CHANGE_PLAN.json R-2 and T-2 specify disabled signing but omit the inherited-configuration negative test required by AGENTS.md. Without it, fixture tests can pass under benign configuration while accessing a user's signer in another environment.
- Failure: Disabling signing in fixtures does not demonstrate that inherited signing settings cannot invoke a signer. Add: “Verify fixture creation under inherited signing=true with a failing recording fake signer, assert zero invocations, and apply both local signing settings and explicit disabling flags to every fixture Git subprocess.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
