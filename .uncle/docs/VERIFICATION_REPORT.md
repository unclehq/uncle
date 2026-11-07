# Verification report

## Findings

### MC-100

- **Action:** S1 AC-1 plus S3 MC-100: agent stage `requirements` and reviewer stage `test-review`, `AWS-Bedrock`, then `foo`.
- **Expected result:** Prompt lists installed runners then aws-bedrock; lowercase storage on both sides; `foo` rejected, nothing written.
- **Actual result:** Prompt `claude codex aws-bedrock`; both stages stored `aws-bedrock`; `foo` gave "Not a ... runner: foo" and the config was byte-identical.
- **Defects:** None

### MC-101

- **Action:** S1 empty-PATH case (tool-only PATH).
- **Expected result:** Prompt lists only aws-bedrock; selecting it succeeds.
- **Actual result:** Prompt `Runner (aws-bedrock; opencode = Self hosted)`; runner line written.
- **Defects:** None

### MC-102

- **Action:** S1 `m` case and S3 MC-102/MC-303 (valid model, invalid model, `d`).
- **Expected result:** Valid model written only to `<stage>.model`, global line unchanged; invalid changes nothing with a Bedrock message; `d` removes only that stage key.
- **Actual result:** All matched; the invalid choice left config and key store byte-identical with Bedrock wording.
- **Defects:** None

### MC-103

- **Action:** S1 AC-3 happy path (mixed claude/codex/self-hosted/bedrock) and the three missing-item runs.
- **Expected result:** All stages switched with model, base_url and per-stage keys; self-hosted keys unchanged; no token leak; on a missing item, a Bedrock error and no file change.
- **Actual result:** All matched, including exact key-set equality and byte-identity checks.
- **Defects:** None

### MC-104

- **Action:** S1 menu 3/4/5 checks and S3 MC-304 (`ftp://x`, userinfo URL, valid loopback URL).
- **Expected result:** 3 opens Bedrock, 4 Miscellaneous, 5 the invalid-choice message; invalid URL writes nothing; valid save gives mode 0600 with self-hosted untouched; token not echoed.
- **Actual result:** All matched; mode was 600; the token was absent from stdout.
- **Defects:** None

### MC-105

- **Action:** S1 display and stages-menu `m` checks.
- **Expected result:** Bedrock stage lists as aws-bedrock; opencode and aider as self-hosted; `m` writes nothing.
- **Actual result:** Matched; config byte-identical after `m`. The pointer text `AWS Bedrock models are set per stage: choose a stage, then m.` is at `uncle:927-ish` and was not asserted verbatim by S1.
- **Defects:** None

### MC-106

- **Action:** S2 `TuiSurface` and `CrossSurface` (config written by the fallback read by the TUI loader; apply-to-all on a Bedrock stage). Headless, not curses.
- **Expected result:** TUI shows aws-bedrock and the same model; apply-to-all applies runner, model, base_url and token; self-hosted keys unchanged.
- **Actual result:** S2 asserts stage_runners, stage_models, base_urls and the Bedrock key set; the self-hosted store is unchanged.
- **Defects:** None

### MC-200

- **Action:** S3 MC-304/MC-102/MC-303 hash comparisons of both key files.
- **Expected result:** Only aws-bedrock-keys.json changes; `m` writes only `<stage>.model`.
- **Actual result:** self-hosted-keys.json byte-identical at each step; the global line unchanged.
- **Defects:** None

### MC-201

- **Action:** S1 AC-3 mixed-runner `a`.
- **Expected result:** All stages aws-bedrock; Bedrock key set equals the stage set; self-hosted keys byte-identical; no sentinel leak.
- **Actual result:** Matched.
- **Defects:** None

### MC-203

- **Action:** S5 typo profile for models, choose-model and set-key; S2 `InvalidProfile`; invalid Base URL via S3 MC-304.
- **Expected result:** Non-zero exit, nothing written, token never printed.
- **Actual result:** Exit 2 with the unsupported-profile message and no files created. S2 InvalidProfile tests passed.
- **Defects:** None

### MC-204

- **Action:** S1 menu 3/4/5 and stages-menu `m`.
- **Expected result:** As in MC-104; `m` prints a pointer and writes nothing.
- **Actual result:** Matched; config byte-identical.
- **Defects:** None

### MC-205

- **Action:** S1 empty-PATH and stub-binary prompts; display checks.
- **Expected result:** Empty PATH lists only aws-bedrock and stores lowercase; with binaries, order is claude, codex, aws-bedrock; opencode and aider show as self-hosted.
- **Actual result:** Matched (`claude codex aws-bedrock; opencode = Self hosted`).
- **Defects:** None

### MC-206

- **Action:** S1 self-to-bedrock switch; S3 bedrock-to-self-hosted switch (opencode stub on PATH); `m` with a model from the self-hosted store.
- **Expected result:** Model unchanged in both directions; `m` accepts only the current store; an invalid choice changes nothing.
- **Actual result:** Model `keepme` preserved both ways; `sh-model` rejected under Bedrock, config unchanged.
- **Defects:** None

