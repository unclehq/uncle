# Verification report

## Findings

### MC-100

- **Action:** Did not launch the interactive curses TUI. Ran runners_for(AGENT) and runners_for(REVIEWER) with PATH=/tmp/emptybin (no claude/codex/kimi/opencode). Also ran scripts/tests/runners-none-installed-test.py (9 tests).
- **Expected result:** Each stage runner picker lists only "Self hosted"; no empty list and no "No agents installed" message appears.
- **Actual result:** runners_for returned ['self-hosted'] for both agent and reviewer sides, and the 9 unit tests passed. The rendered picker and its description text were not observed live. This worker cannot drive and see the curses UI.
- **Defects:** None

### MC-101

- **Action:** Ran the narrow probe scripts/tests/runners-none-installed-test.py (empty-PATH temp env, stubbed TUI object) and inspected uncle_tui.stage_runner/_field_display. Did not drive the interactive TUI or attempt a real stage start.
- **Expected result:** Default is shown as "Self hosted"; starting while unconfigured does not launch a stage and shows the existing configuration-required behavior.
- **Actual result:** Default part verified: with no runner installed or configured, stage_runner returns 'self-hosted' and the runner field displays 'Self hosted' (not 'No agents installed'). Base URL and API key show 'not set', identical to an explicit Self hosted selection. The start-blocked half was not observed live. The probe's own comment says the TUI has no separate configuration gate, and that the shim rejects an unconfigured self-hosted stage at run time. I did not exercise that rejection or see its message.
- **Defects:** None. Setup needed: run the real TUI with an empty-runner PATH and no self-hosted configuration, then try to start a stage and capture the resulting configuration-required message or gate.

### MC-102

- **Action:** Created two temp PATH dirs, one with only an executable stub 'claude', one with only an executable stub 'opencode'. With PATH set to each, called UncleTUI._picker_rows for picker_kind='runner' (the rows the stage runner picker renders) for the first stage target, mapping self-hosted to the display label 'Self hosted'. This exercised the picker row source, not an interactive curses session.
- **Expected result:** With claude: picker lists Claude and Self hosted once each, in that order; with only opencode: only Self hosted, listed once.
- **Actual result:** claude-only PATH: rows = ['claude'] (Self hosted NOT listed). opencode-only PATH: rows = ['Self hosted'] (once). The opencode half matches. The claude half does not match the checklist wording (missing Self hosted entry).
- **Defects:** Checklist/spec mismatch: MC-102 claude-only expectation (Self hosted also listed) contradicts CHANGE_SPEC AC-3; needs human ruling on whether to amend the checklist or the implementation.

### MC-201

- **Action:** Set PATH to a nonexistent dir (no runner binaries) with DEFAULT_RUNNER empty and no configured runner, then called the real UncleTUI._field_display(stage,'runner') (via the Stub in scripts/tests/runners-none-installed-test.py) for the first stage. Also ran that probe file (9 tests, OK). No live curses screenshot taken.
- **Expected result:** The default runner displays as 'Self hosted'; it is not blank.
- **Actual result:** Display string was 'Self hosted  (default)': non-blank, says 'Self hosted', no 'No agents installed' and no raw 'self-hosted'.
- **Defects:** None

### MC-202

- **Action:** Ran scripts/tests/runners-none-installed-test.py (read-only probe). Did not launch the TUI or attempt a live stage start.
- **Expected result:** No stage starts; the existing configuration-required behavior is shown, same as explicitly selecting unconfigured self-hosted.
- **Actual result:** Probe passed (9 tests OK). With no runner installed, runners_for returns ['self-hosted'] and the default stage_runner is 'self-hosted', identical to an explicit self-hosted selection. The probe's own comment says the configuration-required rejection happens in the shim at run time, so no live stage start or resulting message was observed. The 'no run began' and message-display parts are unobserved.
- **Defects:** None

### MC-203

