# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch uncle with PATH containing none of claude, codex, kimi, opencode; open Configure and open the runner picker for an agent stage, then for a reviewer stage.
- Expected result: Each stage runner picker lists only "Self hosted"; no empty list and no "No agents installed" message appears.
- Evidence to capture: Screenshots or terminal captures of both pickers and the description text.
- Actual result: 
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With the same empty-runner PATH and no configured runner, view the default runner shown for a stage, then select Self hosted while it is unconfigured and try to start a stage.
- Expected result: Default is shown as "Self hosted"; starting while unconfigured does not launch a stage and shows the existing configuration-required behavior.
- Evidence to capture: Capture of the default display and the resulting message or gate.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch uncle with PATH containing a stub executable named claude (and separately one with only opencode), then open the stage runner picker.
- Expected result: With claude: picker lists Claude and Self hosted once each, in that order; with only opencode: only Self hosted, listed once.
- Evidence to capture: Captures of the picker for each PATH setup.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With no runner binaries on PATH and no configured runner, view the default runner shown for a stage in the TUI.
- Expected result: The default runner displays as 'Self hosted'; it is not blank.
- Evidence to capture: Screenshot of the stage default.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With no runners installed and self-hosted unconfigured, try to start a stage using the defaulted Self hosted runner.
- Expected result: No stage starts; the existing configuration-required behavior is shown, same as explicitly selecting unconfigured self-hosted.
- Evidence to capture: Screenshot or capture of the resulting message and confirmation that no run began.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Put fake executable claude and opencode on PATH (only those), launch uncle, and open the stage runner picker; repeat with only opencode.
- Expected result: First case shows 'Claude' then 'Self hosted' once each in that order; opencode-only shows only 'Self hosted' once, with no duplicates or extra entries (V2).
- Evidence to capture: Screenshots of both pickers.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start uncle with PATH set to a temp directory containing none of claude, codex, kimi or opencode, open Configure, and open the runner picker for an agent stage and for a reviewer stage.
- Expected result: Each stage runner picker lists only "Self hosted" and the stage default shows "Self hosted"; the text "No agents installed" is never shown.
- Evidence to capture: Screenshot or terminal capture of both pickers and the default display.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With the same empty-runner PATH and self-hosted unconfigured, select the Self hosted default for a stage and try to start it.
- Expected result: No stage starts; the existing configuration-required behavior for self-hosted is shown.
- Evidence to capture: Capture of the screen or message shown after the attempt, plus confirmation that no stage process started.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start uncle with a temp PATH containing executable stub files named claude and opencode, then open the stage runner picker.
- Expected result: The picker lists exactly Claude and Self hosted, with Self hosted appearing once and no other entries.
- Evidence to capture: Capture of the picker list.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch uncle with PATH containing none of the four runner binaries and no configured runner, view the home/configuration screen description text, then try to start a stage with the default Self hosted runner while it is unconfigured.
- Expected result: The text never shows 'No agents installed' and lists 'Self hosted'; starting a stage with unconfigured Self hosted does not launch and shows the same configuration-required behavior as explicitly selecting unconfigured Self hosted.
- Evidence to capture: Screenshots of the description text and of the result of the start attempt.
- Actual result: 
- Status: NOT RUN
