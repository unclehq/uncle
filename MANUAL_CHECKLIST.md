# Manual Checklist
Base checks: 8; resolved: 3; added: 5; removed: 0

## Summary

Planned verification of `CHANGE_PLAN.md:AC1–AC3`; no checks executed.

## Findings

All behavior and invariant IDs below refer to `CHANGE_SPEC.md` unless prefixed with `PLAN` or `BASELINE`.

| Check ID | Priority | Behavior classification | Related behavior | Related invariant | Preconditions | Excl | Deps | Exact action | Expected result | Evidence to capture | Actual result | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MC-001 | P0 | MODIFY, ADD | B-1/2; AR-4; PLAN P6/P8/M1 | I-3/4 | Writable disposable project; interactive 80×24 terminal and operator | terminal:manual, fixture:manual | none | Select each missing-input mode in TUI; dismiss separately with Esc, Enter and another key; create required file and reselect; repeat after restarting TUI | “Required input” popup names required filename as needed; footer returns to menu; no partial launch; selection/workflow cleared; retry launches once; restart rechecks disk | Terminal recording/dimensions; launch log; filesystem before/after | | BLOCKED-SETUP |
| MC-002 | P0 | MODIFY, ADD | B-1/2/3; PLAN T1/T2/Q1 | I-3/4 | Writable isolated fixtures; `scripts/tests/menu-input-test.py:20,124` fixtures; restricted identity able to run copied launcher but denied project-directory search permission; stat/open tracing | fixture:matrix, identity:restricted | none | For TUI indices 0/2 call `select()` with `start_workflow` mocked; for shell choices 1/3 use `shell_fixture()` and input choice plus newline then EOF. For each required filename test missing, directory, broken link, denied stat, empty/nonempty regular file, internal/external regular-file symlink, required file alone and both files. Patch TUI `os.stat` with PermissionError; for shell remove project-directory search permission after entering it as the restricted identity, run copied launcher, restore permission and retry. Trace document stat/open calls before mocked/stub launch | First four block; remaining cases launch; no content validation or document creation; stat error does not crash | Fixture matrix; warnings; stat/content-read and launch traces | | BLOCKED-SETUP |
| MC-003 | P0 | PRESERVE, MODIFY | B-6; AR-5/6; PLAN T5/T6/P10 | I-1/2/4 | Writable spaced-path project; `scripts/tests/menu-input-test.py:124` copied installation/stubs; decoy documents in installation cwd; isolated config | fixture:routing | none | Launch copied `uncle` from project cwd: launcher changes to installation cwd (`uncle:6,31`). Run TUI with `UNCLE_PROJECT_ROOT` set to project from decoy cwd; spy on real `cmd_for()` and mocked Popen (`uncle_tui.py:1015,1270`). Exercise indices 0/2 and issue index 1→123→each issue mode; shell input `1\n3\n2\n123\nc\nq\n`, repeating issue mode n/empty. Repeat ordinary, `misc.auto_mode true`, and launcher `--unattended`; compare args with PC1. With files missing send `1\n3\n1\n` then EOF; separately create required file before the next selection in the same process. Record pre-stub cwd and post-`cd` cwd (`scripts/tests/menu-input-test.py:135`), resolving macOS path aliases | Root document controls gate; launch cwd is project root; issue selection precedes launch without premature gating; args unchanged; missing input warns without extra read; shell can retry and handles EOF without looping | Input transcript; exact invocations; ordered calls, args/cwd; exit codes | | BLOCKED-SETUP |
| MC-004 | P1 | PRESERVE | B-4; PLAN P7/M3 | — | Writable fixture; no reader configured; interactive operator | terminal:manual, fixture:manual | none | Dismiss original notice; trigger and dismiss required-input warning; trigger original notice again | Original notice opens Configure each time; required-input warning returns to menu; title/footer/destination metadata does not leak | Terminal recording and destinations | | BLOCKED-SETUP |
| MC-005 | P0 | PRESERVE | B-5; PLAN P11/T7; ADVERSARIAL_REVIEW.md:AR-001 | I-3 selection-time | Writable disposable projects; actual drivers with isolated stub agents; `scripts/tests/menu-input-test.py:205` fixture; external networking disabled | fixture:race | none | Run `python3 -B scripts/tests/menu-input-test.py MenuInputTests.test_selection_race_actual_drivers -v`: TUI launch callback unlinks input; shell BASH_ENV DEBUG trap unlinks before run_new_application/run_change_workflow; both WORKFLOW agent/reviewer commands point to the exit-73 stub. Reuse fresh `shell_fixture(race=True)` projects with initially absent then empty CHANGE_REQUEST.md and run copied `scripts/change-workflow.sh` directly with UNCLE_PROJECT_ROOT and both stub overrides. Capture driver exits separately from shell-menu exit 0 and printed statuses (`scripts/tests/menu-input-test.py:243–250`) | New-app reaches stub agent with absent REQUIREMENTS.md; change ANALYZE exits 1 before agent; initial missing/empty change inputs exit 1; no live agent/network call | Hook timeline; driver exits; stub calls; network-isolation evidence | | BLOCKED-SETUP |
| MC-006 | P0 | REGRESSION | PLAN AC1/AC2/R1 | I-1/2/3/4 | Writable test environment; planned test file available | fixture:regression, host:verification | none | Run `python3 -B scripts/tests/menu-input-test.py -v`; execute BASELINE_REPORT.md §8 commands 1–3 and 6 verbatim | T1–T7 pass; no new baseline failures; BASELINE F1 failures identified separately, not counted as new | Exact commands/full output/exits; test-to-T1–T7 mapping, including race isolation | | BLOCKED-SETUP |
| MC-007 | P0 | PRESERVE, ROLLBACK | AR-5; PLAN AC3/P3/NC1/RB1 | I-1/2 | Implementation complete; PC1 snapshot and review access; writable rollback copy | fixture:rollback, host:verification | none | Compare final delta with PC1; verify only FC1–FC3 changed and P3 helpers preserved; in disposable copy revert C1–C4, rerun PLAN §17, compare inputs/state/prior edits | Protected paths and prior edits preserved; no persistence migration; rollback restores baseline behavior without losing inputs/state | Scoped diff; PC1 comparison; rollback commands/results and state comparison | | BLOCKED-SETUP |
| MC-008 | P0 | COMPATIBILITY | PLAN Q2/PC2/M1–M3 | I-1/2/3/4 | Native Windows environment and operator | terminal:windows, fixture:windows | none | On native Windows execute MC-001, MC-003 and MC-004 scenarios | Same specified menu, launch and legacy-notice behavior | Windows version; terminal; commands/recording; calls/args/cwd | | BLOCKED-IMPOSSIBLE |
| MC-009 | P0 | REGRESSION, MODIFY | PLAN NC1; IMPLEMENTATION_NOTES.md:IN-13/14 | — | Writable isolated checkout/config; PC1 snapshot | fixture:prior-edits, host:verification | none | Run `bash scripts/tests/plan-scope-test.sh` and `bash scripts/tests/shell-menu-startup-test.sh`; run `bash scripts/tests/checklist-runner-config-test.sh`. Source `scripts/lib/stage-config.sh` with isolated UNCLE_CONFIG; compare side/cmd/runner/model/effort/billing/network for manual-checklist-base/delta against manual-checklist and implementation-step-1 against implementation, using stage overrides, global fallbacks, absent config, aider alias, and conflicting alias-specific keys. Compare changed-file inventory including reports/untracked tests against PC1 status/diff/hashes and IN-5/6/13 | Empty scope assignment exits 0 under errexit/pipefail (`scripts/lib/plan-scope.sh:53`); startup preserves config without undefined-command failure (`uncle:616`); aliases use canonical settings and side (`scripts/lib/stage-config.sh:58`); every file outside FC1–FC3 accounted for as prior edit or declared artifact, unexplained deltas flagged | Commands/exits; config matrix; file dispositions and PC1 comparisons | | BLOCKED-SETUP |
| MC-010 | P0 | REGRESSION, MODIFY | PLAN NC1; CHANGE_TEST_REPORT.md:CT-18 | I-1 | Writable isolated checkout; stub reviewer; absolute temporary paths | fixture:background, host:verification | none | Adapt disposable `scripts/tests/background-performance-test.sh` harness to set PROJECT_ROOT to a spaced project path; invoke extracted actual start_codex_bg from another cwd; stub records cwd/args then sleeps. Run cancellation assertions; repeat with nonexistent PROJECT_ROOT, capturing background wait status and stub calls (`scripts/change-workflow.sh:1400,1440`) | Valid-root reviewer runs in project with existing args; cancellation exits 130 without orphan; invalid-root launch fails before reviewer; unset-root baseline failure remains separately identified | Harness; cwd/args; wait statuses; child-process evidence | | BLOCKED-SETUP |
| MC-011 | P1 | REGRESSION | CHANGE_TEST_REPORT.md:CT-10 | — | ShellCheck installed; PC1 comparison checkout | fixture:lint | none | Run `shellcheck uncle scripts/change-workflow.sh scripts/lib/plan-scope.sh scripts/lib/stage-config.sh scripts/tests/plan-scope-test.sh scripts/tests/checklist-runner-config-test.sh scripts/tests/shell-menu-startup-test.sh` on final and PC1 copies | No unexplained new diagnostics; existing diagnostics identified separately | Version; command; diagnostics/exits and comparison | | BLOCKED-SETUP |
| MC-012 | P0 | REGRESSION, COMPATIBILITY | CHANGE_TEST_REPORT.md:CT-19 | — | Writable isolated checkout; Python, Bash, jq, curses, Aider; loopback binding; native Windows for platform-only cases | fixture:python, host:verification, loopback:127.0.0.1:dynamic, fixture:windows | none | Run `bash -c 'for t in scripts/tests/*test.py; do python3 -B "$t"; rc=$?; printf "%s: exit %s\n" "$t" "$rc"; done'`; repeat windows-portability-test.py on native Windows; inventory every skip and provision its prerequisite before rerun. Retain self-hosted-live-test.py's local-only guard and record allocated port (`scripts/tests/self-hosted-live-test.py:16`) | Every standalone Python suite has an assessed result; platform-only tests execute natively; local Aider assertions hold without external calls; skips remain unresolved until executed | Per-file output/exits; skip dispositions; Windows evidence; endpoint/guard evidence | | BLOCKED-SETUP |
| MC-013 | P0 | REGRESSION | PLAN AC2; CHANGE_TEST_REPORT.md:CT-7/14/18 | — | Writable final and PC1 checkouts; `/private/tmp/uncle-implementation-start` logs; functioning Git identity/signing and shell file descriptors | fixture:full-suite, host:verification | none | In each checkout run `bash -c 'for t in scripts/tests/*-test.sh; do bash "$t"; rc=$?; printf "%s: exit %s\n" "$t" "$rc"; done'`; compare individual assertions and exits with full-results.json and rollback-results.json; rerun environment-blocked suites after correcting prerequisites | No new failures; all 11 reported failing suites individually attributed; matching exit codes alone do not establish matching failures; unresolved assertions remain acceptance gaps | Commands/environment; per-suite logs; assertion-level final/PC1 dispositions | | BLOCKED-SETUP |