- **Action:** Created temp dirs holding only fake executable claude+opencode, and only opencode; called uncle_tui.runners_for(AGENT/REVIEWER) with PATH restricted to each (the function feeding the runner picker); read the picker render code (uncle_tui.py ~7430); ran scripts/tests/runners-none-installed-test.py (9 tests OK). Did NOT drive the live curses picker or capture screenshots.
- **Expected result:** First case shows 'Claude' then 'Self hosted' once each in that order; opencode-only shows only 'Self hosted' once, no duplicates or extras.
- **Actual result:** Data layer: claude+opencode -> ['claude','self-hosted'] for both sides; opencode-only -> ['self-hosted']. Order and uniqueness match. Picker render maps 'self-hosted' to 'Self hosted' but shows 'claude' as lowercase text (no capitalised 'Claude' mapping seen in code), differing from the literal expected label. Live picker screenshots were not captured, so the visible UI was not observed.
- **Defects:** None (possible label-casing discrepancy 'claude' vs 'Claude' needs human confirmation in the live picker)

### MC-301

- **Action:** Imported the real uncle_tui module (python3 -I) with PATH set to an empty temp dir and no stage runner configured. Called runners_for() for every stage (agent and reviewer sides) and UncleTUI._field_display(stage,'runner') for an agent stage (implementation) and a reviewer stage (adversarial-review). Did not drive the interactive curses UI; used the real functions that back the picker and the Configure default display.
- **Expected result:** Each stage runner picker lists only 'Self hosted' and the stage default shows 'Self hosted'; 'No agents installed' is never shown.
- **Actual result:** Picker list is correct: runners_for returned ['self-hosted'] for all 15 stages on both agent and reviewer sides. The default display is wrong: _field_display returned 'claude  (default)' for both implementation (agent) and adversarial-review (reviewer), not 'Self hosted'. Cause: uncle_tui.py:369 sets DEFAULT_RUNNER = 'claude', and stage_runner (uncle_tui.py:1209-1210) returns it before the installed-runner scan. The comment at 1207-1208 says DEFAULT_RUNNER is '' in normal use. The existing probe scripts/tests/runners-none-installed-test.py masks this by setting DEFAULT_RUNNER='' in setUp. 'No agents installed' was not shown.
- **Defects:** New: the stage default displays 'claude (default)' instead of 'Self hosted' when no runners are installed, because module-level DEFAULT_RUNNER='claude' overrides the discovery fallback (uncle_tui.py:369, 1209).

### MC-302

- **Action:** Did not drive the interactive TUI. Ran scripts/tests/runners-none-installed-test.py (9 tests, incl. unconfigured self-hosted default equals explicit selection, base_url/api_key show 'not set'). Then ran scripts/agent-self-hosted.sh (the runner shim a stage launches) with an env -i PATH containing no agent binaries (only python3/dirname/bash) and no self-hosted config.
- **Expected result:** No stage starts; the existing configuration-required behavior for self-hosted is shown.
- **Actual result:** Probe: 9 tests OK. Shim exited with a configuration error 'Self hosted requires an http(s) Base URL without credentials, query, or fragment' and a JSON result is_error=true, duration_ms 0; no opencode/model process was running afterward. The TUI screen/message on pressing start was not observed live.
- **Defects:** None

### MC-303

- **Action:** Created a temp dir holding executable stub files named claude and opencode and used it as the only PATH entry. Imported uncle_tui from the worktree and called runners_for for the agent and reviewer sides. Also called UncleTUI._picker_rows and _picker_filtered for the runner picker, once with a stage target and once with the '!supervision' target. I did not drive the interactive curses screen or capture a screenshot.
- **Expected result:** The picker lists exactly Claude and Self hosted, with Self hosted appearing once and no other entries.
- **Actual result:** runners_for(AGENT) and runners_for(REVIEWER) both returned ['claude', 'self-hosted']. The runner picker rows for a stage target were [('option','claude'),('option','self-hosted')]. The '!supervision' target returned the same two rows. The opencode stub is mapped to self-hosted and appears once, with no extra entries. The picker holds the ids claude and self-hosted; this run did not read the display labels 'Claude' and 'Self hosted' on screen.
- **Defects:** None

