# Change plan: Supervision tooltips

Issue 81

Seeded from [unclehq/uncle#81](https://github.com/unclehq/uncle/issues/81).

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (single-threaded UI); Feature flag (none, UI-only)

## 1. Selected technical approach

All in `uncle_tui.py`, text next to `SUPERVISION_DESC`:

- D-1: add `SUPERVISION_HINT` (one short phrase per CONTROLS key, <=40 chars excluding the `  - ` separator; authoring limit enforced by a test, never truncated at runtime) and `SUPERVISION_CHOICE_DESC` mapping `(key, value)` to a short explanation (effort none/low/medium/high; delegate_gates none/routine). Runner explanations: the runner value set is enumerated from the same list `_picker_rows` uses for the runner picker (tests iterate that list, not a hardcoded copy); each runner gets an entry where known, otherwise a fixed non-empty generic fallback string (a module constant). All hint and explanation text comes only from these static dict entries or the fixed fallback; user-supplied values (e.g. runner names) are never interpolated into them. Tests assert every runner in that list yields a non-empty explanation.
- D-2: `_supervision_items()` appends `  - <hint>` after the value iff the full stdscr width `self.stdscr.getmaxyx()[1] >= 100` (not the menu-panel width). Hints are absent at width 99 and below, and absent if getmaxyx raises or returns a non-positive or non-integer width. Rows keep key prefix. Hints are authored at <=40 chars excluding the separator and are never truncated at runtime; a test asserts len(hint)<=40 for every hint. Key and value are never truncated by the hint logic (the window may clip the row at draw time). Rows beginning with `!` (invalid-config reason rows) and non-CONTROLS rows get no hint; every CONTROLS row has a non-empty hint at width >=100. At width >=100 hints are always rendered; if the side description panel does not fit, `_draw_config_desc` uses its existing bottom-strip fallback and the inline hints stay. No caller parses row text: selection, Enter and toggle act on the row index/key, so Enter/toggle on a hinted row must act on the correct key (asserted by a test).
- D-3: add picker_kind `delegate` in `_picker_rows` returning `option` rows none/routine only (no Custom row, like `network`); extend `_picker_current` and `_title` for it. none and routine are the only selectable values. The current value is marked on the matching row; a stored delegate_gates value outside none/routine is shown as the current value via a fallback current row (no explanation, no none/routine row highlighted), is left unchanged unless the user selects none/routine, and Esc leaves it unchanged. The old free-text Custom entry is no longer reachable for delegate_gates; supervision_lib validation remains the only write gate. Verify the apply path by reading the Enter handler (step 3) so that selection calls the same `_set_field("!supervision", key, value)`.
- D-4: `_supervision_enter` opens the `delegate` picker for `delegate_gates` regardless of the stored value, including an out-of-set one (other non-bool kinds unchanged). The picker lists only none/routine; free-text Custom entry for delegate_gates is intentionally replaced by it, and supervision_lib validation remains the only write gate. Test: with a stored value outside none/routine, the picker opens with no row marked current, Esc leaves the stored value unchanged, and selecting routine stores routine.
- D-5: `_draw_picker` appends `  - <explanation>` only to option rows, and only when `picker_target == "!supervision"` and the row's (key, value) has an entry in `SUPERVISION_CHOICE_DESC` (or the fixed non-empty runner fallback for runner values). Custom, filter, model, current-fallback and empty-list rows, and rows with no entry, are never annotated. No width gate applies to pickers: explanations are drawn at every width and truncated only by the existing `addnstr` width limit; non-supervision pickers are unchanged. Explanation text comes only from static `SUPERVISION_CHOICE_DESC` entries or the fixed fallback (never interpolating user values), and any drawn user-supplied value (such as a runner name) has control characters stripped before `addnstr`.
- D-6: hint eligibility — `_supervision_items()` appends a hint only to rows whose key is in CONTROLS and that have a SUPERVISION_HINT entry; invalid-config rows (beginning with "!"), non-CONTROLS rows, and rows with a missing hint get no hint, whatever the value (empty, bool or long).

## 2. Alternatives
(a) Separate tooltip popup on a key: more input handling, hidden until pressed. (b) Show all descriptions in an expanded panel: no room for 13 long entries. (c) Reuse long `SUPERVISION_DESC` inline: too long for one line.

## 3. Why preferred
Smallest change, no new state or keys, reuses existing draw fallbacks, hints visible at a glance.

## 4. Components to modify
See Change-impact table.

## 5. Not to modify

`scripts/lib/supervisor.py`, stage config menus' text, `CONFIG_DESC`, README, `.uncle/config.example` (unless a drift test fails), existing tests.

Non-goal / invariant: hint and explanation text comes only from static dict entries or a fixed fallback constant; user-supplied values (e.g. runner names) are never interpolated into it, and drawn user values have control characters stripped.

## 6-8. Data flow / interfaces
Pure-display additions. `items()` rows get a hint suffix (width-conditional); `_picker_rows` gains a `delegate` kind. No external API changes.

## 10. Compatibility

Row prefix, stored values and non-supervision pickers unchanged. MODIFY (declared): delegate_gates Enter changes from free-text Custom entry to a none/routine picker; an out-of-set stored value is shown unchanged with no row selected and Esc leaves it unchanged; supervision_lib validation remains the only write gate.

## 12. Error and recovery
Missing hint/description -> nothing appended. Width read failure -> no hints.

## 14. Rollback plan
Revert the commit; no persisted data or schema involved.

## 16. Automated-test strategy

New `scripts/tests/supervision-tooltips-test.py` (hyphenated; leaves protected existing test files untouched). Builds `UncleTUI.__new__` as supervisor-test.py:1038 does, with a fake stdscr that records `addnstr` text. Cases: hint coverage per CONTROLS key (SI-1) and len(hint)<=40 for every hint; '!' reason rows get no hint; row prefix; Enter/toggle on a hinted row at width 120 acts on the correct key (same key and effect as with no hints); width cut-off; effort/delegate/runner picker explanations observed via the recording stdscr, drawn at width >= 120; picker Custom, filter and model rows, and rows without a dict entry, are asserted to have no explanation; delegate selection stores value; small-size draw without exception. Oracle for 'non-supervision picker rows unchanged': the pre-change `_picker_rows` output for each non-supervision picker kind is captured now as literal expected lists in the test (not recomputed from code), and the drawn picker text for a non-supervision target must contain no explanation. Defect injection (record all in IMPLEMENTATION_NOTES.md, each must make the suite fail, then be reverted): (1) blank one hint key; (2) add an explanation to a non-supervision picker row or draw it when picker_target != '!supervision'; (3) put a supervision hint in the wrong picker/key.

Additional required cases: Enter/toggle on each hinted row index at width 120 calls the handler with the matching CONTROLS key; a runner name containing control characters yields the static fallback explanation and drawn text has no control characters; delegate picker with out-of-set stored value highlights no row, offers only none/routine, and Esc leaves the value unchanged.

## 17. Regression-test strategy
Baseline commands in BASELINE_REPORT (shell suites, python critical tier) plus explicit `supervisor`, `supervisor-default-runner`, `supervision-tooltips` and `py_compile`.

## 18. Manual verification
Run `uncle` -> Configure -> Supervision at ~120 cols and ~60 cols: see per-row hints, highlight description, open effort/delegate_gates/runner pickers and read explanations; Esc backs out.

## 20. Implementation sequence

1. Text tables: add `SUPERVISION_HINT` and `SUPERVISION_CHOICE_DESC` beside `SUPERVISION_DESC`
   Owns: `uncle_tui.py`
2. Row hints in `_supervision_items` (D-2): hints at width >=100 only, no truncation of key/value, strip fallback for the side panel; tests cover widths 99, 100, 119 and 120; confirm by reading Enter/toggle handlers that no caller parses row text - builds on step 1's edits to uncle_tui.py (same file, text dependency)
   Owns: `uncle_tui.py`
   Depends on: 1
3. Picker work: `delegate` kind in `_picker_rows`/`_picker_current`/`_title`, `_supervision_enter`, `_draw_picker` explanations (D-3..D-6). First read the picker Enter handler and `_picker_current`'s out-of-set fallback; these are named touched functions, and any change to either is recorded in IMPLEMENTATION_NOTES.md. Out-of-set stored delegate_gates highlights no row, only none/routine are selectable, Esc leaves the value unchanged — builds on same file
   Owns: `uncle_tui.py`
   Depends on: 1
4. Tests: `scripts/tests/supervision-tooltips-test.py` written against the specified behavior. Deliverables: literal expected lists of pre-change non-supervision `_picker_rows` output; hint non-empty/len<=40/unmodified-in-row test; '!' and non-CONTROLS rows unhinted; width 99/100/raising getmaxyx; Enter/toggle on every hinted row index at width 120 targets the matching CONTROLS key; runner set enumerated from the list `_picker_rows` uses; runner name with control characters yields the static fallback and no control characters in drawn text; delegate out-of-set stored value case
   Owns: `scripts/tests/supervision-tooltips-test.py`
   Depends on: 2, 3
5. Reconcile and run commands. Perform defect injection as temporary reversible edits to uncle_tui.py only (blank hint; explanation leaked into non-supervision picker; hint in wrong key), confirm the suite fails each time, revert, and record results in IMPLEMENTATION_NOTES.md. Record any invoked scope cut there; if the runner-explanation cut is invoked, amend AC-2 and remove the runner test from step 4's file in this same step.
   Owns: `uncle_tui.py`, `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 2, 3, 4

## 21. Scope cuts under time pressure

Cut first: runner-choice explanations (if invoked, AC-2 is amended in the plan and deviation notes to exclude the runner picker), then width-conditional hints (keep picker explanations for effort/delegate_gates), never cut SI-1 coverage test.

## 22. Risks
| Risk | Mitigation |
|---|---|
| Longer rows shrink the side panel | 40-char cap, width>=100 gate, existing strip fallback |
| Shared `_draw_picker` regression | Gate on `picker_target == '!supervision'`; test non-supervision rows |
| Unknown delegate selection path | Step 3 reads handler; no stop condition unless apply path cannot call `_set_field` |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Proposal | AC-5 | Single text source in SUPERVISION_* dicts | Dicts beside SUPERVISION_DESC (DESIGN: location revisable) | Keeps menu/picker consistent | CAP-python3 | CODING |
| R-2 | REPOSITORY | supervisor-test.py:1214 | AC-1 | Rows start with key; no caller parses row text, so Enter/toggle on a hinted row act on the correct key; every CONTROLS row has a hint at width >=100; hint length <=40 asserted by test | Append hint after value; hints authored <=40 chars, never truncated at render; '!' rows get no hint; Enter/toggle test on hinted rows | Existing test | CAP-python3 | CODING |
| R-3 | USER | CHANGE_REQUEST.md AC3 | AC-3 | Graceful narrow terminal; hints iff width >= 100 | Width gate (stdscr.getmaxyx()[1] >= 100; boundary tests at 99 and 100) + existing fallback | Spec | CAP-python3 | CODING |
| R-4 | REPOSITORY | CLAUDE.md | AC-4 | Existing tests not edited; unchanged-picker baseline fixed as literals and tests proven to reject leaked explanations | New test file with literal expected non-supervision picker rows and multiple defect injections | Protected paths | CAP-python3 | CODING |

Feasibility: symbols inspected at the lines in the baseline; python3 and bash runners exist (scripts/run-python-tests.sh). No live-authentication prerequisites; LIVE_VERIFICATION is the manual check above.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` | Add hint/choice dicts, row hints, `delegate` picker, picker explanations | Feature | Shared picker/draw code | supervision-tooltips-test, supervisor-test |
| `scripts/tests/supervision-tooltips-test.py` | New suite | Cover AC-1..5 | None | Self + defect injection |
| `.uncle/docs/IMPLEMENTATION_NOTES.md` | Record deviations/defect injection | Workflow | None | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| At width >=100 every CONTROLS row shows a non-empty hint (<=40 chars, authored not truncated) after the value; '!' reason rows get no hint. | SB-1 | SI-1 | _supervision_items | tooltips-test row hints, tooltips-test hint len<=40 authored limit, no runtime truncation, tooltips-test: '!' reason rows and non-CONTROLS rows get no hint | Menu at 120 cols |
| AC-2: effort, delegate_gates and runner pickers show a non-empty explanation for each option row, observed as addnstr text recorded by a fake stdscr at width >=120. delegate_gates offers only none/routine; an unrecognised stored value highlights no row and Esc leaves it unchanged. The runner set is the list `_picker_rows` uses, with a non-empty fixed fallback explanation for unlisted runners. Hints are authored <=40 chars and never truncated at render. Custom, filter, unmapped and '!' rows get no explanation. | SB-3, SB-4, SB-5 | SI-2 | _picker_rows, _draw_picker | tooltips-test pickers (fake stdscr recording addnstr text at width 120; explanation non-empty per option row with an entry), tooltips-test: Custom/filter rows unannotated; delegate out-of-set stored value shown as current and editable, tooltips-test delegate picker with out-of-set stored value: no row current, Esc leaves value unchanged | Open each picker |
| AC-3 | SB-2, SB-7 | SI-3 | _supervision_items, _draw_config_desc | tooltips-test narrow draw at widths 30 and 60, tooltips-test width boundary: hints absent at 99, present at 100, present at 120, absent when getmaxyx raises or width <= 0 | Menu at 60 cols, Menu at 99 and 100 cols |
| AC-4 | SB-6 | SI-2 | pickers | supervisor, shell suites, tooltips-test literal non-supervision picker rows + defect injection (explanation leaked into non-supervision picker) | Stage config picker |
| AC-5 | SB-1 | SI-1, SI-4 | dicts | key-set test, DocsTests | n/a |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Plan did not define how hinted rows coexist with the side panel or strip fallback. | D-2 (s1.2.i2) now states hints always render at width>=100 and the description uses the bottom strip when the panel does not fit. |
| AR-002 | Accepted | The 40-char cap was ambiguous between truncation and authoring limit. | D-2 and AC-1 now say hints are authored <=40 chars excluding separator, never truncated at runtime, and a test asserts length. |
| AR-003 | Accepted | Hint eligibility for invalid-config, non-CONTROLS and empty/long-value rows was unspecified. | Add D-6 to s1.2 and update AC-1 requirement/tests: only CONTROLS-key rows get hints; '!' rows and non-CONTROLS rows get none. |
| AR-004 | Accepted | Explanation scope for Custom/filter/missing-entry rows and the delegate out-of-set stored value were unspecified. | Edit D-3 and D-5 in s1.2 and AC-2 tests: explanations only on option rows with an entry; delegate stored out-of-set value handled via fallback current row. |
| AR-005 | Accepted | Picker width handling was ambiguous; stating that pickers have no width gate and are tested at width >=120 removes the ambiguity. | D-5 states explanations are shown at all widths with no width gate and truncated by addnstr; AC-2 test observes them at width 120. |
| AR-006 | Accepted | The boundary was untested and the gate was not pinned to stdscr width. | D-2 now says hints appear iff stdscr.getmaxyx()[1] >= 100 (absent at 99, on exception or width <=0); AC-3 and R-3 add boundary tests at 99 and 100. |
| AR-007 | Accepted | The delegate picker has no Custom row, so handling of out-of-set stored values must be explicit. | D-3 and D-4 state the picker lists only none/routine, shows an out-of-set value as current, and Esc leaves it unchanged. |
| AR-008 | Accepted | Behavior at widths 100-119 versus the side panel needs a stated rule. | D-2 states hints always show at width >=100, the side panel falls back to the strip if it does not fit, and key/value are never truncated. |
| AR-009 | Accepted | D-5 did not say which picker rows get explanations; limiting to dict-backed option rows protects Custom, filter and model rows (SB-6). | Edit D-5 (s1.2.i5) to annotate only option rows with a SUPERVISION_CHOICE_DESC entry, and add a test case in section 16. |
| AR-010 | Accepted | Appending hints could break callers parsing row text; the plan must state none do and test Enter/toggle on hinted rows. | Edit D-2 (s1.2.i2) with a no-parse rule, add Enter/toggle test to section 16 and R-2, and extend step-2. |
| AR-011 | Accepted | The cap meaning was ambiguous; authoring-time limit excluding separator, test-enforced, is simplest and avoids runtime truncation. | D-1 and D-2 (s1.2.i1, s1.2.i2) now state hints are <=40 chars excluding the '  - ' separator, enforced by test, never truncated at runtime. |
| AR-012 | Accepted | Static-only text and control-character stripping of drawn values prevents injection of terminal escapes from user-supplied runner names. | D-1 and D-5 (s1.2.i1, s1.2.i5) now state text comes only from static dicts or a fixed non-empty fallback, no user value is interpolated, and drawn values have control characters stripped. |
| AR-013 | Accepted | Real gap: delegate picker has no Custom row, so out-of-set stored values need a stated handling. | D-3 (s1.2.i3) states out-of-set values show unchanged with no current selection; validation in supervision_lib stays the only write gate. |
| AR-014 | Accepted | Gate boundary and width source were ambiguous; pinning to stdscr width with 99/100 tests removes the split. | D-2 (s1.2.i2) states hints appear iff stdscr.getmaxyx()[1] >= 100; AC-3 and test rows cover widths 30, 60, 99, 100, 120. |
| AR-015 | Accepted | Cap enforcement and treatment of '!' reason rows were unspecified; authoring-time limit plus a test resolves it. | D-2 now says hints are authored <=40 chars, never truncated at render, '!' rows get no hint; s10 and R-2 add a length test. |
| AR-016 | Accepted | Observation method for picker explanations was undefined. | D-5 and s10 specify a fake stdscr recording addnstr text at width >=120; Custom, filter and unmapped rows get no explanation. |
| AR-017 | Accepted | Runner set and fallback text must be pinned so tests can assert non-empty explanations; the cut-first item contradicted AC-2. | D-1 pins runner set to _picker_rows list and non-empty fallback; section 21 cut amends AC-2; AC-2 requirement updated. |
| AR-018 | Accepted | Delegate picker behavior for current and out-of-set stored values needs a defined expected result. | D-3 and D-4 state none/routine are the only selectable values, unrecognised stored value highlights no row, Esc leaves it unchanged. |
| AR-019 | Accepted | Fixed literal oracles for unchanged pickers and extra defect injections are cheap and prove the tests reject leaked explanations. | Section 16 test strategy and R-4/AC-4 now require literal expected non-supervision picker rows and a second defect injection. |
