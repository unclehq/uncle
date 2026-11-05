# Change Plan

Issue 158

Seeded from [unclehq/uncle#158](https://github.com/unclehq/uncle/issues/158).

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (none, behavior confined to /housekeeping); Concurrency detail folded into approach

## 1. Selected technical approach

D-1: Script uses its own flock `.uncle/workflow/housekeeping.lock` instead of `driver.lock`, and stops writing `.uncle/workflow/mode`. D-2: TUI, when a workflow is active, launches housekeeping as an independent Popen (`self.hk_proc`, stdin DEVNULL, stdout/stderr to `.uncle/workflow/housekeeping/tui.out`, `--unattended`), never touching `self.proc`/`state`. Decision (AR-014): the TUI shows NO extra confirmation before a background launch; the user typing `/housekeeping` is the consent, because a confirm prompt cannot be answered with stdin DEVNULL and would block the build chat. A background run always passes `--unattended` regardless of the user's attended/unattended preference, the deterministic deny list applies identically (unchanged), and `--unattended` affects only the housekeeping process, never the build's persisted mode. The attended confirmation remains only on the idle foreground path. This relaxation of the attended gate is declared for human approval at the plan gate. D-3: a `_poll_housekeeping` called beside `_poll_workflow` posts one chat notice on exit and clears `hk_proc`. The notice state is derived solely from the `hk_proc.poll()` return code: exit 0 maps to DONE; any non-zero exit, a negative return code (killed by signal) or an unobtainable return code maps to FAILED. The notice always includes the exit code (or the signal number for a negative code); no state file is read. D-4: prompt gains a rule that housekeeping must not modify the working tree or the branch under build. Permitted: deleting non-current branches (e.g. branch cleanup). Forbidden: checkout, switch, reset, clean, stash, commit, and editing files in the working tree. The prompt must name working tree, checkout, reset, clean and current branch. D-5 (AR-003): before choosing either path, `/housekeeping` first checks `hk_proc`; any invocation while `hk_proc` is not None and `hk_proc.poll()` is None (build active or idle) is refused with chat_error 'Housekeeping already running'. While any housekeeping run is active (foreground idle-path or background), /new, /issue and /change are ALLOWED and are not refused; housekeeping.lock is independent and never checked by build drivers, and the TUI does not gate build launch on housekeeping state. When idle, `/housekeeping` keeps the existing foreground path.

D-5 (AR-007): A build may start while housekeeping runs. `housekeeping.lock` is independent and is never checked, taken or released by any build driver (`workflow.sh`, `change-workflow.sh`), and `driver.lock` is never checked by housekeeping. Neither process blocks or refuses the other; the only guard on the shared working tree is the D-4 prompt rule.

Definition of 'workflow active' (TUI branch): active means `self.proc is not None` and `self.proc.poll() is None`. Gate waits with a live driver process count as active; a finished build (self.proc None or exited, even with workflow_exit_* set) is idle. When active, /housekeeping launches the background Popen; otherwise the existing foreground path is used.

## 2. Alternatives
A: Make build driver lock shared-read (invasive, touches all drivers). B: Spawn housekeeping in a separate worktree (heavy; agent chores target the repo itself). Rejected.

## 3. Why preferred
Smallest surface: two files of logic, no build-driver changes.

## 4. Components to modify
See impact table.

## 5. Not to modify
`scripts/workflow.sh`, `scripts/change-workflow.sh`, `scripts/lib/mode.sh`, `housekeeping_config.py`, `housekeeping_policy.py`, `uncle` launcher, deny floor.

## 6-8. Data flow / state / interface

No new CLI/API. TUI gains attribute `hk_proc` and a chat notice; script's lock file name changes. Note for D-1: mode resolution (`uncle_resolve_mode`) is unchanged and still derives unattended default; only the persisted mode file write is removed.

Build-start interaction (AR-007): build drivers do not read `housekeeping.lock`; starting a build (`/new`, `/issue`, `/change`, or from a terminal) while housekeeping runs is permitted and unaffected.

## 10. Compatibility

Stale `driver.lock` semantics for builds unchanged. Tests asserting the mode file written by housekeeping or driver.lock refusal for housekeeping are updated (see 16).

Build drivers are unchanged and remain unaware of housekeeping; a build started during a housekeeping run behaves exactly as when none is running (AR-007).

## 11. Concurrency

Two processes: build driver (driver.lock) and housekeeping (housekeeping.lock) — disjoint lock files and disjoint records dir. Housekeeping writes only under `.uncle/workflow/housekeeping/` and to `.uncle/workflow/housekeeping.lock`; it reads the persisted mode (via `uncle_resolve_mode`) but never writes it, and writes no other build artifacts (driver.lock, mode, documents, state). `--unattended` affects only the housekeeping process. Residual risk, explicitly accepted at the plan gate: the housekeeping agent shares the build's working tree. The only control against it modifying the tree/branch under build is the D-4 prompt rule. The existing deterministic deny list/deny floor applies to background runs exactly as to foreground runs and is NOT extended (housekeeping_policy.py and the deny floor stay untouched), so checkout/reset/clean/switch/stash are not newly blocked by code for concurrent runs. This is a declared guard rail, not a sandbox; approving this plan constitutes the human's acceptance of that residual risk.

Build start during housekeeping (AR-007): allowed. Because `driver.lock` is no longer taken by housekeeping, nothing excludes a new build from starting mid-run; the two lock files are independent and neither side checks the other's lock (build drivers never check `housekeeping.lock`). File handling for new files (AR-016): `.uncle/workflow/housekeeping.lock` and `.uncle/workflow/housekeeping/tui.out` are created only inside `.uncle/workflow/` with the process default umask/file modes (no chmod widening). The TUI opens tui.out with O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW (truncated each launch, so no stale output carries over) and the script opens housekeeping.lock with O_NOFOLLOW; if either path is a symlink the open fails and the run is refused with an error (TUI chat_error / script exit 1) rather than following it. housekeeping.lock is a flock; a leftover file with no holder is not stale state, since the kernel releases the lock on exit and the next run simply re-acquires it.

## 12. Error and recovery

Popen failure: chat_error, hk_proc None. Refusal rule: any /housekeeping, whether the build is active or idle, is refused with chat_error 'Housekeeping already running' only when hk_proc is not None and hk_proc.poll() is None (checked before the foreground/background branch); an exited hk_proc not yet cleared by the poll does not block a new launch. If housekeeping.lock is held by a run from another terminal, hk_proc is None, so the TUI launches the script; the script exits 1 on the held lock, and the poll posts 'Housekeeping already running' (not a FAILED notice). The poll identifies this case by exit code 1 together with the script's lock-refusal message in tui.out. Any other exit is reported once: exit 0 is DONE; any other nonzero exit, or a run killed by signal, is FAILED with its exit code (or signal number, e.g. -15) in the notice. flock is released by the kernel on exit. Stopping the build never stops housekeeping; quitting the TUI terminates a live hk_proc via the existing stop-tree helper and posts no completion notice for that run (quit sets a flag so _poll_housekeeping stays silent).

AR-004 rule: Starting a build (/new, /issue, /change) while housekeeping runs is allowed; housekeeping.lock is independent and never checked by build drivers, and builds do not check hk_proc. The housekeeping completion notice is posted by _poll_housekeeping independently of build state (active, idle, gated, or finished), and a build stop never stops housekeeping.

## 14. Rollback

`git revert` of the change; no persisted data format to restore. Mode semantics under rollback and as shipped: housekeeping never writes `.uncle/workflow/mode` (it may read it); the idle foreground `/housekeeping` path keeps its existing attended confirmation behavior unchanged; a background launch is always `--unattended`, which affects only the housekeeping process and never the build's persisted mode. No component may rely on a housekeeping-written mode file; any existing test asserting that write is updated per section 16.

## 16. Automated-test strategy

Additional test assertions (AR-003, AR-011, AR-013, AR-016): in `tui-housekeeping-test.py` (step 5): /housekeeping is refused with 'Housekeeping already running' while hk_proc is alive, once with the build active and once with it idle; empty /housekeeping text spawns no process and posts a usage chat_error; the background Popen receives stdin=DEVNULL and the tui.out path opened truncating (O_TRUNC|O_NOFOLLOW), and a symlinked tui.out is refused with chat_error and hk_proc None. In `housekeeping-workflow-test.sh` (step 4): a symlinked housekeeping.lock makes the script exit 1 without following it. Policy test (AR-013): the existing deny-list policy test is run unchanged and asserts checkout, reset, clean, switch and stash are denied under the --unattended invocation; if that test does not already exist, the plan records that no such enforcement exists and the prompt rule is the sole control.

Extend `housekeeping-workflow-test.sh`: (a) hold driver.lock via flock in a helper, run script with stub agent, expect exit 0 and driver.lock still held by helper; (b) run the script twice, once with the mode file absent and once with it present, and assert it is unchanged in both cases (still absent after the first run; hash identical after the second); (c) second concurrent run exits 1; (d) prompt.md must contain a prohibition naming each of: `working tree`, `checkout`, `reset`, `clean`, and `current branch`; the shell test greps prompt.md for each of these five strings separately and fails if any is absent. Extend `tui-housekeeping-test.py`: replace `test_refused_while_workflow_active` (existing expectation conflicts with SB-1; change is in scope per Issue 158 and recorded in IMPLEMENTATION_NOTES) with tests for background launch, double-launch refusal, completion notice; add a quit test: quit with a live hk_proc calls the stop-tree helper on hk_proc and posts no completion notice; keep `/new` etc. refusal test.

Added for AR-007 in `housekeeping-workflow-test.sh`: (e) with housekeeping.lock held by a helper flock, `driver.lock` can still be acquired by a stand-in build and `housekeeping.lock` is not referenced by any build driver (grep of `scripts/workflow.sh` and `scripts/change-workflow.sh` for `housekeeping.lock` finds nothing).

## 17. Regression-test strategy

Full `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` (baseline commands, group 1 2). Housekeeping launch behavior to cover: Popen failure yields chat_error and hk_proc None. The TUI refuses a second run only when hk_proc is not None and hk_proc.poll() is None ('Housekeeping already running'). If hk_proc is None (e.g. a run from another terminal holds housekeeping.lock), the TUI launches anyway; the script exits 1 on the held lock, and the TUI posts 'Housekeeping already running' (not a FAILED notice) when the exit code is 1 and tui.out contains the lock-refusal message. Any other non-zero exit, signal or missing exit maps to FAILED with the exit code or signal. Empty TEXT is rejected by the TUI before launch with a usage chat_error and no Popen. tui.out is truncated on each launch (opened 'w', not append), so it reflects only the latest run. flock is released by the kernel on exit. Stopping the build (stop/cancel of self.proc) never stops housekeeping; quitting the TUI always terminates hk_proc via the existing stop-tree helper if it is alive, and posts no completion notice.

## 18. Manual verification
Start a build in the TUI, run `/housekeeping list merged branches`, observe build continues and a completion notice appears.

## 19. Observability
Chat notices; `.uncle/workflow/housekeeping/tui.out`, existing run.log/state.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/housekeeping-workflow.sh` | own lock, drop mode-file write | AC-2, AC-3, AC-4 | Medium: lock semantics | housekeeping-workflow-test.sh |
| `prompts/housekeeping-plan.md` | working-tree rule: prohibition in prompt.md naming `working tree`, `checkout`, `reset`, `clean` and `current branch`; sole control for working-tree safety of concurrent runs; deny list unchanged | AC-6 | Medium: prompt-only guard, residual risk accepted by human at plan gate | housekeeping-workflow-test.sh |
| `uncle_tui.py` | background launch (no confirm prompt, always --unattended, deny list unchanged), poll, one-shot notice (DONE iff return code 0, else FAILED with exit code/signal), stop on quit with no notice | AC-1, AC-4, AC-5 | Medium: TUI state | tui-housekeeping-test.py |
| `scripts/tests/housekeeping-workflow-test.sh` | new/updated cases | AC-2..AC-6 | Low | self |
| `scripts/tests/tui-housekeeping-test.py` | replace refusal test, add cases incl. exit-code to DONE/FAILED notice mapping (0, non-zero, signal-killed FAILED notice) and quit-with-live-hk_proc (stop-tree called, no notice); tests fix active state explicitly (live self.proc mock => background Popen; None or exited self.proc => foreground path) | AC-1, AC-4, AC-5 | Low | self |
| `README.md` | document concurrent housekeeping | docs | Low | none |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: when `self.proc is not None and self.proc.poll() is None` (workflow active), /housekeeping launches a background Popen without touching self.proc/state; otherwise the foreground path is used. | SB-1 | SI-4, SI-5 | uncle_tui.py | tui-housekeeping-test.py: background launch while build active; starting a build while hk_proc is alive is allowed | build + /housekeeping |
| AC-2 | SB-2 | SI-5 | housekeeping-workflow.sh | housekeeping-workflow-test.sh | n/a |
| AC-3: Housekeeping never reads or changes the build's persisted mode file (present or absent, it is unchanged); its --unattended flag affects only the housekeeping process and has no effect on a build running attended. | SB-3 | SI-3 | housekeeping-workflow.sh | housekeeping-workflow-test.sh | n/a |
| AC-4: a second housekeeping run is refused by the script (exit 1) while housekeeping.lock is held. The TUI refuses to launch only while its own hk_proc.poll() is None (exited-but-uncleared hk_proc allows relaunch). When the lock is held elsewhere (e.g. another terminal) and the script exits 1, the TUI surfaces a FAILED notice carrying the lock message. | SB-4 | SI-1 | script, uncle_tui.py | housekeeping-workflow-test.sh: second concurrent run exits 1 with lock message, tui-housekeeping-test.py: refusal only when hk_proc.poll() is None; exited-but-uncleared hk_proc allows relaunch; script exit 1 (lock held elsewhere, hk_proc None before launch) yields FAILED notice with lock message, not 'already running' | n/a |
| AC-5: on exit of a background housekeeping run (not terminated by TUI quit) the TUI posts exactly one chat notice whose state comes only from hk_proc's return code: 0 is DONE; any other exit, signal (negative code) or unobtainable code is FAILED; the notice includes the exit code or signal. The notice is posted regardless of build state (idle, stopped or finished). A run terminated by TUI quit posts no notice. | SB-6 | SI-4 | uncle_tui.py | tui-housekeeping-test.py: exit 0 yields DONE notice with code 0, tui-housekeeping-test.py: exit 1 and exit 2 yield FAILED notice with the code, tui-housekeeping-test.py: negative return code (e.g. -9) yields FAILED notice naming the signal, tui-housekeeping-test.py: notice posted on exit, including when the build is idle, stopped or finished, tui-housekeeping-test.py: quit with live hk_proc calls stop-tree helper and posts no notice | observe notice |
| AC-6: prompt.md contains a prohibition on modifying the working tree/branch under build, naming working tree, checkout, reset, clean and current branch. | SB-7 | SI-2 | prompt, script | housekeeping-workflow-test.sh greps prompt.md for each of: working tree, checkout, reset, clean, current branch, policy test | n/a |
| AC-7: SB-5/SB-8 regression coverage, including that /new, /issue and /change remain allowed while a housekeeping run (foreground or background) is active. | SB-5, SB-8 | SI-4 | all | full runners, tui-housekeeping-test.py: /new,/issue,/change not refused while hk_proc alive | n/a |

AC-3 clarification (AR-015): `--unattended` passed to housekeeping is process-local. Housekeeping neither reads nor writes `.uncle/workflow/mode`; a concurrently running attended build keeps its persisted mode. `uncle_resolve_mode` is unchanged.

## Restrictions

| R-ID | source_kind | Source | Req | Property | Mechanism (revisable DESIGN) | Rationale | CAP | Phase | Feasibility evidence |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Acceptance | AC-1..3 | Housekeeping must not alter build inputs/results/tree | separate lock, no mode write, prompt rule | disjoint shared state | CAP-LOCK | CODING | housekeeping-workflow.sh:60-83 inspected |
| R-2 | REPOSITORY | CLAUDE.md | AC-7 | Do not weaken tests | only conflicting refusal test replaced | requirement-based | CAP-TEST | CODING | tui-housekeeping-test.py:51 inspected |
| R-3 | REPOSITORY | CLAUDE.md | all | No project commits | none made | policy | CAP-NONE | CODING | n/a |

Live verification: no credentials needed; all checks are automated with stub agents. Runner binding: shell/Python runners per baseline commands.

## 20. Implementation sequence

1. S-1 Script lock and mode change (D-1, D-4 hook, D-5): edit housekeeping-workflow.sh to use `housekeeping.lock` and drop mode write; do not add any housekeeping.lock check to build drivers. Open the lock file without following symlinks (refuse with exit 1 if the path is a symlink) and with default file modes, per the s8 file-handling rule.
   Owns: `scripts/housekeeping-workflow.sh`
2. S-2 Prompt rule (D-4): add working-tree rule to prompts/housekeeping-plan.md. Permitted: deleting non-current branches. Forbidden: checkout, switch, reset, clean, stash, commit, and editing the working tree or the current branch.
   Owns: `prompts/housekeeping-plan.md`
3. S-3 TUI background launch, poll, notice, quit cleanup (D-2, D-3). Background launch always passes --unattended, never shows a confirmation prompt, and relies on the unchanged deny list; the attended confirmation stays only on the idle foreground path. Open `.uncle/workflow/housekeeping/tui.out` truncating, with O_NOFOLLOW and default modes; on symlink or open failure post chat_error and leave hk_proc None. The completion notice maps hk_proc return code 0 to DONE and any other code or signal to FAILED, including the code in the text.
   Owns: `uncle_tui.py`
4. S-4 Shell tests for AC-2..AC-6: lock independence, mode file absent and present, second-run exit 1, prompt.md grepped separately for `working tree`, `checkout`, `reset`, `clean` and `current branch` (the exact strings fixed by step 2), and symlinked housekeeping.lock refusal.
   Owns: `scripts/tests/housekeeping-workflow-test.sh`
   Depends on: 1, 2
5. S-5 TUI tests for AC-1, AC-4, AC-5 (replaces existing refusal test); includes cases for DONE notice on exit 0, FAILED notice with exit code on non-zero exit, signal-killed run reported FAILED, and quit with live hk_proc calling the stop-tree helper and posting no notice.
   Owns: `scripts/tests/tui-housekeeping-test.py`
   Depends on: 3
6. S-6 README note.
   
   Steps 1, 2, 3 are independent files and may run in parallel.
   Owns: `README.md`
   Depends on: 1, 3

## 21. Scope cuts under time pressure
Cut first: README (S-6), then completion notice (SB-6/AC-5), then prompt-test assertion. Never cut lock separation, mode-file isolation or SB-1.

## 22. Risks and unresolved questions
- Agent may still edit the working tree despite the prompt rule (guard rail only; documented, not sandboxed).
- SI-5 is a RELAXED invariant needing human approval at the plan gate; it is the requested feature.
- Existing test replacement in S-5 is flagged for reviewer attention.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan was silent on attended users and confirm prompts for background runs; stating the rule removes ambiguity. | Section 1 (s1.1) now states a background run always passes --unattended, the deny list applies identically, and no confirmation is shown; step 3 text updated to match. |
| AR-002 | Accepted | A lock held by another terminal leaves hk_proc None; the script's exit 1 must be distinguished from a real failure. | Edit s9.1 and AC-4 so a script exit 1 from a held housekeeping.lock posts 'Housekeeping already running', not FAILED. |
| AR-003 | Accepted | The plan left /housekeeping while a background run is alive but the build is idle unspecified; refusing on a live hk_proc regardless of build state closes that gap. | Edited s1.1 and s9.1 so any /housekeeping while hk_proc.poll() is None is refused with 'Housekeeping already running', active or idle. |
| AR-004 | Accepted | Starting a build during housekeeping is unspecified; we decide it is allowed because the locks and records dirs are disjoint, and the notice is independent of build state. | Section 12 (s9.1) gains the allowed-build and build-independent-notice rule; AC-1 and AC-5 requirements and tests updated to match. |
| AR-005 | Accepted | Quit-vs-notice conflict is real; deciding that a quit-terminated run posts no notice while signal kills report FAILED with the signal/exit code resolves it. | Edit s9.1 error/recovery text, AC-5 requirement/tests, s15.1.r3 and r5 rows, and step-5 to specify and test the quit and signal behavior. |
| AR-006 | Accepted | The records location and the script's mode-file access were unstated, so SI-3's scope was ambiguous. | Section 11 (s8.1) now states the write set (housekeeping/ dir and housekeeping.lock) and that mode is read, never written. |
| AR-007 | Accepted | Dropping driver.lock removes the only build/housekeeping exclusion, so the plan must state that a build may start while housekeeping runs. | Added build-concurrency rule to s1 (D-5), s8 concurrency note, s6 interface note, and a shell test plus step-1 note that build drivers never check housekeeping.lock. |
| AR-008 | Accepted | Interaction of any active housekeeping run (foreground or background) with /new, /issue, /change was unspecified; builds are allowed since housekeeping.lock is independent. | Added decision D-5 to s1.1 and updated AC-7 requirement/tests to state /new,/issue,/change are allowed while housekeeping runs. |
| AR-009 | Accepted | Real gap: the plan did not state how mode-file removal affects the idle foreground path or readers of the old mode file. | Section 14 (s10.1) now states mode semantics: foreground keeps its attended confirmation, background is unattended, and no reader depends on a housekeeping-written mode file. |
| AR-010 | Accepted | Section 12 contradicted itself on whether quit stops housekeeping; the two events are distinct and need distinct rules. | Section 12 now states stopping the build never stops housekeeping, while quitting the TUI always terminates hk_proc. |
| AR-011 | Accepted | TUI guard keys on hk_proc while the script lock is housekeeping.lock, so a lock held from another terminal and TUI output handling were undefined. | Edit s12.1 to specify exit-1 lock refusal notice, empty TEXT handling and tui.out truncate-on-launch. |
| AR-012 | Accepted | The prompt rule must not forbid legitimate repo chores such as branch cleanup, so permitted and forbidden actions need to be stated explicitly. | Section 1 (D-4) and step-2 now specify permitted (delete non-current branches) vs forbidden (checkout, reset, clean, commit, edit working tree) actions. |
| AR-013 | Partially accepted | Deterministic denies would require changing the deny floor/policy, which is out of scope; instead the plan declares the prompt rule the sole control for working-tree safety, plus a test, and makes the residual risk explicit for human acceptance. | Edit s8.1 and s1.1 to state the prompt rule is the only control and the human accepts it at the plan gate; unchanged deny list still applies; AC-6 and s15.1.r2 note this. |
| AR-014 | Accepted | Dropping the attended gate for a repo-writing agent must be an explicit, human-visible decision; the user's slash command is the consent and the deny list still applies. | s1.1 D-2 states background launch needs no confirmation, is always --unattended, deny list unchanged; s15.1.r3 and step-3 note it. |
| AR-015 | Accepted | Real gap: with mode-file write removed, the plan must state that housekeeping's --unattended is process-local and never touches a running build's persisted mode. | AC-3 requirement and a new prose block in Traceability state housekeeping never reads or changes the build's persisted mode; --unattended affects only the housekeeping process. |
| AR-016 | Accepted | New housekeeping.lock and tui.out files had no stated location, mode, symlink or stale-state behavior; a short rule closes the gap. | Added a file-handling rule to s8 (concurrency/state) and extended step-1 to implement it for the lock and tui.out. |
| AR-017 | Accepted | The s12 sentence is self-contradictory; quit and build-stop need distinct, explicit rules. | Rewrote s12.1 so stopping the build never stops housekeeping, while quitting the TUI always terminates hk_proc. |
| AR-018 | Accepted | The plan named no source for DONE/FAILED; the exit status of hk_proc is the authoritative, testable source. | Edit s1.1 (D-3), AC-5, s15.1.r3 and s15.1.r5 to define exit-status mapping and add a test for it. |
| AR-019 | Accepted | The TUI guard on hk_proc and the script's lock refusal are distinct mechanisms; each case needs a defined outcome. | Section 12 and AC-4 now state: refuse only when hk_proc.poll() is None; script exit 1 from a held lock surfaces as a FAILED notice with the lock message; tests added. |
| AR-020 | Accepted | The prompt rule needs fixed required wording so AC-6 is testable beyond a vague 'contains the rule'. | Section 16 test (d), AC-6 requirement/tests and s15.1.r2 now require prompt.md to name working tree, checkout, reset, clean and current branch, each grepped. |
| AR-021 | Accepted | AC-3 permits the mode file to be absent, so a hash-only comparison leaves the absent case untested. | Section 16 test item (b) now runs with the mode file absent and present, asserting it is unchanged (still absent, or hash identical) in both. |
| AR-022 | Accepted | Quit with a live hk_proc is specified but untested and its notice behavior is undefined; a test and an explicit no-notice rule close the gap. | s9.1 states quit posts no completion notice; s11.1 adds a quit test asserting the stop-tree helper call and no notice. |
| AR-023 | Accepted | 'Active' was undefined for the TUI branch; defining it as a live self.proc makes SB-1/SB-5 testable. | Section 1 gains a definition of active (self.proc not None and running); AC-1 and the TUI test row/step reference it. |
