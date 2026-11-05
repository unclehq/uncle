## AR-001: Plan is silent on attended-mode users and confirm-gated actions for a background run; spec only says it is always unatte

- Severity: HIGH
- References: CHANGE_SPEC section 15 Assumptions; CHANGE_PLAN D-2 passes --unattended with stdin DEVNULL.
- Failure: Plan is silent on attended-mode users and confirm-gated actions for a background run; spec only says it is always unattended. Settle with: 'A background run always passes --unattended, the deny list applies identically, and no confirmation prompt is ever shown.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The TUI guard keys on hk_proc, but housekeeping.lock may be held by a run from another terminal.

- Severity: HIGH
- References: CHANGE_PLAN section 12 (hk_proc check) versus SB-4/AC-4 (script lock refusal); SB-6 reports only DONE/FAILED.
- Failure: The TUI guard keys on hk_proc, but housekeeping.lock may be held by a run from another terminal. The case hk_proc None with lock held is unspecified. Settle with: 'If the script exits 1 because housekeeping.lock is held, the TUI posts "Housekeeping already running", not a FAILED notice.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Unspecified: /housekeeping while a background run is alive but the build is idle (foreground path), or before the poll c

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 ('When idle, keeps foreground path') versus section 12 (refusal described only for a second run in TUI).
- Failure: Unspecified: /housekeeping while a background run is alive but the build is idle (foreground path), or before the poll clears hk_proc. Settle with: 'Any /housekeeping while hk_proc is alive, build active or idle, is refused with "Housekeeping already running".'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Starting a build (/new, /issue, /change) while housekeeping runs is unspecified, as is whether the completion notice dep

- Severity: MEDIUM
- References: SB-8 and SI-4 cover only a workflow already active; CHANGE_PLAN section 12 says build stop does not stop housekeeping.
- Failure: Starting a build (/new, /issue, /change) while housekeeping runs is unspecified, as is whether the completion notice depends on build state. Settle with: 'Starting a build while housekeeping runs is [allowed/refused]; the completion notice is posted independently of build state.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Quit terminating hk_proc conflicts with SB-6/AC-5, which require a completion notice with final state; the reported stat

- Severity: MEDIUM
- References: CHANGE_PLAN section 12 versus SB-6 'DONE/FAILED and exit code'.
- Failure: Quit terminating hk_proc conflicts with SB-6/AC-5, which require a completion notice with final state; the reported state of a run killed by quit or signal is unspecified. Settle with: 'A run terminated by TUI quit posts no notice; a run killed by signal is reported FAILED with its exit code.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: SI-3 lists 'build artifacts' undefined, and the plan does not say whether the script still reads mode or where its disjo

- Severity: LOW
- References: CHANGE_SPEC SI-3 versus CHANGE_PLAN section 6-8 and section 11 (records dir claimed disjoint, path unstated).
- Failure: SI-3 lists 'build artifacts' undefined, and the plan does not say whether the script still reads mode or where its disjoint records dir lives. Settle with: 'Housekeeping writes only under .uncle/workflow/housekeeping/ and housekeeping.lock, and reads mode but never writes it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan doesn't say how a build starting while housekeeping runs behaves.

- Severity: HIGH
- References: CHANGE_PLAN s1 D-1/s11; CHANGE_SPEC non-goals leave launcher concurrency unspecified.
- Failure: Plan doesn't say how a build starting while housekeeping runs behaves. Dropping driver.lock removes the only exclusion between them. Settle: 'A build may start while housekeeping runs; housekeeping.lock is independent and never checked by build drivers.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Idle foreground /housekeeping (SB-5) is unspecified against /new,/issue,/change and builds.

- Severity: HIGH
- References: CHANGE_SPEC SB-5/SB-8 vs CHANGE_PLAN s1; SB-8 covers only 'workflow active'.
- Failure: Idle foreground /housekeeping (SB-5) is unspecified against /new,/issue,/change and builds. Settle: 'While any housekeeping run is active, /new,/issue,/change are (refused|allowed).'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Mode-file removal vs attended/unattended: background is always unattended, but the idle foreground path's attended confi

- Severity: MEDIUM
- References: CHANGE_PLAN s6-8 and s10 (existing tests assert mode file written); CHANGE_SPEC s15.
- Failure: Mode-file removal vs attended/unattended: background is always unattended, but the idle foreground path's attended confirmation and any reader relying on the housekeeping-written mode file are unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: hk_proc lifecycle contradicts itself: 'quit/stop of build does not stop housekeeping; quit terminates hk_proc'.

- Severity: MEDIUM
- References: CHANGE_PLAN s12 Error and recovery.
- Failure: hk_proc lifecycle contradicts itself: 'quit/stop of build does not stop housekeeping; quit terminates hk_proc'. Settle: 'Stopping the build never stops housekeeping; quitting the TUI always terminates hk_proc.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: TUI second-run check uses hk_proc, but the script uses housekeeping.lock.

- Severity: MEDIUM
- References: CHANGE_PLAN s12; SB-4 and SB-6.
- Failure: TUI second-run check uses hk_proc, but the script uses housekeeping.lock. A run from another terminal leaves hk_proc None, so the exit-1 notice is undefined. Empty TEXT and tui.out overwrite/append are also unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The prompt rule forbidding working-tree changes conflicts with chores that act on the repo, e.g.

