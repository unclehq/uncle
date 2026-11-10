## AR-001: The plan does not say how --help/--version combine with other arguments or an invalid argument.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 (D-1) and SB-1/SB-2 only cover the flag in isolation; AC-1 says 'regardless of working-tree state'.
- Failure: The plan does not say how --help/--version combine with other arguments or an invalid argument. Decision: 'The first of --help/-h/--version found in argv wins, is handled before preflight, and later arguments are ignored; an unknown argument alone still goes through preflight.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: AC-7 allows suites to 'fail with a clear prerequisite message', but AC-8 requires run-all-tests.sh to exit 0 with 0 fail

- Severity: HIGH
- References: CHANGE_SPEC AC-7 vs AC-8; CHANGE_PLAN s13 'leave a suite red and list it'.
- Failure: AC-7 allows suites to 'fail with a clear prerequisite message', but AC-8 requires run-all-tests.sh to exit 0 with 0 failed. Decision: 'A prerequisite-failing suite counts as FAILED for AC-8; the change is complete only when all suites pass, otherwise the suite is listed as unresolved.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: SB-5 gives two incompatible expected results: a defined refusal message, or a fixture made a valid repo.

- Severity: MEDIUM
- References: CHANGE_SPEC SB-5 'Defined refusal message per tests (or fixture made a valid repo)'; CHANGE_PLAN s5.1 'root cause decided in step 4'.
- Failure: SB-5 gives two incompatible expected results: a defined refusal message, or a fixture made a valid repo. Decision: 'The TUI shows a refusal message and does not raise when the worktree list is unavailable; the fixture changes only if the test asserts a valid repo.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: AC-5 requires passing 'with a dirty host .gitignore', but D-2 makes fixtures create their own .gitignore, so no test exe

- Severity: MEDIUM
- References: CHANGE_SPEC AC-5 and SB-6 vs CHANGE_PLAN D-2 and change-impact row r3 'masks real ignore bug'.
- Failure: AC-5 requires passing 'with a dirty host .gitignore', but D-2 makes fixtures create their own .gitignore, so no test exercises the dirty-host case. Decision: 'The attestation fixture writes its own .gitignore, with and without .uncle; at least one shard asserts the ignore-containing case.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The step-4 Owns list is closed, but the exit-127 and gates-verification-integrity fixes may touch other files, and 'fixt

- Severity: MEDIUM
- References: CHANGE_PLAN s12 step-4 Owns vs s14.1.i1 and s7.1.
- Failure: The step-4 Owns list is closed, but the exit-127 and gates-verification-integrity fixes may touch other files, and 'fixture setup, never assertions' is not defined. Decision: 'Any file outside the Owns list needs an IMPLEMENTATION_NOTES.md deviation entry before editing; a setup edit changes no assertion, expected value, or skip condition.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: SB-8's 'clear prerequisite message' for a missing command does not say where it appears or what exit code it uses.

- Severity: LOW
- References: CHANGE_SPEC s8 'Missing prerequisites yield a message naming the missing tool, not exit 127'; AC-7.
- Failure: SB-8's 'clear prerequisite message' for a missing command does not say where it appears or what exit code it uses. Decision: 'A missing tool prints `missing prerequisite: <tool>` on stderr and exits with a code other than 127.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Help/version moves before preflight, but mixed args (`--version --unattended`, `--help build`) are unspecified.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 D-1 and R-3 ('only help/version moved earlier'); AC-1/AC-2 say only 'regardless of tree state'.
- Failure: Help/version moves before preflight, but mixed args (`--version --unattended`, `--help build`) are unspecified. Plan should say: help/version are honored only when they are the first recognized flag, never write state, and any real-run args still go through full preflight.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: SB-8/AC-7 allow 'fail with clear prerequisite message', but AC-8 requires exit 0 with 0 failed.

- Severity: HIGH
- References: CHANGE_SPEC AC-7 vs AC-8; CHANGE_PLAN s13 'leave a suite red and list it'.
- Failure: SB-8/AC-7 allow 'fail with clear prerequisite message', but AC-8 requires exit 0 with 0 failed. Plan should say: a prerequisite-failure suite counts as red, AC-8 is unmet until all pass, and any such suite is listed for the PR.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Early-branch fix location (product vs fixture) is open, and step 4 Owns omits the early-branch product files.

