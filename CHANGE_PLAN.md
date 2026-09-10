# Change Plan
| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Selection-time scope retained; new-app driver lacks the claimed fallback (ADVERSARIAL_REVIEW.md:AR-001). | §4 C4; §11 P11; §16 T7; appended scope, acceptance and checks |
Omitted sections: none

## 1. Selected technical approach
Plan P1: Gate both menus; stat only.
Plan P2: Empty passes (AU2/spec §15); directories/stat errors fail.

## 2. Alternative approaches considered
| ID | Rejected approach | Reason |
|---|---|---|
| A1 | Gate `_run()` | Intercepts issue seeding |
| A2 | Require nonempty | Violates spec §15 |

## 3. Why the selected approach is preferred
P1 preserves issue ordering (`uncle_tui.py:_confirm`).

## 4. Exact components to modify
Tests in C4.

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| C1 `uncle_tui.py:_confirm` | Guard `_run` | I-3/4 | Wrong root/mode | T1,T2,T5 |
| C2 `uncle_tui.py:__init__,handle_key,_title,_draw_notice` | Notice destination/title | AR-4; B-4 | First-run notice | T3,T4 |
| C3 `uncle:640` menu dispatch | Guard choices 1/3 via `-f "$PROJECT_ROOT/..."`; warn then continue | Menu parity | Shell exits | T6 |
| C4 `scripts/tests/menu-input-test.py` | Menu fixtures | Acceptance | Fixture drift | T1–T7 |

## 5. Components explicitly not to modify
Plan P3: Preserve `uncle` run helpers; TUI `_project_root,cmd_for,start_workflow`; drivers, config, packaging, existing tests and baseline F2 edits.

## 6. Data-flow changes
Plan P5: Selection → fixed filename at project root → stat → warning/launch.

## 7. State-transition changes
Plan P6: Missing → notice; clear selection/workflow; dismissal → menu; reselect rechecks.
Plan P7: Reset notice metadata; default Configure.

## 8. Interface and API changes
Plan P8: Title “Required input”; “[filename] is needed”; footer targets menu.
Plan P9: Shell warns; no extra read/flag change.

## 9. Schema or persistence changes
None.

## 10. Compatibility strategy
Plan P10: Gate auto/unattended menus, not drivers (AU3; `uncle:usage`).

## 11. Concurrency implications
Plan P11: Interpret I-3 at menu selection; no locks/recheck. Accept deletion after stat: new-app may launch an agent without REQUIREMENTS.md (`scripts/stagegate.sh:1096,1264`; `scripts/lib/early-prerequisites.py:13`). Change ANALYZE retains its guard (`scripts/change-workflow.sh:1523`).

## 12. Error and recovery behavior
Plan P12: `OSError`/false stat blocks before `_run`; create file and retry.

## 13. Migration plan
None.

## 14. Rollback plan
Plan RB1: Revert C1–C4; rerun §17; preserve inputs/state/prior edits.

## 15. Feature-flag or containment strategy
Plan P13: No flag; menus only.

## 16. Automated-test strategy
Plan: `python3 -B scripts/tests/menu-input-test.py -v`; mock launches; shell uses copied launcher/stub drivers/config.
IDs: `CHANGE_SPEC.md`.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AR-1 | B-1 | I-3/4 | C1,C3 | T1 new blocked | M1 |
| AR-2 | B-2 | I-3/4 | C1,C3 | T1 change blocked | M1 |
| AR-3 | B-3 | I-3 | C1,C3 | T2 alone/both/empty | M2 |
| AR-4 | §9 | I-3 | C2 | T3 Esc/Enter/other key; retry | M1 |
| AR-5 | B-4/5 | — | C2,C3 | T4 legacy notice; T6 args | M3 |
| AR-6 | B-6 | I-1/2/4 | C1,C3 | T5 cwd/root; issue order | M2 |

Plan T1: Directories/broken links/stat denial; missing fails before/passes after (baseline T4).
Plan T6: Shell retry/EOF/auto/spaced root; assert calls/args/cwd; T5: Popen cwd.