## Assumptions

| ID | Unverified prerequisite | Settled by |
|---|---|---|
| A-1 | Current filesystem profile is read-only; fixture creation and test writes unavailable | Supply a writable disposable execution workspace for MC-001–007 and MC-009–013 |
| A-2 | BASELINE §8 establishes Bash/Python execution, not interactive terminal access or an operator | Provision interactive terminal; if waiting on an operator afterward, classify MC-001/004 BLOCKED-HUMAN |
| A-3 | Resolved fixture instructions remain unexecuted; restricted identity, tracing and network isolation are unverified | Provision MC-002/003/005 prerequisites and execute their actions |
| A-4 | Windows is unavailable in this macOS environment | Supply native Windows executor for MC-008/012 |
| A-5 | ShellCheck, Aider and loopback execution prerequisites are unverified | Provision and record versions/capabilities for MC-011/012 |

## Open questions

| ID | Gate decision |
|---|---|
| O-1 | PLAN PC2 requires native Windows M1–M3 before acceptance; MC-008 cannot verify that here. Human must change the environment or approve a revised verification strategy/criterion. |
| O-2 | Mandatory execution fields and coverage exceed the 4,000-byte budget; retained without dropping obligations. |

## acceptance-criteria traceability

| Criterion | Checks |
|---|---|
| AR-1/2 | MC-001/002/003/006 |
| AR-3 | MC-001/002/006 |
| AR-4 | MC-001/003 |
| AR-5 | MC-003/004/005/007/009 |
| AR-6 | MC-002/003 |
| PLAN AC1 | MC-001–006/008 |
| PLAN AC2 | MC-006/011/012/013 |
| PLAN AC3 | MC-007/009 |

