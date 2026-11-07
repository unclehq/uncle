## AR-001: Apply-to-all (`a`) is only specified for success and for the no-Bedrock-stage refusal.

- Severity: HIGH
- References: CHANGE_SPEC BH-4 and section 8 cover only the no-Bedrock-stage refusal; CHANGE_PLAN section 6 shows only the success path.
- Failure: Apply-to-all (`a`) is only specified for success and for the no-Bedrock-stage refusal. Plan should say: 'If the Bedrock key store lacks token, model or base_url for the source stage, `a` prints a Bedrock-worded error and writes nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Fallback `m` writes `<stage>.model`, but lookup falls back to `aws-bedrock.model`; plan never says which key is written.

- Severity: HIGH
- References: CHANGE_PLAN section 6 (`config_set <stage>.model`) vs stage-config.sh:344-346.
- Failure: Fallback `m` writes `<stage>.model`, but lookup falls back to `aws-bedrock.model`; plan never says which key is written. Plan should say: 'Fallback `m` writes only `<stage>.model`; global `aws-bedrock.model` is never modified by configure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: BH-1 keeps the stage's existing model when switching to aws-bedrock, which can leave a Self hosted model name on a Bedro

- Severity: MEDIUM
- References: CHANGE_SPEC BH-1 'stage's model kept'; spec section 8 has no validation.
- Failure: BH-1 keeps the stage's existing model when switching to aws-bedrock, which can leave a Self hosted model name on a Bedrock stage. Plan should say: 'Switching to aws-bedrock keeps the model unvalidated' or 'clears it if not in the Bedrock list'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Menu renumbering leaves stale scripted input unspecified (old '3' now opens Bedrock setup).

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 and risk 22; CHANGE_SPEC section 7.
- Failure: Menu renumbering leaves stale scripted input unspecified (old '3' now opens Bedrock setup). Plan should say: 'Item 3 opens Bedrock configuration with no confirmation; invalid numbers show the existing invalid-choice message.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Runner prompt ordering and the zero-installed-CLI case are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1; BH-9; uncle_no_runner at stage-config.sh:273.
- Failure: Runner prompt ordering and the zero-installed-CLI case are unspecified. Plan should say: 'With zero installed CLIs the prompt lists only aws-bedrock and accepts it; order is installed runners then aws-bedrock.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Audit rows collide: stages-menu `m` is Self hosted only (uncle:887) yet a Bedrock stage now displays as aws-bedrock ther

- Severity: MEDIUM
- References: CHANGE_PLAN audit table rows uncle:875 vs uncle:887.
- Failure: Audit rows collide: stages-menu `m` is Self hosted only (uncle:887) yet a Bedrock stage now displays as aws-bedrock there (uncle:875). Plan should say: 'Stages-menu `m` on a Bedrock stage prints a message pointing to per-stage configure and writes nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan never says what happens to model when a stage's runner switches to or from aws-bedrock.

- Severity: HIGH
- References: CHANGE_SPEC BH-1 'stage's model kept'; INV-1 requires separate key stores but gives no model carry-over rule.
- Failure: The plan never says what happens to model when a stage's runner switches to or from aws-bedrock. BH-1 says 'stage's model kept', so a Self hosted model could remain on a Bedrock stage. Settle with: 'Changing runner to or from aws-bedrock leaves model unchanged; `m` validates against the key store of the stage's current runner.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Menu renumbering (Misc 3 to 4) is only an assumption and risk; no test covers input 3 or 4 for scripted users.

- Severity: HIGH
- References: CHANGE_PLAN D-4 and risk s21.1.i1; the traceability table has no menu-mapping test.
- Failure: Menu renumbering (Misc 3 to 4) is only an assumption and risk; no test covers input 3 or 4 for scripted users. Settle with: 'Input 3 opens Configure AWS Bedrock, 4 opens Miscellaneous, and the shell test asserts both mappings and rejection of 5.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Apply-to-all behavior is unspecified for stages with an existing per-stage key or a non-HTTP runner such as claude or co

- Severity: MEDIUM
- References: CHANGE_PLAN s6 'copy runner/model/base_url to all stages'; INV-1 covers only the key stores.
- Failure: Apply-to-all behavior is unspecified for stages with an existing per-stage key or a non-HTTP runner such as claude or codex. Settle with: 'Apply-to-all overwrites runner, model and base_url on every stage, replaces each stage's Bedrock key, and leaves self-hosted-keys.json untouched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Behavior of `uncle_selectable_runners` with no installed binaries is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 vs stage-config.sh:294,316 (uncle_no_runner); BH-9 says only 'installed runners plus aws-bedrock'.
- Failure: Behavior of `uncle_selectable_runners` with no installed binaries is unspecified. The no-runner error at stage-config.sh:316 is unchanged while the picker offers Bedrock. Settle with: 'With no binaries installed the prompt lists only aws-bedrock, and selecting it succeeds.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Showing the raw runner in the list (uncle:875) conflicts with unchanged Self hosted display: legacy opencode/aider value

- Severity: MEDIUM
- References: CHANGE_PLAN audit row uncle:875 'show raw runner' vs s8 Compatibility; stage-config.sh:311 normalizes opencode|aider|aws-bedrock.
- Failure: Showing the raw runner in the list (uncle:875) conflicts with unchanged Self hosted display: legacy opencode/aider values would now display raw. Settle with: 'The list shows the raw runner only for aws-bedrock; opencode and aider still display as self-hosted.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: An unrecognized optional profile argument on `self_hosted.py` is unspecified; a typo would silently write the Self hoste