- Severity: MEDIUM
- References: CHANGE_PLAN s9.1.r4 'early-branch code' unnamed; step-4 owns omits it.
- Failure: Early-branch fix location (product vs fixture) is open, and step 4 Owns omits the early-branch product files. Plan should say: step 1 triage names the product files and step 4 Owns is amended before any edit.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Isolating fixture .gitignore could mask a real defect when a repo .gitignore contains `.uncle`.

- Severity: MEDIUM
- References: CHANGE_PLAN s9.1.r3 risk 'masks real ignore bug'; CHANGE_SPEC SB-6, AC-5 'including with a dirty host .gitignore'.
- Failure: Isolating fixture .gitignore could mask a real defect when a repo .gitignore contains `.uncle`. Plan should say whether the product must handle that case, and whether a check covers it or triage records it as out of scope.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: SB-5 gives two outcomes when worktree listing fails (refusal message, or repair the fixture) and defers the choice.

- Severity: MEDIUM
- References: CHANGE_SPEC SB-5 'or fixture made a valid repo'; CHANGE_PLAN s5.1 'decided in step 4'.
- Failure: SB-5 gives two outcomes when worktree listing fails (refusal message, or repair the fixture) and defers the choice. Plan should say: WorktreeListError is caught in the resume path, shown as a refusal with no state change, and the fixture is repaired only if non-repo was unintended.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Signing-fix scope is open-ended ('other flagged fixtures') while step 3 Owns lists two files.

- Severity: LOW
- References: CHANGE_PLAN s9.1.r6 'and other flagged fixtures'; step-3 owns lists only two files.
- Failure: Signing-fix scope is open-ended ('other flagged fixtures') while step 3 Owns lists two files. Plan should say: every file the supervisor-test.py audit flags is in scope for step 3 and no others.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan moves help/version parsing before the run-policy preflight but does not say how arguments are parsed when --help/--