## preserved-behavior coverage

| Behavior | Checks |
|---|---|
| B-3/4/5/6 | MC-002; MC-004; MC-005; MC-003 respectively |
| PLAN UB2 | MC-005 |
| Prior edits and fixture deviations, IMPLEMENTATION_NOTES.md:IN-12–14 | MC-003/005/007/009/010 |

## changed-behavior coverage

| Behavior | Checks |
|---|---|
| MODIFY B-1/2 | MC-001/002/003 |
| ADD B-3 | MC-002 |
| PLAN BD1/P6/P7/P8/P9/P10 | MC-001/003/004 |
| Diff beyond FC1–FC3: plan parser, stage aliases, background cwd | MC-007/009/010 |

## invariant coverage

| Invariant | Checks |
|---|---|
| I-1/2 | MC-003/010 |
| I-3 | MC-001/002/005 |
| I-4 | MC-002/003; outside-root symlink exception per PLAN Q1 |

## regression coverage

| Area | Checks |
|---|---|
| Notice navigation, retry, restart | MC-001/004 |
| CLI, root, issue ordering, shell EOF | MC-003 |
| Driver guards and accepted deletion race | MC-005 |
| Timing/performance and existing suites | MC-006; BASELINE §8 command 2 includes timing suite |
| Protected scope, rollback, prior edits | MC-007/009/010 |
| Native Windows and terminal rendering beyond automated assertions | MC-008/012; MC-001/004 |
| CT-10 NOT RUN linting | MC-011 |
| CT-19 NOT RUN shell stat denial and standalone Python suites | MC-002/012 |
| CT-7/14/18 unresolved full-suite failures | MC-010/013 |

## removed checks

| Check ID | Reason |
|---|---|
| None | No base check is provably inapplicable. |