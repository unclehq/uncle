# Verification report

## Findings

### MC-102

- **Action:** Headless probe (.uncle/tests/mc102.py, Mock curses stdscr) of UncleTUI at widths 99, 100, 60, 30 with config_section='supervision': called _supervision_items() to count hinted rows, called _draw_config_desc for rows 0/3/12, and ran the full _draw_prompt with config_sel=3 and looked for the highlighted row's description text in the addnstr output. No real terminal resize was done (pyte unavailable, no human terminal).
- **Expected result:** Inline hints absent at <=99 columns and present at 100; at 60 and 30 columns the highlighted row's description still appears (strip fallback); nothing crashes or truncates keys or values.
- **Actual result:** Inline hints behave as expected: 0/13 rows hinted at 99, 13/13 at 100, 0/13 at 60 and 30. No exceptions at any width. Keys and values were intact in the sample rows. FAIL on the description fallback: in the full screen draw (_draw_prompt) the highlighted row's description ('Reasoning effort for the supervisor...') is NOT drawn at 99, 100, 60 or 30 columns. In uncle_tui.py the only caller of _draw_config_desc is at line 8528-8529, which is gated on config_section == 'stages', so the Supervision section never gets the description panel or the narrow strip. Calling _draw_config_desc directly does produce the strip at 60/30, but the screen never calls it for Supervision. With inline hints hidden at <=99, the user sees no description at all at those widths.
- **Defects:** Supervision section never calls _draw_config_desc (uncle_tui.py:8528 gated on config_section == 'stages'), so the strip fallback for the highlighted row's description is missing at 60 and 30 columns. Proposed ID: DEF-MC102.

### MC-103

- **Action:** Ran a narrow temporary probe (/tmp/mc103.py) reusing the real UncleTUI _draw_picker via the project's test harness at width 120 with a Mock curses screen (not a real terminal). Opened the effort picker and the runner picker via _supervision_enter, captured drawn rows, then sent Esc (27) through handle_key and read the stored value and save_config.
- **Expected result:** Each option row (none/low/medium/high; each runner) shows a '  - explanation'. Custom and filter rows have no explanation, and Esc backs out leaving the stored value unchanged.
- **Actual result:** Effort picker: none/low/medium/high each show a distinct '  - ' explanation; the 'Custom… (type an effort)' row has none. Runner picker: claude, codex, kimi, Self hosted and AWS Bedrock each show a '  - ' explanation. Esc left the picker (state became 'stage'), supervision value stayed None before and after, and save_config was not called, for both pickers. No filter row was drawn in this capture, so the filter-row clause was not directly observed. It was not exercised with a typed filter.
- **Defects:** None

### MC-104

- **Action:** Ran a narrow temporary probe (/tmp/mc104/p.py) driving the real UncleTUI picker code (headless, mocked curses) for delegate_gates: opened the picker, captured drawn lines, confirmed 'routine', reopened, confirmed 'none', and read the menu row via _supervision_items(). Not a live terminal session; no real keypress in a running TUI was made.
- **Expected result:** Picker lists only none and routine, each with an explanation, no Custom free-text row. Current value marked; each selection stored and shown in the menu row.
- **Actual result:** Picker (value none) showed exactly: '> none  <current>  - Every gate waits for you.' and '  routine  - Supervisor answers routine dialogs; signing, publication and waivers still need you.' No custom row. Selecting routine stored 'routine' and returned to config state; reopening showed '<current>' on routine. Selecting none stored 'none'. Menu rows: 'delegate_gates routine  - standing delegation: none/routine' and 'delegate_gates none  - standing delegation: none/routine'. Also the driver-run test file's delegate tests (3) passed on a direct run.
- **Defects:** None

### MC-105

