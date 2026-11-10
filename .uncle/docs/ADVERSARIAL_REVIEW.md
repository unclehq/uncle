## AR-001: Width gate vs.

- Severity: HIGH
- References: CHANGE_PLAN D-2 and Risks table; CHANGE_SPEC SB-2/SB-7. Settle with: 'At width>=100 hints are always rendered; if the side panel does not fit, the description uses the bottom strip and hints stay.'
- Failure: Width gate vs. hint cap vs. side panel collide: hints appear at width>=100 but the plan doesn't say how rows with hints coexist with the side description panel, or whether the strip fallback hides inline hints. 'Existing strip fallback' is not defined for the hinted-row case.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: AC-1 says every row has a hint after the value at 120 cols, but D-2 says hint is capped at 40 chars and rows may be trun

- Severity: HIGH
- References: CHANGE_SPEC AC-1/SB-1 vs CHANGE_PLAN D-2 ('capped at 40 chars'). State: 'Hints are authored at <=40 chars, never truncated at runtime; a test asserts len<=40.'
- Failure: AC-1 says every row has a hint after the value at 120 cols, but D-2 says hint is capped at 40 chars and rows may be truncated by the window; the plan doesn't say whether row text (key+value+hint) is itself truncated, or whether 'cap' means truncation with ellipsis or a authoring limit.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Invalid-config rows ('!

- Severity: MEDIUM
- References: CHANGE_SPEC section 8 vs SB-1 ('each row'). State: 'Rows beginning with "!" and non-CONTROLS rows get no hint.'
- Failure: Invalid-config rows ('! reason'), bool rows and rows whose value is empty/very long are not specified for hint rendering; spec says '! reason unchanged' but not whether a hint is appended to them.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Picker explanation behavior is unspecified for the Custom row, the current-value marker, filtered/empty picker lists, an

- Severity: MEDIUM
- References: CHANGE_PLAN D-3/D-5 ('option rows only'), SB-4 vs 'Custom' behaviors in SB-6. State: 'Custom and non-option rows get no explanation; a stored delegate_gates value outside none/routine is shown as current via a fallback row and Enter keeps it editable.'
- Failure: Picker explanation behavior is unspecified for the Custom row, the current-value marker, filtered/empty picker lists, and for runner values with no entry; also the delegate picker has no Custom row so a previously stored custom delegate_gates value has no stated handling.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Picker explanation width handling is ambiguous: truncation by addnstr is stated for D-5, yet AC-2 requires a non-empty e

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 vs CHANGE_SPEC AC-2/AC-3. State: 'Picker explanations are shown at all widths and truncated by window width; no width gate applies to pickers.'
- Failure: Picker explanation width handling is ambiguous: truncation by addnstr is stated for D-5, yet AC-2 requires a non-empty explanation per choice, and on narrow terminals the explanation could be cut to nothing; AC-3 covers only the menu hints.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Width read failure rule: getmaxyx exceptions yield no hints, but behavior for a fake/zero width or exactly 100 is only p

- Severity: LOW
- References: CHANGE_PLAN D-2 (>=100) vs AC-3 widths 30/60/120. State: 'Hints show at width 100 and above and are absent at 99; add boundary test at 99 and 100.'
- Failure: Width read failure rule: getmaxyx exceptions yield no hints, but behavior for a fake/zero width or exactly 100 is only partly stated, and the test widths (30, 60, 120) don't cover the boundary.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: delegate_gates Enter changes from free-text Custom to a none/routine picker with no Custom row; the plan doesn't say how

- Severity: HIGH
- References: CHANGE_PLAN D-3/D-4 'no Custom row, like network'; CHANGE_SPEC SB-4 currently 'Free-text Custom row only'.
- Failure: delegate_gates Enter changes from free-text Custom to a none/routine picker with no Custom row; the plan doesn't say how out-of-set stored values are shown or re-entered. Settle: 'The delegate picker lists only none and routine; a stored value outside that set shows as current, and Esc leaves it unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The width gate (>=100 total cols) is in tension with side-panel room, and behavior at 100-119 is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 vs SB-7; AC-1 tests only width 120.
- Failure: The width gate (>=100 total cols) is in tension with side-panel room, and behavior at 100-119 is unspecified. Settle: 'At width >=100 hints show; the side panel falls back to the strip when it doesn't fit; key and value are never truncated.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Picker explanations are gated on picker_target=='!supervision', but it's unstated which rows get them (Custom, model, fi

- Severity: MEDIUM
- References: CHANGE_PLAN D-5; CHANGE_SPEC SB-6 requires filter and Custom entry unchanged.
- Failure: Picker explanations are gated on picker_target=='!supervision', but it's unstated which rows get them (Custom, model, filtered, rows without a description). Settle: 'Explanations are appended only to option rows with an entry in SUPERVISION_CHOICE_DESC; Custom, filter and model rows are never annotated.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Appending hints to _supervision_items rows could break any caller that parses row text (selection, Enter, toggle).

- Severity: MEDIUM
- References: CHANGE_PLAN D-2/R-2 cite only supervisor-test.py:1214; section 16 has no test for Enter/toggle on hinted rows.
- Failure: Appending hints to _supervision_items rows could break any caller that parses row text (selection, Enter, toggle). The plan checks only the key prefix. Settle: 'No caller parses row text; Enter/toggle on a hinted row acts on the correct key, and a test asserts this.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The 40-char hint cap is ambiguous: it's unclear whether it includes the '  - ' separator or whether overlong hints get t