- Severity: LOW
- References: CHANGE_PLAN s2 vs SB-7 and D-4.
- Failure: The prompt rule forbidding working-tree changes conflicts with chores that act on the repo, e.g. branch cleanup. Settle: 'Permitted: deleting non-current branches; forbidden: checkout, reset, clean, commit, edit on the working tree.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Background housekeeping runs an unattended agent with write access to the build's working tree, guarded only by a prompt

- Severity: HIGH
- References: CHANGE_PLAN s11/s22: 'mitigated by D-4 prompt rule only'; s5 forbids touching housekeeping_policy.py and the deny floor; AC-6 keeps the deny list unchanged.
- Failure: Background housekeeping runs an unattended agent with write access to the build's working tree, guarded only by a prompt rule. Plan should say: either deterministic denies (checkout, reset, clean, switch, stash) apply to concurrent runs, or the prompt rule is the only control and the human accepts that.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Background launch is always unattended, dropping the attended confirmation gate for an agent with repo write access.

- Severity: HIGH
- References: CHANGE_SPEC s15: 'background launch is always unattended'; PLAN D-2 passes --unattended.
- Failure: Background launch is always unattended, dropping the attended confirmation gate for an agent with repo write access. Plan should say whether the TUI asks the user to confirm before a background launch.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: With the mode file write removed, it is unspecified how --unattended in housekeeping interacts with a build running atte

- Severity: MEDIUM
- References: CHANGE_PLAN s6-8: uncle_resolve_mode unchanged, only the mode file write removed; SB-3, SI-3.
- Failure: With the mode file write removed, it is unspecified how --unattended in housekeeping interacts with a build running attended. Plan should say: housekeeping never reads or changes the build's persisted mode, and --unattended affects only the housekeeping process.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: New housekeeping.lock and tui.out files have no stated permissions, symlink handling or stale-state behavior.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 D-1/D-2 name the new files; no permission or symlink behavior is described.
- Failure: New housekeeping.lock and tui.out files have no stated permissions, symlink handling or stale-state behavior. Plan should say they are created inside .uncle/workflow with existing file modes and opened without following symlinks.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Quit behavior is self-contradictory: quit does not stop housekeeping, yet quit terminates hk_proc.

- Severity: MEDIUM
- References: CHANGE_PLAN s12: 'TUI quit/stop of build does not stop housekeeping; quit terminates hk_proc via existing stop-tree helper if alive.'
- Failure: Quit behavior is self-contradictory: quit does not stop housekeeping, yet quit terminates hk_proc. Plan should say: quitting the TUI terminates hk_proc, and a stop of the build alone does not.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan never says how the TUI derives DONE/FAILED for the completion notice (SB-6).

- Severity: HIGH
- References: CHANGE_SPEC SB-6 and CHANGE_PLAN D-3 name no source for 'state'; AC-5 cannot be asserted without one.
- Failure: The plan never says how the TUI derives DONE/FAILED for the completion notice (SB-6). Settle with: 'Exit 0 maps to DONE; any other exit, signal or missing state file maps to FAILED; the notice includes the exit code or signal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The TUI second-run refusal rests on hk_proc, but the plan doesn't cover a lock held by another terminal, or an exited hk

- Severity: HIGH
- References: CHANGE_PLAN section 12 (chat_error) vs. AC-4 (script exit 1; TUI notice) describe different mechanisms.
- Failure: The TUI second-run refusal rests on hk_proc, but the plan doesn't cover a lock held by another terminal, or an exited hk_proc not yet cleared by the poll. Settle with: 'The TUI refuses only when hk_proc.poll() is None; a script lock refusal (exit 1) surfaces as a FAILED notice with the lock message.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: AC-6/SB-7 can only be tested as 'prompt.md contains the rule', and no required wording is fixed.

- Severity: MEDIUM
- References: CHANGE_PLAN section 16(d); SB-7 lists the verbs but fixes no exact strings.
- Failure: AC-6/SB-7 can only be tested as 'prompt.md contains the rule', and no required wording is fixed. Settle with: 'prompt.md must contain a prohibition naming working tree, checkout, reset, clean and current branch; the shell test greps each.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: AC-3 allows the mode file to be absent, but the test strategy specifies only a hash comparison.

- Severity: MEDIUM
- References: CHANGE_PLAN section 16(b) vs. CHANGE_SPEC AC-3 'or absent if absent'.
- Failure: AC-3 allows the mode file to be absent, but the test strategy specifies only a hash comparison. Settle with: 'The shell test runs with the mode file absent and with it present, and asserts it is unchanged in both cases.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Quit with a live hk_proc is specified (section 12) but has no test, and whether a completion notice is posted when quit

- Severity: MEDIUM
- References: CHANGE_PLAN section 12 vs. the section 16 TUI test list; no AC covers quit.
- Failure: Quit with a live hk_proc is specified (section 12) but has no test, and whether a completion notice is posted when quit kills it is undefined. Settle with: 'Add a test that quit with a live hk_proc calls the stop-tree helper and posts no completion notice.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: 'Workflow active' is undefined for the TUI branch, e.g.

- Severity: LOW
- References: SB-1 and SB-5 trigger on 'active' vs. 'idle' with no definition; AC-1 mocks Popen without fixing the state.
- Failure: 'Workflow active' is undefined for the TUI branch, e.g. a gate wait or a finished build with workflow_exit_* set. Settle with: 'Active means self.proc is not None and running; otherwise the foreground path is used.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