- **Action:** No tmux/pty emulator exists here, so I drove the real UncleTUI class (uncle_tui.py) headlessly: a fake curses screen at 120 cols and a throwaway UNCLE_CONFIG temp file (the project's .uncle/config was not touched). Stored `supervision.delegate_gates bogus`, loaded config, ran _supervision_enter on delegate_gates, rendered _draw_picker, then ran the real _go_back (Esc).
- **Expected result:** Picker opens with only none/routine selectable and no row marked current; stored value shown unchanged without an explanation; Esc leaves config unchanged.
- **Actual result:** Picker rows were exactly '> none  - Every gate waits for you.' and '  routine  - Supervisor answers ...'. No row had <current>. The stored 'bogus' is shown in the menu row ('delegate_gates bogus  - standing delegation: none/routine'), not as a separate picker row. After Esc the config line was still 'supervision.delegate_gates bogus' and the in-memory value was still bogus. Selecting routine stored routine. Note: Esc from the !supervision picker sets state to 'stage', not 'config' (the same line exists in HEAD, so it is not part of this change). If the checklist meant a separate unannotated 'bogus' row inside the picker, that was not observed.
- **Defects:** None

### MC-106

- **Action:** Headless drive of the real UncleTUI at 120 cols with a temp config: _supervision_enter on `enabled` twice, on `max_interventions`, then _set_field with 'abc', '-5' and '7'. Opened the effort, runner and model pickers, applied a filter 'o' and inspected the Custom rows.
- **Expected result:** Bool toggles with no picker; numeric edit works; stage-config and model pickers show bare choices without explanations; filter and Custom still work.
- **Actual result:** enabled went false, then true, with state staying 'config' (no picker). max_interventions opened the picker/edit state (picker_kind max_interventions). 'abc' and '-5' were rejected with 'must be a nonnegative integer' and nothing was stored; '7' was stored. Filter 'o' narrowed the effort, runner and model rows. The Custom rows are present for effort and model. Caveat: the effort, runner and model pickers opened with target !supervision DO show '  - explanations' for effort and runner (that is the intended Supervision behaviour per MC-103/202); the model rows show only labels, no explanations. The 'bare choices' part applies to non-Supervision stage pickers, covered under MC-304.
- **Defects:** None

### MC-200

- **Action:** Checked for tools to drive the real curses TUI at 120 columns (tmux); inspected prepared probe scripts/tests/supervision-tooltips-test.py and the driver green-check command list. Did not drive the live TUI.
- **Expected result:** Every control row starts with its key, then value, then a short '  - hint' (<=40 chars, untruncated); Enter acts on the row's own key (bool toggles without picker, numeric opens edit); highlighted row's full description still shows in side panel/strip.
- **Actual result:** Live interactive observation not performed: no terminal multiplexer/emulator (tmux not installed) is available to drive and capture the real TUI. Mocked-curses unit tests (test_every_control_has_a_short_hint_appended_unmodified, test_width_boundary, test_enter_and_toggle_on_each_hinted_row_target_matching_key) exist and are run by the driver green-check (supervision-tooltips), but they are not a live observation and were not re-run here.
- **Defects:** None. Setup action: install tmux (or a pty/terminal emulator such as pyte) and rerun MC-200 at 120 cols, or a human performs the check.

### MC-201

- **Action:** Could not open a real resizable terminal/take screen captures. Instead drove the real UncleTUI code (via the project's test harness with a mocked curses screen) at widths 99, 100, 60, 30, 10, 5, 1 and heights 40/5/2: called _supervision_items(), _draw_picker() for effort/delegate_gates/runner/enabled pickers, and _draw_config_desc() for the highlighted row.
- **Expected result:** Inline hints absent at 99 and below, present at 100; keys/values not truncated by hint logic; highlighted description still shows; tiny sizes never crash.
- **Actual result:** Rows had no hint separator at 99, 60, 30, 10, 5, 1 and had hints at 100 (e.g. 'enabled   true  (default)  - turn supervision on or off'); base key/value text unchanged. No exceptions in any picker draw at any width/height combination. _draw_config_desc rendered the highlighted description ('!supervision — Opt in to event-triggered diagnosis') at 99/100/60 and truncated gracefully at 30/10/5 without error. Not observed in a live terminal: no screen captures and no actual terminal resize events.
- **Defects:** None. Needs a person to visually confirm in a real terminal resized to 99/100/60/30 columns and capture screens; programmatic evidence above found no defect.

### MC-202

- **Action:** Instantiated the real UncleTUI at width 120 (curses stdscr mocked, isolated temp config, via the project's test harness class), entered Supervision -> effort, runner, delegate_gates through _supervision_enter, captured every row drawn by the real _draw_picker, and returned to config state between pickers (non-interactive Esc equivalent; no live terminal was driven).
- **Expected result:** Each option row in effort (none/low/medium/high), runner (every listed runner) and delegate_gates (none/routine) pickers shows a non-empty '  - explanation'; Custom, filter and model rows carry none; delegate_gates has no Custom row.
- **Actual result:** effort: none/low/medium/high each had a distinct non-empty explanation; 'Custom… (type an effort)' had none. runner: claude, codex, kimi, Self hosted, AWS Bedrock all had non-empty explanations; no Custom row. delegate_gates: only none and routine, both explained, no Custom row. No filter or model rows appeared in these pickers.
- **Defects:** None

### MC-203

- **Action:** Headless drive of the real UncleTUI at 120 cols, temp config starting empty: opened delegate_gates, selected routine, reopened, pressed Esc via _go_back, then reopened and selected none, then reopened again.
- **Expected result:** Current value marked on the matching row; selecting stores exactly routine/none and is shown in the menu row; Esc leaves the value unchanged.
- **Actual result:** Fresh open marked '> none  <current>'. After selecting routine the config line was 'supervision.delegate_gates routine' and the menu row showed 'routine'. The reopened picker marked routine <current>. Esc left routine unchanged. Selecting none stored 'none' and the menu row showed none. The reopened picker marked none <current>.
- **Defects:** None

### MC-204

- **Action:** Same headless drive as MC-105: stored the out-of-set value `bogus` in a temp config, opened the picker from the Supervision menu, pressed Esc, then selected routine.
- **Expected result:** Picker lists only none/routine with no row highlighted as current; Esc leaves the stored value unchanged; selecting routine stores routine.
- **Actual result:** Rows were none and routine only, with no <current> marker. After Esc the config still held 'bogus'. Selecting routine stored 'routine'. The checklist says 'stored value shown as an unannotated current row'; no separate row for the stored value exists in the picker (it appears only in the menu row). I took 'no row marked current' as the controlling statement.
- **Defects:** None

### MC-301

- **Action:** A real terminal resize was not possible in this worker. I ran a temporary probe in /tmp/mc301/probe.py that builds the UncleTUI object with curses mocked, as the prepared supervision-tooltips test does. For widths 99, 100, 60 and 30 it called _supervision_items() and then _draw_prompt(40, w) with state=config and config_section=supervision. It recorded the hinted rows, the drawn lines and any description text. I repeated the draw at widths 160 and 60 to check where the description appears. I also read uncle_tui.py around lines 8385-8530.
- **Expected result:** Inline hints are absent at 99 columns and below and present at 100. At 60 and 30 columns the highlighted-option description still shows through the strip fallback. No crash or garbled screen appears, and keys and values are not truncated by the hint logic.
- **Actual result:** The hint boundary and no-crash parts match. Width 99 had 0 of 13 rows hinted, width 100 had 13 of 13 (e.g. 'enabled   true  (default)  - turn supervision on or off'), width 60 had 0 and width 30 had 0. _draw_prompt drew all four widths without an exception. At 60 and 30 columns only the title and the 13 option rows were drawn (14 lines), and no highlighted-option description or strip appeared. The same was true at width 160, where there is no side panel either. In the code, _draw_config_desc, which contains the strip fallback, is called only when config_section == 'stages' (uncle_tui.py:8528-8529). Supervision-section descriptions (_supervision_desc) are therefore never drawn on the Configure screen at any width. At width 30 the rows are cut by the existing addnstr(w-1) clipping, so the value is cut, not by hint logic. This is pre-existing behaviour, since no hint is appended below 100.
- **Defects:** New defect: the highlighted-option description never renders in Configure -> Supervision (no side panel and no narrow-width strip), because _draw_config_desc is only invoked for the 'stages' section. Observed: no description at 60 or 30 columns. Expected: the strip description shows.

### MC-302

- **Action:** Rendered the real UncleTUI._draw_picker at width 120 (curses stdscr mocked, via the project's own supervision-tooltips test harness) after opening the effort, delegate_gates and runner pickers through _supervision_enter on the supervision config section, and captured the drawn lines. This was not an interactive terminal session; Esc was not pressed.
- **Expected result:** Each option row (effort none/low/medium/high; delegate_gates none/routine; each runner) shows a short non-empty explanation. Custom rows get none. The delegate_gates picker lists only none and routine.
- **Actual result:** effort: none/low/medium/high each have a distinct non-empty explanation; the 'Custom… (type an effort)' row has none. delegate_gates: only none and routine, both explained, no custom row. runner: claude, codex, kimi, self-hosted, aws-bedrock all have non-empty explanations.
- **Defects:** None

### MC-303

- **Action:** Headless drive of the real UncleTUI, temp config: opened delegate_gates, selected routine, reopened the menu and picker, pressed Esc without selecting, then selected none.
- **Expected result:** routine stored and shown; Esc leaves it unchanged; none stored; current value marked each time.
- **Actual result:** routine was stored ('supervision.delegate_gates routine') and the menu row showed routine. Esc left it unchanged. none was stored ('supervision.delegate_gates none'). The picker marked the current value (<current>) on each reopen.
- **Defects:** None

### MC-304

- **Action:** Headless drive: opened _open_picker for effort, network, runner and model against the stage 'requirements' (outside Supervision) at 120 cols. Separately toggled `enabled` in Supervision, and in the Supervision effort/model pickers typed a filter and used Custom entry (model custom stored 'my-model').
- **Expected result:** Non-supervision pickers show no explanations; bool toggles without a picker; filtering and Custom entry work as before.
- **Actual result:** The stage effort/network/runner/model pickers showed bare rows ('none', 'low <current>', 'medium', 'high'; 'false <current>', 'true'; claude, codex, kimi, Self hosted; model names with labels only) and no ' - ' explanation text. The bool toggled with no picker. Filter 'o' narrowed rows. Custom for model entered config_edit and stored the typed value.
- **Defects:** None

### MC-401

- **Action:** Headless drive of the real UncleTUI at 120 cols, temp config: pressed Enter on `enabled`, then on `max_interventions`, then ran _set_field with an invalid value ('abc', '-5') and a valid one ('7').
- **Expected result:** Bool toggles with no picker; numeric edit opens free-text entry, rejects invalid values and stores valid ones; hinted rows act on the correct key.
- **Actual result:** enabled toggled false and then true with no picker. The numeric row opened the free-text edit flow for its own key (picker_kind max_interventions). Invalid values were rejected with 'must be a nonnegative integer' and not stored; 7 was stored. The 120-col menu rows carried hints, and Enter on each acted on its own key (also covered by the project test file).
- **Defects:** None

### MC-402

- **Action:** Rendered UncleTUI.draw() in state=config, section=supervision with a mocked curses screen (temp probe /tmp/probe402.py, isolated UNCLE_CONFIG) at widths 60, 99 and 100, with the highlight on rows 0 (enabled), 3 (effort) and 6 (stage_time_seconds), and captured every addnstr call. A real terminal was not driven, so no screen captures exist.
- **Expected result:** At 60 and 99 columns: no inline hints, rows not garbled, and the highlighted row's description still shows in the strip or side panel. At 100 columns: hints appear and the description still shows. No crash at any width.
- **Actual result:** Partly met. Hints: none at 60 or 99, and appended as '  - <hint>' on every row at 100 (for example 'effort  low  (default)  - supervisor reasoning effort'). Rows are intact and the highlight marker moves correctly. Nothing raised at any width. The description does not show: at 60, 99 and 100 no side panel or strip text was drawn for the highlighted row. The only draw calls were the title, the rows (plus the logo at 99 and 100) and nothing else. Cause: uncle_tui.py:8528 calls _draw_config_desc only when config_section == 'stages', so _supervision_desc() (uncle_tui.py:5128) is never rendered on the Supervision config screen. The same gate applies at every width, and the git diff shows no change to that line. The description is only reachable through the picker, which this check did not cover.
- **Defects:** Highlighted-row description is not drawn on the Supervision config screen at any width (uncle_tui.py:8528 only draws it for the 'stages' section). Needs a DEFECTS entry.

### MC-403

- **Action:** Drove the real UncleTUI picker code headlessly (mocked curses screen, temp config) for the model, effort, runner and network pickers on the 'plan' stage: opened the picker, drew it, typed filter 'o', typed non-matching filter 'zzz', selected Custom... where present, then pressed Esc (_go_back). Ran the identical script against the HEAD version of uncle_tui.py (git show HEAD) and the working-tree version, and diffed the outputs.
- **Expected result:** The picker rows, labels, ordering, filtering and Custom entry behave as before, and no explanation text appears next to any row.
- **Actual result:** Baseline and modified outputs were byte-identical (rows, drawn lines, filtered rows, Custom transitions). Model and effort pickers: Custom... selection moved to config_edit with the typed filter 'zzz' prefilled, and Esc returned to the stage screen. Runner and network pickers have no Custom row, as before. The separator '  - ' (explanation text) appears in none of the drawn lines.
- **Defects:** None

### MC-404

- **Action:** Headless drive of the real UncleTUI: in Supervision opened the model picker, inspected rows, filtered, chose Custom and entered 'my-model'. Opened the effort picker, selected high, then restored low.
- **Expected result:** Model rows show no explanations; filter and Custom work as before; effort selection stores the chosen value.
- **Actual result:** Model rows showed ids and labels only, no ' - ' explanation. Filter 'o' narrowed them. Custom opened the edit state and stored 'supervision.model my-model'. The effort pick stored 'supervision.effort high', then 'low' after restoring. The temp config was used, so the project's config needed no restore.
- **Defects:** None

### MC-405

- **Action:** Headless drive: opened delegate_gates in a temp config, selected routine, reopened and pressed Esc. Then stored the out-of-set value `bogus`, reopened and pressed Esc, and checked the config.
- **Expected result:** Picker lists only none/routine, each with an explanation; routine stores 'routine'; Esc leaves the value unchanged, including an out-of-set value with no row highlighted.
- **Actual result:** Picker listed none and routine, each with a non-empty explanation. routine was stored. Esc left both routine and bogus unchanged. With bogus stored, no row carried <current>.
- **Defects:** None

### MC-406

- **Action:** Headless drive at 120 cols: wrote `supervision.max_interventions notanumber` to a temp config, called _supervision_items(), then restored the temp config to empty.
- **Expected result:** The '! reason' row appears unchanged with no hint; all other rows still start with their key; nothing crashes.
- **Actual result:** 14 rows were returned: the 13 control rows plus a final '! Supervision corrections disabled: supervision.max_interventions must be a nonnegative integer. Fix .uncle/config.' row. That row had no ' - ' hint. No other row failed to start with its key. No exception was raised.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-102 | YES | FAIL | Probe output: '99 hinted rows: 0 / 13', '100 hinted rows: 13 / 13', '60 ... 0 / 13', '30 ... 0 / 13'. Full draw: '99 drawn 37 desc shown: False', '100 ... False', '60 drawn 14 desc shown: False', '30 drawn 14 desc shown: False'. Code: uncle_tui.py:8528 `if self.state == "config" and getattr(self, "config_section", "") == "stages": self._draw_config_desc(...)`; grep shows _draw_config_desc has no other caller. Probe script: .uncle/tests/mc102.py. Note: the driver green-check passes, but its test_draw_at_small_sizes only exercises the picker draw, not this config screen. |
| MC-103 | YES | PASS | Effort rows: '  none  - No extended reasoning; fastest and cheapest.' / '> low  <current>  - Light reasoning for simple diagnoses.' / '  medium  - Balanced reasoning depth and cost.' / '  high  - Deepest reasoning; slowest and costliest.' / '  Custom… (type an effort)'. Runner rows: '> claude  <current>  - Claude CLI; confirms steering answers.' / '  codex  - Codex CLI as the supervisor runner.' / '  kimi  - Runs supervisor diagnoses with this CLI.' / '  Self hosted  - Self-hosted runner; confirms steering answers.' / '  AWS Bedrock  - Runs supervisor diagnoses with this CLI.' Post-Esc: value None (before None), save called False. The repo test scripts/tests/supervision-tooltips-test.py covers the same assertions; the probe passed (Ran 1 test, OK). |
| MC-104 | YES | PASS | Probe output lines A/B/stored/row as quoted above; unittest -k delegate: Ran 3 tests OK. |
| MC-105 | YES | PASS | Script output from the headless drive: 'current marked: False', 'esc -> stage [supervision.delegate_gates bogus] bogus', 'select routine -> config [supervision.delegate_gates routine]'. Not a real terminal session. |
| MC-106 | YES | PASS | Script output: 'enabled -> config [supervision.enabled false]', 'enabled -> config [... true]', 'numeric -> picker picker_kind max_interventions', 'invalid abc -> ... []', 'valid 7 -> [supervision.max_interventions 7]', 'filter o -> [...]', 'custom row [...]'. Headless, not a real terminal. |
| MC-200 | YES | BLOCKED-SETUP | `which tmux` returned 'tmux not found'; .uncle/launch.json absent; green-check.md lists 'bash scripts/run-python-tests.sh -- supervisor supervisor-default-runner supervision-tooltips' as driver command. |
| MC-201 | YES | BLOCKED-HUMAN | Ad-hoc python run importing scripts/tests/supervision-tooltips-test.py Base harness; output table showed 'none' for widths <=99 and 'hints' for 100, all draws 'ok'. Driver green-check covers the unit tests (test_width_boundary, test_draw_at_small_sizes_does_not_raise). |
| MC-202 | YES | PASS | Drawn rows: effort: '  none  - No extended reasoning; fastest and cheapest.' / '> low  <current>  - Light reasoning for simple diagnoses.' / '  medium  - Balanced reasoning depth and cost.' / '  high  - Deepest reasoning; slowest and costliest.' / '  Custom… (type an effort)'. runner: five rows each with '  - ...'. delegate_gates: '> none  <current>  - Every gate waits for you.' / '  routine  - Supervisor answers routine dialogs; signing, publication and waivers still need you.'. Picker kinds: effort [option x4, custom]; runner [option x5]; delegate_gates [option x2]. Text capture used instead of screen captures, and Esc was simulated by resetting state rather than pressing a key. |
| MC-203 | YES | PASS | Script output lines 'routine -> [supervision.delegate_gates routine] [delegate_gates routine  - standing delegation: none/routine]', 'esc -> stage [supervision.delegate_gates routine]', 'none -> [supervision.delegate_gates none]'. Headless drive. |
| MC-204 | YES | PASS | 'current marked: False'; 'esc -> stage [supervision.delegate_gates bogus] bogus'; 'select routine -> config [supervision.delegate_gates routine]'. I edited a temp config, not a hand-edited project .uncle/config in a launched TUI. |
| MC-301 | YES | FAIL | Probe output: width 99 'hinted rows 0 / 13'; width 100 'hinted rows 13 / 13'; widths 60 and 30 'hinted rows 0 / 13', 'draw ok; lines 14'. The drawn lines at 60 and 30 were the 'Configure' title plus the 13 rows, with no description line. The _draw_config_desc call is guarded by the 'stages' section check at uncle_tui.py:8528. Not verified in a real terminal. |
| MC-302 | YES | PASS | Captured lines: '  none  - No extended reasoning; fastest and cheapest.' / '> low  <current>  - Light reasoning for simple diagnoses.' / '  medium  - Balanced reasoning depth and cost.' / '  high  - Deepest reasoning; slowest and costliest.' / '  Custom… (type an effort)'. delegate_gates: '> none  <current>  - Every gate waits for you.' / '  routine  - Supervisor answers routine dialogs; signing, publication and waivers still need you.' Runner: claude, codex, kimi, 'Self hosted', 'AWS Bedrock' each with '  - <text>'. Temporary script /tmp/mc302/p.py. |
| MC-303 | YES | PASS | Same script output as MC-203, including the config lines read back from the temp file. |
| MC-304 | YES | PASS | Script output 'effort [...] expl False', 'network ... expl False', 'runner ... expl False', 'model ... expl False', 'custom -> config_edit', 'custom stored config [supervision.model my-model]'. Headless drive, not a real terminal. |
| MC-401 | YES | PASS | Script output as listed under MC-106. Headless; the real keypress loop was not run. |
| MC-402 | YES | FAIL | Probe output: no description text in any draw call for any width or selection. The 100-column output shows the hint suffixes. At 60 the rows have no hints. Gate at uncle_tui.py:8527-8529 (section == 'stages'). Driver green-check already covers hint width boundaries in unit tests (supervision-tooltips-test.py test_width_boundary), which do not exercise the description panel on the config screen. |
| MC-403 | YES | PASS | /tmp/mc403/run.py output diff of /tmp/mc403/b.json (HEAD) vs /tmp/mc403/n.json (working tree): IDENTICAL; grep -c '  - ' on n.json = 0. Limitation: this was a headless harness of the real draw/key-handling methods, not a screen capture in a real terminal. |
| MC-404 | YES | PASS | Script output 'effort -> [supervision.effort high]', 'effort back -> [supervision.effort low]', 'custom stored config [supervision.model my-model]'. |
| MC-405 | YES | PASS | Script output from the MC-105 and MC-203 sections: 'current marked: False', 'esc -> stage [supervision.delegate_gates bogus] bogus', 'routine -> [supervision.delegate_gates routine]'. |
| MC-406 | YES | PASS | Script output: '14 ! Supervision corrections disabled: ... [] False' (the empty list means no non-key rows; False means no hint on the reason row). |
