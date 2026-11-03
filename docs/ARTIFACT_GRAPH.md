# Artifact graph scheduler: design proposal

Status: proposal, not approved, no driver code changed.
Goal: a new-application build finishes consistently in about 4 minutes. Measured today: 8m09s to 10m36s.

## Measured critical path (run 3, 488s)

| Stage | Seconds |
|---|---:|
| IMPLEMENT | 226 |
| PROJECT_PLAN | 74 |
| TEST_REVIEW | 46 |
| FINAL_AUDIT | 39 |
| UPDATED_PLAN | 28 |
| EXECUTE_CHECKLIST | 24 |
| ADVERSARIAL_REVIEW | 19 |
| REQUIREMENTS | 16 |
| MANUAL_CHECKLIST | 10 |

Inside IMPLEMENT the parallel steps take about 80s (wave 1 about 46s, wave 2 about 36s). Then a single lead
agent runs for 135s. It opens by reporting vitest failures in the key and UI tests, fixes them, runs the
defect injections and Playwright, and writes the notes. That is a repair pass inside IMPLEMENT, every run.

The mutation runner (23.5s) also runs twice on an unchanged tree, in IMPLEMENT and again in FINAL_AUDIT.

## What a graph fixes and what it does not

A graph removes dead time between stages. It does not remove the 135s lead agent, because that time is spent
on test/code mismatches, which is a content problem. Reaching 4 minutes needs both, and the second matters more.

## Model

A node is one producer of one artifact. Every node declares:

- `inputs`: artifacts, or named parts of an artifact, it reads;
- `approvals`: approval records it needs before it may start;
- `writes_source`: whether it changes the project tree;
- `speculative_ok`: whether it may start before its approvals exist.

A node is ready when its inputs exist and its approvals are recorded. A speculative result carries the
content hash of every input it read, and is adopted only if those hashes still match when its consumer
needs it. This is the rule `adopt_speculative` already applies to one stage; the graph applies it to all.

## Constraints the graph must keep

- Source-writing nodes never start before `UPDATED_PROJECT_PLAN.md` has an approval record (CLAUDE.md).
  In unattended mode the approval is recorded automatically; the edge is still enforced.
- Reviewer artifacts stay reviewer-owned, and a reviewer reads a finished artifact, not a partial one.
- A discarded speculative node costs tokens. Speculate only where the input is almost always unchanged.

## Phases

1. **Declare, do not schedule.** Describe today's stages as nodes in one data file and validate that the
   current order is a valid topological order of it. No behaviour change. Output: the real critical path.
2. **Remove the repeated work.** Reuse the IMPLEMENT-stage mutation-runner result in FINAL_AUDIT when the
   tree hash is unchanged. About 23s, no model involved.
3. **Pipeline inside IMPLEMENT.** Replace wave barriers with per-step input edges, and run vitest and the
   build as each wave lands, feeding failures back to the same workers. Aim: remove most of the 135s lead agent.
4. **Overlap the tail.** Start EXECUTE_CHECKLIST when the build passes, and TEST_REVIEW when the tests exist.
5. **Graph-driven scheduler.** Only if phases 1 to 4 leave the target unmet.

## Verification

Each phase is judged on repeated runs of the same application command: wall time, repair count, final audit
blockers. A change that speeds up a run but raises the failure rate is rejected. Phase 3 changes what
the test and source workers see of each other, so it needs the largest number of runs.

## Not decided

- Whether phase 3 should try to prevent the key/UI test mismatches (for example a shared contract of
  accessible names and test ids written before the fan-out) or repair them in the loop. The contract is
  cheaper if it works.
- Whether 4 minutes is reachable at all with planning at about 137s. If planning stays near that, the
  rest of the build has about 100s.

## Migrating the driver from bash to Python

Direction from the maintainer: the driver moves from the bash state machine to Python, and the graph
scheduler is built there, not in bash.

Size today: `stagegate.sh` 6,525 lines (100 functions, 59 states), `change-workflow.sh` 4,944, about 24,600
lines of bash under `scripts/`. `scripts/lib` already holds about 40,000 lines of Python, so most of the logic
is already Python and what remains in bash is orchestration: state transitions, gates, process control,
speculation, prompt assembly.

### Approach: strangler, not rewrite

A rewrite of both drivers in one change cannot be verified. Instead:

1. **A Python driver owns the loop.** It reads and writes the state file, dispatches the 59 states, and runs
   the graph. Each state handler starts as a call into the existing bash code, so behaviour is unchanged.
   This needs the bash functions to be sourceable. `stagegate.sh` runs its main loop when executed, so
   the functions move into a library file first, with no change to what they do.
2. **Port state by state**, ordered by speed value: IMPLEMENT and the parallel step runner first, then
   verification, then the review and checklist stages, then the gates. A ported state's bash body is deleted
   in the same change, so there is never two implementations of one state.
3. **`change-workflow.sh` and `from-issue.sh` follow** once the new-application driver is done. They share
   `gates.sh`, `green-check.sh` and `audit-verdict.sh`, which port once.