- Severity: LOW
- References: CHANGE_PLAN D-1/D-2 vs CHANGE_SPEC SB-1.
- Failure: The 40-char hint cap is ambiguous: it's unclear whether it includes the '  - ' separator or whether overlong hints get truncated. Settle: 'Each hint is <=40 chars excluding the separator, enforced by test, with no runtime truncation.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Runner explanations use a generic fallback, but the plan doesn't say whether user-supplied runner names are interpolated

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 'runner values with a generic fallback string'; D-5 appends explanations to option rows.
- Failure: Runner explanations use a generic fallback, but the plan doesn't say whether user-supplied runner names are interpolated or sanitized before addnstr. Settle with: 'Hint and explanation text comes only from static dict entries or the fixed fallback; user values are never interpolated, and drawn values have control characters stripped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The delegate picker has no Custom row, but delegate_gates took free text before (SB-4).

- Severity: LOW
- References: CHANGE_PLAN D-3 'no Custom row'; CHANGE_SPEC SB-4, SI-2.
- Failure: The delegate picker has no Custom row, but delegate_gates took free text before (SB-4). A stored out-of-set value is unspecified. Settle with: 'Delegate picker offers only none/routine; an out-of-set stored value shows unchanged in the row with no current selection; supervision_lib validation stays the only write gate.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The hint width gate is ambiguous at the boundary.

- Severity: HIGH
- References: CHANGE_PLAN D-2 (width >= 100 via stdscr.getmaxyx()); CHANGE_SPEC AC-3 tests widths 30, 60 and 120 only. Settle it with: 'Hints appear iff stdscr.getmaxyx()[1] >= 100; the tests must cover widths 99 and 100.'
- Failure: The hint width gate is ambiguous at the boundary. The plan says terminal width >= 100 but never says whether this is the full terminal width or the menu panel width. It also does not say what happens at widths 61-99, which AC-3 never tests (it tests 30, 60 and 120). Tests and code could split on exactly 99/100 and on whether the width is stdscr's.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: AC-1 says every row has a non-empty hint at width 120, but the plan also says a missing hint renders nothing, and it cap

- Severity: HIGH
- References: CHANGE_SPEC AC-1 vs section 8 ('Missing hint renders no hint'; 'Invalid config row ! reason unchanged'); CHANGE_PLAN D-2 (<=40 chars). Settle it with: 'Hint length <= 40 is asserted by the test, not truncated at render time; ! reason rows get no hint.'
- Failure: AC-1 says every row has a non-empty hint at width 120, but the plan also says a missing hint renders nothing, and it caps hints at 40 chars without saying who enforces the cap. Truncation versus rejection is unspecified. A row with a long value, or an invalid '! reason' row, may or may not get a hint.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The plan does not define how picker explanations are observed in tests.

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 and section 16 ('picker explanations'); CHANGE_SPEC AC-2 ('non-empty explanation for every choice'). Settle it with: 'The test asserts via a fake stdscr recording addnstr text at width >= 120; Custom rows get no explanation.'
- Failure: The plan does not define how picker explanations are observed in tests. D-5 says they are appended in _draw_picker and truncated by addnstr, so a fake stdscr's captured text depends on the width and on whether the Custom row and filter rows get explanations. Whether a Custom row or a filtered-out choice keeps its explanation is unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Runner explanations use a generic fallback, but the plan never defines the runner value set or the fallback text.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 ('runner values with a generic fallback string') and section 21 (cut runner explanations first); CHANGE_SPEC AC-2/SB-5. Settle it with: 'The runner set is enumerated from the same list that _picker_rows uses; the fallback string is non-empty; if the cut is invoked, AC-2 is amended to exclude the runner picker.'
- Failure: Runner explanations use a generic fallback, but the plan never defines the runner value set or the fallback text. Tests can't assert 'non-empty for every runner' unless the set of runners is pinned to a source. The cut-first item 'runner-choice explanations' also contradicts AC-2, which requires them.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan does not say how the delegate picker's current value is shown, or what happens when the stored delegate_gates v

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 ('no Custom row, like network'), D-4; CHANGE_SPEC SB-4 ('Free-text Custom row only' before). Settle it with: 'An unrecognised stored value highlights no row, and none/routine are the only selectable values.'
- Failure: The plan does not say how the delegate picker's current value is shown, or what happens when the stored delegate_gates value is neither none nor routine. It also does not say whether a previous free-text Custom entry is still reachable. Tests have no defined expected result.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The defect-injection method is underspecified.

- Severity: LOW
- References: CHANGE_PLAN section 16 (defect injection: blank one hint key only); CHANGE_SPEC AC-4 ('equals prior values'). Settle it with: 'Prior non-supervision _picker_rows output is captured as literal expected lists in the test, and defect injection also adds an explanation to a non-supervision picker to confirm failure.'
- Failure: The defect-injection method is underspecified. The plan has no way to prove that tests reject a hint-in-the-wrong-picker defect or a leaked explanation in non-supervision pickers, only a single blanked hint. Required test oracles for the 'unchanged' baseline are not fixed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