### MC-404

- **Action:** Ran a narrow probe with PATH=/nonexistent: imported uncle_tui and called runners_for(AGENT) and runners_for(REVIEWER). Read the uncle_tui.py runner-display code (_field_display) and the _open_picker notice code. Did not launch the interactive TUI and did not attempt a stage start.
- **Expected result:** The text never shows 'No agents installed' and lists 'Self hosted'; starting a stage with unconfigured Self hosted does not launch and shows the same configuration-required behavior as explicitly selecting unconfigured Self hosted.
- **Actual result:** Partial evidence only. With no runner binaries on PATH, runners_for returned ['self-hosted'] for both AGENT and REVIEWER. _field_display maps a self-hosted default to the label 'Self hosted'. The 'No agents installed' string remains only as a guard in _open_picker for the case where there are no runners at all, which the fallback should prevent. The live home-screen text and the stage-start behavior with unconfigured Self hosted were not observed, and no screenshots were captured, so the check is not complete.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | BLOCKED-HUMAN | PATH=/tmp/emptybin python3 -c 'runners_for' printed: agent ['self-hosted'] / reviewer ['self-hosted']. Unit test output: Ran 9 tests, OK. |
| MC-101 | YES | BLOCKED-SETUP | python3 scripts/tests/runners-none-installed-test.py: Ran 9 tests, OK. uncle_tui.py:1196-1210 (stage_runner), uncle_tui.py:1706 (self-hosted requires a base URL). |
| MC-102 | YES | FAIL | Probe output: "derive-brief ['claude']" and "derive-brief ['Self hosted']". runners_for in uncle_tui.py:690-709 returns only installed binaries and falls back to ['self-hosted'] only when none are installed. CHANGE_SPEC.md AC-3 says that with runner binaries on PATH output is unchanged, 'no extra entries', which conflicts with this checklist row's expectation. The conflict is between the checklist and the approved spec; the checklist expectation was not met as written. |
| MC-201 | YES | PASS | Direct call output: 'Self hosted  (default)'. Probe runners-none-installed-test.py: Ran 9 tests, OK. Code: uncle_tui.py lines 1295-1300. A rendered TUI screenshot was not captured; evidence is the real display function output. |
| MC-202 | YES | NOT RUN | Probe output: Ran 9 tests, OK. Includes test_unconfigured_self_hosted_default_matches_explicit_selection. No screenshot or capture of the configuration-required message. |
| MC-203 | YES | NOT RUN | runners_for output above; uncle_tui.py:690-709 and 7430; unittest run OK (9 tests). |
| MC-301 | YES | FAIL | Terminal output with PATH=<empty tmp dir>: DEFAULT_RUNNER 'claude'; implementation agent ['self-hosted']; adversarial-review reviewer ['self-hosted']; _field_display -> 'claude  (default)' for both. Source: uncle_tui.py:369, 1196-1212, 1294-1300. git show HEAD:uncle_tui.py has no DEFAULT_RUNNER line, so the diff does not add it and it may be pre-existing in the checkout. |
| MC-302 | YES | BLOCKED-HUMAN | Unittest output 'Ran 9 tests ... OK'; shim stderr/JSON error as quoted above; ps showed 0 opencode processes. Exit code of shim not captured (PIPESTATUS empty under zsh). The TUI notice was not captured, which the checklist asks for. |
| MC-303 | YES | PASS | Console output of the in-process probe: ['claude', 'self-hosted'] ['claude', 'self-hosted'] / [('option', 'claude'), ('option', 'self-hosted')] / [('option', 'claude'), ('option', 'self-hosted')]. Source: uncle_tui.py runners_for (around line 690) and _picker_rows (around line 1455). |
| MC-404 | YES | NOT RUN | Probe output: ['self-hosted'] ['self-hosted']. Code references: uncle_tui.py:1290, 1299-1300, 1534. Existing test scripts/tests/runners-none-installed-test.py covers the fallback; I did not re-run it. |