### Safety net

The 75 shell tests that run `stagegate.sh` are the regression suite: a port is accepted only if they pass
unchanged. Porting a state also adds a Python unit test for its transitions. Repeated builds of the same
application command judge speed and failure rate, as for every other phase.

### Hazards

- **Bash reads a running script incrementally.** Editing `stagegate.sh` while a build is running can break
  that build. All driver work happens in a separate tree or after the measurement runs finish.
- Gate and approval behaviour (CLAUDE.md) must be reproduced exactly, including the unattended records of
  what nobody reviewed.
- The prompts, the state file format and the on-disk artifacts are interfaces that other tools read
  (`uncle_tui.py`, `performance-report.sh`, `uncle verify`). They stay stable through the port.

### Order of work

0. Extract the bash functions into a sourceable library with no behaviour change. Tests pass unchanged.
1. Python driver skeleton that runs the existing states through the library. Same builds, same results.
2. The artifact graph and its scheduler, in Python.
3. Port IMPLEMENT and its fixup loop.
4. Port the remaining states, then the other two drivers.

## Finding from runs 4 and 5: later-wave workers are told to work blind

Waves put tests and the mutation list after the source, but the step worker prompt (`## Speed (binding)` in
stagegate.sh, mirrored in change-workflow.sh) is the same for every wave. It tells a worker not to read files other
steps own because "they are being written right now and may not exist yet", to write everything in the first response,
and not to run tests. For wave 1 that is right. For waves 2 and 3 the source is final and merged, and the rule keeps
the one reader who could check the contract from checking it.

Observed consequences: mutation `find` strings that match zero or two times (runs 1 and 4), a theme test whose
"nearest opaque surface" helper disagrees with the CSS (run 5), and a lead agent that spends about 135s afterwards
fixing what the workers could have fixed while they held the context.

Two mechanical gaps stand behind it. Sandboxes exclude generated directories, so a worker has no `node_modules` and
cannot run what it writes. And nothing installs or builds between waves.

### Phase 3, as built

1. After each merged wave, run the plan's dependency install and the build before the next wave starts. A source
   error then stops the build at the wave that caused it.
2. Later-wave sandboxes link the project's dependency directories read-only.
3. Workers in waves 2 and 3 get a different section in place of Speed: read the source you test, write your files,
   run only your own test once, fix your own files until it passes, and report a source defect instead of editing it.

## Module streaming (decided after runs 15 and 16)

Measured (runs 15, 16; 12m36s and 14m32s): the plan stages are about 2 minutes and already parallel inside; IMPLEMENT through
EXECUTE_CHECKLIST is about 10. Of that, the checklist (early run, fix pass, rerun, real stage) is the largest single cost, and a
fix pass that touches one file invalidates the fingerprint of every row, so the real stage runs most rows again (run 16: 155 s).
Splitting the plan stages by module would save at most about 40 s and is the riskiest to build. It is deferred.

Order of work, each step measured by a real run before the next:

1. **Plan modules own their tests.** Done: the planner puts a unit-testable source file in one step with its unit tests. Run 16
   produced `engine.js`+test and `keymap.js`+test; both workers ran their own tests.
2. **A fix keeps source and tests together.** Done: the early-checklist fix prompt tells a worker to change a test it owns when
   its fix changes behavior that test asserts (run 16's repair came from the fix changing Backspace-in-Error and not its test).
3. **Rows depend on modules, not on the whole tree.** Measured on run 16 and dropped: none of its 18 drafted rows carries a
   plan ID (B-n, I-n, ...), so the plan's requirement trace cannot map a row to files, and almost every row is an end-to-end
   browser journey (click arithmetic, keyboard, Error recovery, resize, long input) that needs the engine, the key map, the
   component and the styles together. Page load already imports every module, so a loaded-file list would name all of them.
   A file-level dependency would keep the whole-tree rule for nearly every row. Mapping rows by file is not worth building.
   What a fix really invalidates is behavior, and nothing says which rows exercise a behavior.
   The cost that remains has a different cause, found in run 16: the drafted row said "Backspace is ignored in Error", the plan
   was silent about Backspace in Error, and the code did the opposite. Rows and plan disagree because the plan leaves
   input-in-Error-state unspecified. The cheaper lever is upstream: have the plan state the behavior of every input in every
   state, so rows and code start from the same text and the early run fails less.
4. **Stream rows as modules land.** A row starts when every module it depends on has merged and built, independently of the
   other modules. Rows with no mapping wait for the whole wave, as now.
5. **Per-module test review.** A module's own unit tests and assertion quality are reviewed when the module merges. Whole-app
   rows, the final green check and the audit still run once at the end, which is where the app is checked as one whole.
6. **Plan stages by module.** Only if steps 3 to 5 leave the plan stages as the long pole.

Unattended runs only at first: attended gates stay stage by stage.

Not changing: attestation (each module's stages are recorded as separate artifact records), the whole-plan adversarial review
(cross-module contracts need one view), and the rule that only a PASS is reused.