- Severity: HIGH
- References: CHANGE_PLAN s1 D-1 says preflight stays before any state write for all other args; R-3 'only help/version moved earlier'. Mixed forms like `--unattended --version` or `--version build` are unspecified.
- Failure: Plan moves help/version parsing before the run-policy preflight but does not say how arguments are parsed when --help/--version appear alongside other args. Decide: help/version is honored only when it is the sole argument (or first), and any other combination still runs preflight before any state write.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: No stated guarantee that the early help/version path performs no side effects (no state write, no journal, no worktree/b

- Severity: HIGH
- References: CHANGE_SPEC SB-1/SB-2 and SI-1 only specify output and exit code. Nothing in the plan or spec covers side-effect freedom for the early path.
- Failure: No stated guarantee that the early help/version path performs no side effects (no state write, no journal, no worktree/branch creation, no reviewer launch). Add: 'The help/version path prints and exits 0 before sourcing any state, creating directories, or invoking git/agent CLIs; a test asserts the tree is unchanged afterward.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Fixture signing hygiene covers only named files (tree-attested-final-audit-test.sh, build-attestation-test.py) while SB-

- Severity: MEDIUM
- References: CHANGE_PLAN step 3 Owns lists two files; AC-6 requires every fixture commit/tag. Also unspecified: whether fixtures set repo-local gpgsign=false and neutralize inherited global config/GPG agent env.
- Failure: Fixture signing hygiene covers only named files (tree-attested-final-audit-test.sh, build-attestation-test.py) while SB-7 says 'flagged fixtures' and 'every fixture git commit/tag'. Settle scope: all fixture git commit/tag/commit-tree calls under scripts/tests/** must carry the flags, and the supervisor audit is the enforcer.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Fixture isolation for .gitignore and the exit-127 / WorktreeListError fixes lack a rule against a fix that reads or muta

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 and risk s22 (dirty host .gitignore); SB-6 tests must be 'independent of the host checkout's .gitignore'. The dirty .gitignore is also listed as modified in git status.
- Failure: Fixture isolation for .gitignore and the exit-127 / WorktreeListError fixes lack a rule against a fix that reads or mutates the host checkout. State: fixtures run only in disposable temp repos with sanitized HOME/GIT_CONFIG_GLOBAL, and no fix may touch the project's real .gitignore or git config.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Where a missing prerequisite becomes a 'clear message', the plan does not say the suite fails closed.

- Severity: MEDIUM
- References: AC-7 says 'pass or fail only with a clear prerequisite message', while AC-8 requires 0 skipped; D-4 permits adding prerequisite checks, and the two statements leave the outcome of a missing tool ambiguous.
- Failure: Where a missing prerequisite becomes a 'clear message', the plan does not say the suite fails closed. Add: 'A missing tool produces a nonzero exit naming the tool; it must never be reported as a pass or a skip.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan never says how args parse when --help/--version combine with other args (`--version --unattended`, a build requ

- Severity: HIGH
- References: CHANGE_PLAN s1.1 D-1 and R-3 ('only help/version moved earlier'); CHANGE_SPEC SB-1/SB-2 list only bare-flag triggers.
- Failure: The plan never says how args parse when --help/--version combine with other args (`--version --unattended`, a build request, unknown flags). Settle it: 'If --help, -h or --version appears anywhere in argv, print it, exit 0, skip preflight and write no state; --help wins over --version.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-8 requires 0 failed on run-all-tests.sh, but AC-7/SB-8 allow suites to 'fail with a clear prerequisite message'.

- Severity: HIGH
- References: CHANGE_SPEC AC-7 ('pass or fail only with a clear prerequisite message') vs AC-8 ('exits 0 reporting 0 failed').
- Failure: AC-8 requires 0 failed on run-all-tests.sh, but AC-7/SB-8 allow suites to 'fail with a clear prerequisite message'. These conflict, and 'clear' is untestable. Settle it: 'A suite failing on a missing prerequisite counts as FAIL for AC-8; the message wording is checked by a named test or manual check.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The causes of the exit 127 and gates-verification-integrity failures are unknown, so SB-8/AC-7 have no concrete expected

- Severity: HIGH
- References: CHANGE_SPEC s15 ('UNRESOLVED until reproduced'); CHANGE_PLAN s22.
- Failure: The causes of the exit 127 and gates-verification-integrity failures are unknown, so SB-8/AC-7 have no concrete expected behavior to test. Settle it: 'Step 1 records each cause and its expected behavior; if no cause is found, the suite is listed as unresolved and AC-7 is marked not met.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: AC-5 requires passing 'with a dirty host .gitignore' but no step creates that condition; the dirty state of this worktre

- Severity: MEDIUM
- References: CHANGE_SPEC AC-5 verification is only 'run-all-tests.sh'; CHANGE_PLAN s9.1.r3.
- Failure: AC-5 requires passing 'with a dirty host .gitignore' but no step creates that condition; the dirty state of this worktree is incidental. Settle it: 'attestation-statement-test.py is run with a host .gitignore containing `.uncle` and again with it clean; both must pass.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The plan says each suite 'fails before and passes after', but the baseline was taken in a dirty tree where some failures

- Severity: MEDIUM
- References: CHANGE_PLAN s16-17 ('Each fails before and passes after') vs s22 (failures may 'vanish on clean main').
- Failure: The plan says each suite 'fails before and passes after', but the baseline was taken in a dirty tree where some failures may be host artifacts, so the before-state is ambiguous. Settle it: 'Failures are judged against clean main; failures seen only in the dirty tree are recorded as host-state and need no code change.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: SB-4 requires 'no ref, no journal, no mutation' in skip contexts, but the plan gives no way to detect 'no mutation'.

- Severity: MEDIUM
- References: CHANGE_SPEC SB-4 and SI-3; CHANGE_PLAN s9.1.r4 ('product or fixture per triage').
- Failure: SB-4 requires 'no ref, no journal, no mutation' in skip contexts, but the plan gives no way to detect 'no mutation'. Settle it: 'Verification compares `git for-each-ref` and a file-hash inventory before and after each skip context; any difference fails.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
