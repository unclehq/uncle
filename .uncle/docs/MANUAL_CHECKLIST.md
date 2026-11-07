# Manual checklist

## Fallback runner picker

### MC-100
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: In a temp project with a fixture .uncle/config, run `./uncle`, open fallback Configure, choose a stage, press `r`, and type `AWS-Bedrock`; repeat for one agent stage and one reviewer stage, then try an invalid name like `foo`.
- Expected result: The prompt lists installed runners in order then aws-bedrock last; AWS-Bedrock is stored lowercase as `<stage>.runner aws-bedrock` for both sides; `foo` is rejected with the existing message and nothing is written.
- Evidence to capture: Terminal transcript of the prompt and the resulting .uncle/config lines.
- Actual result: 
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: Run the fallback Configure with PATH containing no runner binaries (empty runner PATH) and open the runner prompt for a stage, then type `aws-bedrock`.
- Expected result: The prompt lists only aws-bedrock and selecting it succeeds without the no-agents-installed error.
- Evidence to capture: Terminal transcript and the written runner line in .uncle/config.
- Actual result: 
- Status: NOT RUN

## Fallback model choice and key clearing

### MC-102
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: With a fixture aws-bedrock-keys.json containing `__opencode_models__` and a Bedrock stage, press `m` in the stage configure and choose a valid model, then `m` again with an invalid name, then press `d`.
- Expected result: The stage shows as aws-bedrock with Bedrock prompts; the valid model is written only to `<stage>.model` (global aws-bedrock.model line unchanged); the invalid choice changes nothing with a Bedrock-worded message; `d` removes only that stage's Bedrock key.
- Evidence to capture: Transcript plus before/after .uncle/config and aws-bedrock-keys.json contents.
- Actual result: 
- Status: NOT RUN

## Fallback apply-to-all

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: With a Bedrock stage having a sentinel token, model and base_url in fixtures and other stages on claude/codex/self-hosted, press `a` in the fallback; then repeat with the token, model, or base_url missing.
- Expected result: Success: every stage gets runner aws-bedrock, model and base_url, aws-bedrock-keys.json has an entry per stage, self-hosted-keys.json is unchanged, and the token appears nowhere in output or .uncle/config. Failure: a Bedrock-worded error names the missing item and no files change.
- Evidence to capture: Transcript, sha of both key files before/after, grep for the sentinel in output and config.
- Actual result: 
- Status: NOT RUN

## Fallback Configure menu

### MC-104
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: Open fallback Configure and enter 3, then 4, then 5; in item 3 supply a valid URL and a hidden token, and also try an invalid URL like `ftp://x`.
- Expected result: 3 opens Configure AWS Bedrock, 4 opens Miscellaneous, 5 shows the invalid-choice message; a valid setup writes aws-bedrock-keys.json (mode 0600) leaving self-hosted-keys.json untouched; invalid URL is rejected with nothing written and the token is never echoed.
- Evidence to capture: Transcript, `ls -l` of key files, file hash of self-hosted-keys.json before/after.
- Actual result: 
- Status: NOT RUN

## Fallback stages menu

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: none
- Exact action: Open the fallback stages menu with one aws-bedrock stage plus opencode and aider stages, view the list, then press `m` on the Bedrock stage.
- Expected result: The Bedrock stage lists as aws-bedrock while opencode and aider list as self-hosted; `m` on the Bedrock stage prints a pointer to per-stage configure and writes nothing.
- Evidence to capture: Transcript and unchanged .uncle/config hash.
- Actual result: 
- Status: NOT RUN

## TUI parity

### MC-106
- Required for acceptance: YES
- Exclusive resources: file:temp-project-config
- Depends on: MC-103
- Exact action: Open the full-screen TUI in the project whose config was written by the fallback with an aws-bedrock stage; check the Configure runner display, then run apply-to-all on a Bedrock stage.
- Expected result: The TUI shows the stage as aws-bedrock with the same model; apply-to-all applies runner, model, base_url and Bedrock token to all stages without a refusal, and self-hosted-keys.json is unchanged.
- Evidence to capture: Screen capture or transcript and key file hashes.
- Actual result: 
- Status: NOT RUN

