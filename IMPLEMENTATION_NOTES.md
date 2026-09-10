## files changed
| ID | File | Purpose | Approved-plan step | Behavior or invariant affected |
|---|---|---|---|---|
| IN-1 | uncle_tui.py:__init__,_confirm,handle_key,_title,_draw_notice | Stat selected input; clear blocked selection; reset notice title/destination on dismissal | S2/C1/C2 | B-1/B-2, I-3/I-4, AR-4; legacy Configure destination |
| IN-3 | uncle:menu case dispatch | Gate choices 1/3 with project-root -f; warn and continue | S2/C3 | P2/P9/P10 |
| IN-4 | scripts/tests/menu-input-test.py:MenuInputTests | Extend existing regression scaffold with file types, auto mode, actual-driver races | S1/S3/C4 | T1–T7; eight passing tests |
| IN-5 | IMPLEMENTATION_NOTES.md | Replace prior blocker report with implementation evidence | S3 | Scope accounting |
| IN-6 | CHANGE_TEST_REPORT.md | Replace prior report with executed checks and remaining acceptance gaps | S3 | AC1/AC2 |

## purpose of each change
See IN-1, IN-3–IN-6; CHANGE_PLAN.md remains authoritative.

## approved-plan step
| ID | Evidence |
|---|---|
| IN-7 | S1: `python3 -B scripts/tests/menu-input-test.py -q` confirmed 11 failures before production edits. |
| IN-8 | S2: C1–C3 implemented; S3 automated menu checks pass; manual/native acceptance incomplete. |

## behavior or invariant affected
| ID | Evidence |
|---|---|
| IN-9 | `MenuInputTests.test_selection_race_actual_drivers` executes copied actual drivers for both menus: new-app stub exits 73; change ANALYZE exits 1 before agent invocation. |
| IN-10 | PC1 snapshot `/private/tmp/uncle-implementation-start/{status,diff,hashes.json}` records prior work; hash comparison confirms protected files unchanged. |
| IN-11 | Python symbol comparison against HEAD confirms uncle run helpers and uncle_tui.py:_project_root,cmd_for,start_workflow unchanged. |

## deviations
| ID | Disposition |
|---|---|
| IN-12 | C4 stub now changes to UNCLE_PROJECT_ROOT like actual drivers; paths resolved for macOS /var alias. Shell race asserts the driver's printed exit status because uncle:launch returns to its menu. No expected production behavior changed. |
| IN-13 | PC1 existing edits preserved: ADVERSARIAL_REVIEW.md, CHANGE_PLAN.md, scripts/change-workflow.sh, scripts/lib/{plan-scope,stage-config}.sh, scripts/tests/plan-scope-test.sh, uncle; existing untracked checklist-runner-config-test.sh and shell-menu-startup-test.sh preserved. C4 and both requested reports were already uncommitted. |
| IN-14 | Prior removal of uncle's undefined apply_config call is preserved; the S1 shell fixture now reaches dispatch. |

## unresolved concerns
| ID | Concern | Settled by |
|---|---|---|
| IN-15 | Q2 and manual M1–M3 unverified; automated 80×24 rendering uses mocked curses | Native Windows and interactive terminal checks before AC1 acceptance |
| IN-16 | Shell permission-denial behavior unverified; TUI PermissionError covered | Run shell fixture under a restricted identity |
| IN-17 | Full-suite failures and rollback comparison recorded in CHANGE_TEST_REPORT.md | Resolve environment/test failures outside FS1 |