- Severity: LOW
- References: self_hosted.py:1974-1982 uses only args[0] and args[1]; D-2 does not validate args[2].
- Failure: An unrecognized optional profile argument on `self_hosted.py` is unspecified; a typo would silently write the Self hosted store, breaking INV-1. Settle with: 'A profile argument other than aws-bedrock or absent exits non-zero and writes nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan does not say how the Bedrock token moves during fallback apply-to-all.

- Severity: HIGH
- References: CHANGE_PLAN s6: 'token copied via read_keys/save_keys' but D-2 lists no such subcommand; INV-5 forbids token in argv/output.
- Failure: Plan does not say how the Bedrock token moves during fallback apply-to-all. Settle with: 'Apply-to-all copies the token only inside self_hosted.py via a subcommand on aws-bedrock-keys.json; the token never passes through shell variables, argv, env or output.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Invalid profile argument handling is unspecified.

- Severity: MEDIUM
- References: D-2 optional trailing arg; self_hosted.py:1970-1982 uses unvalidated positional args, so a typo could write a Bedrock token to self-hosted-keys.json (INV-1).
- Failure: Invalid profile argument handling is unspecified. Settle with: 'Any profile argument other than aws-bedrock or absent exits non-zero, writes nothing, and never falls back to the Self hosted store.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Bedrock connection setup (BH-6) leaves URL validation unspecified.

- Severity: MEDIUM
- References: profile_menu (self_hosted.py:1960-1966) takes URL unvalidated; _bedrock_url_ok exists at line 72; CHANGE_SPEC s10 claims 0600 mode but no test is mapped.
- Failure: Bedrock connection setup (BH-6) leaves URL validation unspecified. Settle with: 'Configure AWS Bedrock applies _bedrock_url_ok to the Base URL and rejects invalid URLs without writing; failures redact the token via redact_token.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Apply-to-all scope for tokens is ambiguous for stages with other runners.

- Severity: MEDIUM
- References: BH-4/AC-3: token copied 'to every stage'; INV-1 only asserts self-hosted-keys.json byte-identical.
- Failure: Apply-to-all scope for tokens is ambiguous for stages with other runners. Settle with: 'Apply copies the Bedrock token only to stages set to aws-bedrock by this action, in aws-bedrock-keys.json only.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Plan does not state where token absence is asserted.

- Severity: LOW
- References: AC-3 verification greps only '.uncle/config or output'; INV-5 does not name stderr.
- Failure: Plan does not state where token absence is asserted. Settle with: 'No token appears in stdout, stderr, .uncle/config or argv for any fallback action, including failures.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: AC-6 requires a fallback selection to be read by the TUI loader, but the plan never names which TUI function is the conf

- Severity: HIGH
- References: CHANGE_SPEC AC-6 verification: 'loads a config written by the fallback test into the TUI config reader'; plan section 16 names no function.
- Failure: AC-6 requires a fallback selection to be read by the TUI loader, but the plan never names which TUI function is the config reader under test. Plan should say: 'AC-6 test calls <named TUI function> on the fallback-written config and asserts stage_runner == aws-bedrock.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: BH-4/AC-3 'token copied to every stage' is untestable: the plan doesn't say how the per-stage token is keyed in aws-bedr

- Severity: HIGH
- References: CHANGE_PLAN section 6: 'token copied via read_keys/save_keys(profile=aws-bedrock)'; BH-4 says 'every stage' with no enumeration.
- Failure: BH-4/AC-3 'token copied to every stage' is untestable: the plan doesn't say how the per-stage token is keyed in aws-bedrock-keys.json or which stages count as 'all'. Plan should say: 'apply-to-all writes keys[stage]=token for each stage in <explicit list>, and the test asserts exactly that key set.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Error behavior for `m` is unspecified for an empty model list, EOF, a blank choice, and a name without the local/ prefix

- Severity: MEDIUM
- References: self_hosted.py:1955-1957 applies local_model() and an OpenCode-worded error; CHANGE_SPEC section 8 only says 'Bedrock-worded message'.
- Failure: Error behavior for `m` is unspecified for an empty model list, EOF, a blank choice, and a name without the local/ prefix. Plan should say: 'For aws-bedrock, choose-model matches names exactly as stored, exits nonzero with a Bedrock-worded stderr message on an unknown or empty choice, and prints nothing to stdout.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: `d` on a Bedrock stage with no stored key, and `set-key` with empty stdin, are unspecified, so test oracles can disagree

- Severity: MEDIUM
- References: self_hosted.py:1974-1982 pops silently on empty key; BH-7 states only the 'clears' case.
- Failure: `d` on a Bedrock stage with no stored key, and `set-key` with empty stdin, are unspecified, so test oracles can disagree. Plan should say: 'd with no stored key exits 0 and leaves aws-bedrock-keys.json byte-identical.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The shell test's fallback of awk-extracting function blocks from `uncle` tests copies rather than shipped code, so the d

- Severity: MEDIUM
- References: CHANGE_PLAN step 4 and risks: 'check whether uncle can be sourced ... else extract function blocks with awk'; section 16 requires tests to fail on HEAD.
- Failure: The shell test's fallback of awk-extracting function blocks from `uncle` tests copies rather than shipped code, so the defect-injection-on-HEAD claim can pass or fail for the wrong reason. Plan should say: 'The shell test runs the real `uncle` functions; an extracted copy is allowed only if the test asserts it matches the file text.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: The prompt format in BH-9 ('installed runners plus aws-bedrock') leaves order and separator unspecified, and doesn't say

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 helper 'installed + aws-bedrock'; stage-config.sh:215 lowercases values; AC-1 only says 'the prompt lists it'.
- Failure: The prompt format in BH-9 ('installed runners plus aws-bedrock') leaves order and separator unspecified, and doesn't say how uppercase input like 'AWS-Bedrock' is handled. Plan should say: 'Prompt lists uncle_selectable_runners in order, installed first then aws-bedrock; input is lowercased and written lowercase.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