### MC-200
- Exclusive resources: none
- Exact action: In a temp project with fixture aws-bedrock-keys.json and a distinct self-hosted-keys.json (record its hash), run the `uncle` shell-fallback and use the Configure AWS Bedrock menu item, then per-stage `m` and `d` on a Bedrock stage. Re-hash both key files after each step.
- Expected result: Bedrock actions change only aws-bedrock-keys.json; self-hosted-keys.json hash is unchanged throughout, and `m` writes only <stage>.model (the global aws-bedrock.model line is unchanged).
- Actual result: 
- Status: NOT RUN

### MC-201
- Exclusive resources: none
- Exact action: In the fallback with a mixed-runner fixture (claude, codex, self-hosted, aws-bedrock stages with a sentinel Bedrock token), press `a` on a Bedrock stage; capture all stdout/stderr and inspect .uncle/config and both key files.
- Expected result: Every stage becomes aws-bedrock with model and base_url; aws-bedrock-keys.json stage keys equal exactly the switched stages with the sentinel token; self-hosted-keys.json is byte-identical; the sentinel appears nowhere in output or .uncle/config.
- Actual result: 
- Status: NOT RUN

### MC-203
- Exclusive resources: none
- Exact action: Run `self_hosted.py models`, `choose-model` and `set-key <config> <stage>` with profile `aws-bedrok` (typo), with a sentinel token on stdin for set-key, and again with an invalid Base URL in Configure AWS Bedrock.
- Expected result: Each exits non-zero with an error, nothing is written, both key files stay byte-identical, and the token never appears in output.
- Actual result: 
- Status: NOT RUN

### MC-204
- Exclusive resources: none
- Exact action: In the fallback open Configure menu and enter 3, then 4, then 5; also on a Bedrock stage use the stages-menu `m`.
- Expected result: 3 opens Configure AWS Bedrock, 4 opens Miscellaneous, 5 shows the existing invalid-choice message with no changes; stages-menu `m` on a Bedrock stage prints a pointer to per-stage configure and writes nothing.
- Actual result: 
- Status: NOT RUN

### MC-205
- Exclusive resources: none
- Exact action: In the fallback with an empty runner PATH, open the runner prompt for a stage, note the listed runners, enter `AWS-Bedrock`; then restore PATH with fake claude/codex binaries and view the prompt and stage list including opencode/aider legacy stages.
- Expected result: Empty PATH lists only aws-bedrock and accepts it, stored as lowercase `aws-bedrock`; with binaries, installed runners appear in order then aws-bedrock last; the stage list shows aws-bedrock only for Bedrock stages while opencode/aider show as self-hosted.
- Actual result: 
- Status: NOT RUN

### MC-206
- Exclusive resources: none
- Exact action: Switch a stage with an existing Self hosted model to aws-bedrock in the fallback and back, noting <stage>.model each time, then press `m` and attempt a model from the other runner's store.
- Expected result: The model value is unchanged and unvalidated in both directions; `m` offers and accepts only models from the current runner's key store, and an invalid choice changes nothing.
- Actual result: 
- Status: NOT RUN

### MC-207
- Exclusive resources: none
- Exact action: In the TUI, select a Bedrock stage and use apply-to-all, then open the same project's config via the fallback stage list.
- Expected result: All stages show aws-bedrock with the same model/base_url in both surfaces; self-hosted-keys.json is unchanged and the token is not displayed or written to .uncle/config.
- Actual result: 
- Status: NOT RUN

### MC-302
- Exclusive resources: file:tmp-bedrock-fallback-project
- Depends on: MC-301
- Exact action: In a temp project whose Bedrock key store lacks the token (then, in a separate run, the model, then the base_url) for the source stage, hash .uncle/config and both key files, press `a` in the fallback, and re-hash.
- Expected result: Each run prints a Bedrock-worded error on stderr naming the missing item but not the token, all three files are byte-identical to before, and the menu keeps running.
- Actual result: 
- Status: NOT RUN