| ID | Planned race test |
|---|---|
| T7 | In C4, delete input after successful menu stat, before launch, for both menus/modes. Run actual drivers in disposable projects with stub agent executables; assert new-app reaches agent with REQUIREMENTS.md absent and change ANALYZE exits 1 before agent. No live agents. |

## 17. Regression-test strategy
Plan R1: Baseline §8 commands 1–3,6; no new failures; report F1.
Plan R2: Diff driver guard/helpers.

## 18. Manual-verification strategy
| ID | Planned check |
|---|---|
| M1 | Temp project: missing modes; 80×24 popup; dismiss/create/retry |
| M2 | Stub drivers: cwd/issue order; TUI/piped shell/auto mode |
| M3 | No reader: original notice → Configure |

## 19. Observability changes
Plan O1: Warning only.

## 20. Implementation sequence
| ID | Planned step |
|---|---|
| S1 | Add C4; record T1 failure |
| S2 | Implement C1/C2 and C3 |
| S3 | Run §16–18; inspect P3 diff |

## 21. Scope cuts under time pressure
Plan SC1: Defer F1 repairs; retain acceptance checks.

## 22. Risks and unresolved questions
| ID | Disposition |
|---|---|
| Q1 | RESOLVED by human: accept symlinks to regular files as present, including targets outside the project directory. |
| Q2 | UNRESOLVED: Windows; run native M1–M3 |

## Frozen change scope
| ID | Plan boundary |
|---|---|
| FS1 | C1–C4 only; enforce selection-time I-3 per P11; no driver guard or atomicity guarantee. |

## Files expected to change
| ID | Planned file |
|---|---|
| FC1 | `uncle_tui.py` (C1/C2) |
| FC2 | `uncle` (C3) |
| FC3 | `scripts/tests/menu-input-test.py` (C4) |

## Files that must not change
| ID | Protected scope |
|---|---|
| NC1 | All files outside FC1–FC3, including `scripts/stagegate.sh`, `scripts/change-workflow.sh`, `scripts/lib/early-prerequisites.py`; preserve P3 symbols and prior edits. |

## Expected behavioral differences
| ID | Planned difference |
|---|---|
| BD1 | `CHANGE_SPEC.md` B-1/B-2 and AR-4, verified by T1/T3/T6. |

## Expected unchanged behavior
| ID | Planned preservation |
|---|---|
| UB1 | `CHANGE_SPEC.md` B-3–B-6, I-1/I-2/I-4, verified by §16–18. |
| UB2 | P11 driver race outcomes, verified by T7. |

## Exact acceptance criteria
| ID | Planned acceptance |
|---|---|
| AC1 | Pass §16 AR-1–AR-6 rows, T1–T7 and §18 M1–M3; apply P2/P10/P11 to spec ambiguities. |
| AC2 | §17: no new failures; report existing F1 separately. |
| AC3 | Diff confined to FC1–FC3 and P3 preserved. |

## Pre-implementation checks
| ID | Planned check |
|---|---|
| PC1 | Record `git diff` and `git status --short` to protect prior edits. |
| PC2 | Resolve Q1 before implementation; resolve Q2 with native M1–M3 before acceptance. |
| PC3 | Confirm T7 fixtures execute actual drivers with stub agents and no live network calls. |

## Post-implementation checks
| ID | Planned check |
|---|---|
| PO1 | Execute §16–18, including T7; inspect final diff against PC1 and AC3. |

## First features to cut if time expires
| ID | Planned cut |
|---|---|
| CUT1 | SC1 only; no acceptance checks or T7 cuts. |

## Conditions that require stopping implementation
| ID | Stop condition |
|---|---|
| STOP1 | Required edits exceed FS1/NC1, Q1 remains unresolved, or T7 cannot isolate agents: stop for scope/fixture resolution. |
| STOP2 | T7 contradicts P11: stop and revisit AR-001 before acceptance. |