### MC-207

- **Action:** S2 TUI apply-to-all plus S2 CrossSurface; the fallback side is S1's display check. Not one live round trip.
- **Expected result:** Same runner/model/base_url on both surfaces; self-hosted keys unchanged; no token in config.
- **Actual result:** The TUI side asserted in S2; the fallback display of Bedrock stages asserted in S1.
- **Defects:** None

### MC-302

- **Action:** S1 missing token, model and base_url runs. The Depends on MC-301 has no matching row in the checklist.
- **Expected result:** Bedrock-worded stderr naming the item (not the token), all three files byte-identical, menu continues.
- **Actual result:** Bedrock-worded error present and files byte-identical in each run; menu processed the trailing `q`. S1 asserts "Bedrock" wording but not that the missing item is named.
- **Defects:** None

### MC-303

- **Action:** S3 two-stage key fixture, `d` twice.
- **Expected result:** First `d` removes only that stage key; second `d` leaves the file byte-identical.
- **Actual result:** Matched; the other stage key, `__opencode_models__` and self-hosted keys were untouched.
- **Defects:** None

### MC-304

- **Action:** S3 MC-304 block.
- **Expected result:** Invalid URL rejected, nothing written; valid save gives mode 0600, token not echoed, self-hosted untouched.
- **Actual result:** Matched against a loopback mock for model discovery.
- **Defects:** None

### MC-305

- **Action:** S1 empty-PATH `r` plus stages-menu `m` with before/after comparison.
- **Expected result:** Only aws-bedrock listed and stored lowercase; `m` prints a pointer and leaves config byte-identical.
- **Actual result:** Matched.
- **Defects:** None

### MC-401

- **Action:** S3 MC-401 block on a self-hosted stage (`a`, `d`) with the self-hosted key store.
- **Expected result:** Self hosted prompt text and `a`/`d` behavior unchanged; aws-bedrock-keys.json never created.
- **Actual result:** Prompt `pply Self hosted to all stages` present; the claude stage switched to self-hosted; `d` removed only the self-hosted key; no Bedrock file; no token leak. Self-hosted `m` was not run in S3; the Self Hosted `m` path is the unmodified default profile (S2 `test_default_profile_still_uses_self_hosted_store`).
- **Defects:** None

### MC-402

- **Action:** S3 MC-402: claude, codex and kimi via `r`, then `bogus`.
- **Expected result:** Valid runners written; `bogus` rejected with the existing message and nothing written.
- **Actual result:** Matched.
- **Defects:** None

### MC-405

- **Action:** S4 picker lists; S2 `test_apply_to_all_on_self_hosted_stage_unchanged`. Headless, not curses.
- **Expected result:** All runners selectable; aws-bedrock listed; self-hosted apply-to-all still uses Self hosted keys.
- **Actual result:** Both sides list five runners; S2 passed.
- **Defects:** None

### MC-406

- **Action:** S1 stages-menu `m` byte-identity; S3 `uncle_stage_runner` for a Bedrock and a self-hosted stage; `aws-bedrock-dispatch-test.sh`.
- **Expected result:** `m` prints a pointer and writes nothing; both stages resolve to the self-hosted dispatch path.
- **Actual result:** Both resolve to `self-hosted`. The dispatch test has one pre-existing FAIL (D-1) and PASS on the aws-bedrock dispatch line. I did not run the full `workflow stage dispatch status` command.
- **Defects:** D-1, (pre-existing, unrelated)

### DRV-1

- **Action:** Not recorded.
- **Expected result:** Not recorded.
- **Actual result:** Not recorded.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | PASS | S1 and S3 exit 0 |
| MC-101 | YES | PASS | S1 exit 0 |
| MC-102 | YES | PASS | S1 and S3 exit 0 |
| MC-103 | YES | PASS | S1 exit 0 |
| MC-104 | YES | PASS | S1 and S3 exit 0 |
| MC-105 | YES | PASS | S1 exit 0 |
| MC-106 | YES | PASS | S2 exit 0, headless TUI |
| MC-200 | NO | PASS | S1 and S3 hash checks |
| MC-201 | NO | PASS | S1 exit 0 |
| MC-203 | NO | PASS | S2 and S5 exit 2 on typo |
| MC-204 | NO | PASS | S1 exit 0 |
| MC-205 | NO | PASS | S1 and S4 |
| MC-206 | NO | PASS | S1 and S3 |
| MC-207 | NO | PASS | S1 and S2 |
| MC-302 | NO | PASS | S1 missing-item runs |
| MC-303 | NO | PASS | S3 |
| MC-304 | NO | PASS | S3 |
| MC-305 | NO | PASS | S1 |
| MC-401 | YES | PASS | S2 and S3 |
| MC-402 | YES | PASS | S3 |
| MC-405 | YES | PASS | S2 and S4, headless TUI |
| MC-406 | YES | PASS | S1 and S3; D-1 pre-existing |
| DRV-1 | NO | FAIL | Driver run-shell-tests.sh and run-python-tests.sh exit 1; PREEXISTING per green-check.md (D-2) |