### MC-303
- Exclusive resources: file:tmp-bedrock-fallback-project
- Depends on: MC-302
- Exact action: In a temp project with fixture Bedrock keys, create stage keys for two stages in aws-bedrock-keys.json, press `d` in the fallback on one Bedrock stage, then press `d` again on a Bedrock stage with no stored key, and hash the key files before and after each press.
- Expected result: The first `d` removes only that stage's Bedrock key and leaves the other stage's key and self-hosted-keys.json untouched. The second `d` exits cleanly and leaves aws-bedrock-keys.json byte-identical.
- Actual result: 
- Status: NOT RUN

### MC-304
- Exclusive resources: file:tmp-bedrock-fallback-project
- Depends on: MC-303
- Exact action: In the fallback Configure menu choose item 3 (Configure AWS Bedrock). Enter an invalid Base URL (for example https://user:pw@host/?q=1), then a valid URL with a sentinel token typed at the hidden prompt, and check the file mode of aws-bedrock-keys.json.
- Expected result: The invalid URL is rejected with a Bedrock-worded message and nothing is written. The valid save writes aws-bedrock-keys.json with mode 0600, the token is not echoed to the terminal, and self-hosted-keys.json is unchanged.
- Actual result: 
- Status: NOT RUN

### MC-305
- Exclusive resources: file:tmp-bedrock-fallback-project
- Depends on: MC-304
- Exact action: In the fallback, run `uncle` with an empty PATH (no runner CLIs installed) and open per-stage Configure, press `r` and type `AWS-Bedrock`. Then open the stages menu and press `m` on a Bedrock stage, hashing .uncle/config before and after.
- Expected result: The runner prompt lists only aws-bedrock and accepts it, and .uncle/config stores `aws-bedrock` in lowercase. Stages-menu `m` on the Bedrock stage prints a pointer to per-stage configure and leaves .uncle/config byte-identical.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a temp project with a fixture .uncle/config (stages on claude, codex, kimi and self-hosted) and a self-hosted-keys.json, run `uncle` shell-fallback Configure for a self-hosted stage: press `m`, choose a model, press `a`, then `d`. Compare the prompts and results with the pre-change behavior described in the plan.
- Expected result: Self hosted prompts text and `m`/`a`/`d` behavior are unchanged: model written to <stage>.model, apply-to-all uses Self hosted keys, `d` clears only the self-hosted key; aws-bedrock-keys.json is never created or modified.
- Evidence to capture: Terminal transcript plus before/after copies of .uncle/config and both key files.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the fallback, configure a claude, a codex and a kimi stage via the Runner prompt (`r`), and enter an invalid name such as `bogus` at the prompt.
- Expected result: Valid runners are accepted and written as before; `bogus` is rejected with the existing 'Not a <side> runner' message and nothing is written.
- Evidence to capture: Transcript and the resulting .uncle/config lines.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the full-screen TUI in a temp project, open the runner picker for an agent and a reviewer stage, pick claude, codex, kimi and self-hosted in turn, and select aws-bedrock once; use Configure AWS Bedrock and apply-to-all on a self-hosted stage.
- Expected result: All runners remain selectable and behave as before; aws-bedrock is still listed with its Configure screen; apply-to-all on a self-hosted stage still works with Self hosted keys.
- Evidence to capture: Screenshots or terminal captures of the picker and resulting .uncle/config.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With a Bedrock-selected stage and a Bedrock key store, use the fallback stages-menu `m` on that stage, then run workflow stage dispatch status for a self-hosted stage and a Bedrock stage in the same project.
- Expected result: Stages-menu `m` on a Bedrock stage prints a pointer to per-stage configure and writes nothing; self-hosted and Bedrock stages both still resolve to the self-hosted dispatch path.
- Evidence to capture: Transcript and unchanged .uncle/config hash before and after.
- Actual result: 
- Status: NOT RUN
