# Change Plan — Issue 180
Omitted sections: Schema/persistence (none); Migration (none); Concurrency (interactive single process); Feature flag (none; additive)

Seeded from [unclehq/uncle#180](https://github.com/unclehq/uncle/issues/180).

Issue 180

## 1. Selected technical approach

D-1: Keep shell dispatch normalization untouched. In the `uncle` fallback use `uncle_raw_stage_runner` to detect a Bedrock stage and a new additive helper `uncle_selectable_runners` (installed + `aws-bedrock`, mirrors TUI `selectable_runners`) for the prompt. The helper prints one runner per line in `uncle_installed_runners` order, then `aws-bedrock` last; the prompt lists them in that order, space-separated. Prompt input is lowercased before matching and the lowercase value is what is written (input `AWS-Bedrock` is stored as `aws-bedrock`). With zero installed binaries (empty PATH) the helper and prompt list only `aws-bedrock`, and selecting it succeeds; the unchanged `uncle_no_runner` error (stage-config.sh:294,316) is not reached by the configure picker.
D-2: Extend `self_hosted.py` CLI with an optional profile argument: `models <config> [aws-bedrock]`, `choose-model <config> [aws-bedrock]`, `set-key <config> <stage> [aws-bedrock]`; omitting it is byte-identical to today.
D-3: Generalize TUI `_apply_opencode_to_all_stages` over `HTTP_RUNNERS`, using `_keys_for(runner)` for the token store and runner-specific notice text.
D-4: Menu: add item 3 "Configure AWS Bedrock"; Miscellaneous becomes 4 (matches TUI order).
D-5: Tests extend existing style; new hyphenated Python test, new shell test (asserting runner order, lowercase normalization of `AWS-Bedrock`, and the empty-PATH case); existing dispatch test untouched.

D-6 (runner prompt order, AR-005): `uncle_selectable_runners` prints the `uncle_installed_runners` output in its existing order (claude, codex, kimi, self-hosted when opencode is installed), then `aws-bedrock` last. With zero installed CLIs it prints only `aws-bedrock`, and selecting it succeeds (the unchanged no-runner error at stage-config.sh:316 is not reached by the configure prompt). Prompt input is lowercased before matching and the lowercase value is written.

## 2. Alternatives
(a) Make `uncle_installed_runners` include aws-bedrock — rejected: it feeds default-runner selection and no-runner error (stage-config.sh:103,316), changing unrelated behavior. (b) Remove Bedrock normalization — rejected: workflow drivers rely on `self-hosted` (INV-2).

## 3. Why preferred
Smallest surface, additive, no change to dispatch or key stores.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`scripts/lib/self_hosted_http.py`, `bedrock_protocols.py`, `stagegate.sh`, `change-workflow.sh`, `uncle_installed_runners`, `scripts/tests/aws-bedrock-dispatch-test.sh`, `aws-bedrock-test.py`, `aws-bedrock-protocols-test.py`.

## 6. Data flow

Fallback `m`: `self_hosted.py choose-model <config> aws-bedrock` -> stdout model -> `config_set <stage>.model`. `m` writes ONLY `<stage>.model`; the global `aws-bedrock.model` key is never modified by any configure action (it remains only a read-time fallback in uncle_stage_model), and the shell test asserts that global line is byte-identical after `m`. Fallback `a` (apply-to-all): the stage set 'all' is the explicit list of stage names used by the TUI apply-to-all (the same `STAGES` list the TUI iterates, not any stage inferred from other keys). The shell copies runner/model/base_url to every stage in that list in the config, then calls `self_hosted.py apply-all <config> aws-bedrock <source-stage>`. That subcommand copies the source stage's token entirely inside Python (read_keys/save_keys with profile=aws-bedrock) so that for each stage S in the list, keys[S]=<token> in aws-bedrock-keys.json (top-level key = stage name, value = the token string, same layout as the TUI `_keys_for(aws-bedrock)` store). The token never passes through shell variables, argv, env, stdout or stderr. After the action the set of stage keys in aws-bedrock-keys.json is exactly that explicit stage list (plus any pre-existing non-stage metadata keys, unchanged). Tests use a sentinel token and assert exactly that key set, that each value equals the source token, and that the sentinel appears in no captured stdout/stderr.

Apply-to-all (`a`) rule: it overwrites runner, model and base_url on every stage in the config, including stages currently on non-HTTP runners such as claude or codex. It replaces each affected stage's entry in aws-bedrock-keys.json, discarding any stale per-stage Bedrock key. It leaves self-hosted-keys.json byte-identical. The aws-bedrock-keys.json key set afterwards is exactly the stages switched by this action. Fallback `a` failure path: before any write, validate the source stage's Bedrock settings (token in aws-bedrock-keys.json, model, base_url). If any of the three is missing, `a` prints a Bedrock-worded error to stderr naming the missing item (never the token), exits without writing `.uncle/config`, aws-bedrock-keys.json or self-hosted-keys.json, and the `continue` loop keeps the menu running. Validation completes before the first write, so there is no partial apply.

## 8. Interface changes

Optional trailing profile arg on three `self_hosted.py` subcommands (D-2), plus a new subcommand `apply-all <config> aws-bedrock <source-stage>` (D-2): it copies the source stage's Bedrock token to the target stages' entries in aws-bedrock-keys.json inside Python, with no token on argv, env, or output. No config format change.

Profile validation: one shared function validates the profile for every subcommand (including apply-all). An absent profile argument selects the Self hosted store (unchanged); exactly `aws-bedrock` selects the Bedrock store; any other value (e.g. a typo such as `aws-bedrok`) exits non-zero with an error on stderr, writes nothing, never falls back to the Self hosted store (INV-1), and leaves both key files byte-identical.

Choose-model for `choose-model <config> aws-bedrock`: names are matched exactly as stored in the Bedrock key store (no `local_model()` / `local/` prefixing, no `openai/` stripping); on an unknown name, blank choice, EOF, or empty model list it exits non-zero with a Bedrock-worded message on stderr (no OpenCode wording) and prints nothing to stdout; on success it prints only the matched model name.

Model carry-over on runner switch (AR-003): switching a stage's runner to aws-bedrock keeps the stage's existing `<stage>.model` unchanged and unvalidated (no clearing, no check against the Bedrock list); the stale model is only replaced when the user runs `m`, which validates against the key store of the stage's current runner. Documented in docs/aws-bedrock.md.

## 10. Compatibility

Default-profile calls unchanged; Self hosted prompts text unchanged for Self hosted stages. Stages-menu list display: the raw runner is shown only when it equals aws-bedrock; opencode and aider (and self-hosted) stages still display as self-hosted exactly as today.

## 12. Error and recovery
Per spec section 8; failures write nothing; `continue` loop keeps the menu running.

## 14. Rollback plan
Revert the commit; no persisted state changes (aws-bedrock-keys.json format unchanged).

## 16. Automated-test strategy

New `scripts/tests/aws-bedrock-configure-test.sh` (fallback: AC-1,2,3, plus menu mapping for AC-4: input 3 opens Configure AWS Bedrock with no confirmation, input 4 opens Miscellaneous, input 5 prints the existing invalid-choice message and writes nothing). New `scripts/tests/aws-bedrock-configure-test.py` (AC-3 TUI, AC-4 CLI profile arg, AC-6 cross-surface). All run via the existing runners (hyphenated name collected). Runner-prompt assertions in the shell test: the prompt lists installed runners in order then `aws-bedrock` last; input `AWS-Bedrock` is stored as `aws-bedrock` (lowercase) in `.uncle/config`. The shell test also asserts that switching a stage with an existing Self hosted model to aws-bedrock leaves `<stage>.model` byte-identical (kept, unvalidated, not cleared). The shell test must exercise the real shipped `uncle` functions, either by sourcing `uncle` through a source guard (owned by step 2) or by driving the script itself; an awk-extracted copy of a function is permitted only if the test also asserts that the extracted text is byte-identical to the corresponding text in `uncle`. Both new tests use a sentinel token and assert it is absent from stdout, stderr, .uncle/config and the recorded argv of every fallback action, including failing ones, while present only in aws-bedrock-keys.json. Defect-injection: the tests must fail on HEAD for BH-1/BH-3/BH-4/BH-5/BH-6 (the pre-change code rejects aws-bedrock and maps 3 to Miscellaneous), and that failure must come from the real `uncle` code, not a copy.

AC-6 oracle: the test writes a config through the real fallback (`uncle` configure_stage selecting aws-bedrock), then loads that file with the existing `uncle_tui.py` config reader and calls its stage-runner resolver (`stage_runner`) on the loaded values, asserting the result == `aws-bedrock` (and the model/base_url the TUI shows match the fallback-written ones). The test imports and calls that function from `uncle_tui.py`; it must not parse the config with its own ad hoc parser. The exact function name and signature are confirmed against the source at the start of step 4. That function is read-only for this change: step 3 does not modify it, so uncle_tui.py stays owned by step 3 alone (apply-to-all generalization only).

AR-016 / AR-019 assertion (shell and Python tests): apply-to-all sets keys[stage]=token for each enumerated stage. With a mixed-runner fixture and a sentinel token, after apply-to-all the set of stage keys in aws-bedrock-keys.json equals exactly (set equality, not subset or truthiness) the explicit list of stages this action switched to aws-bedrock, each value equals the source token, and self-hosted-keys.json is byte-identical. Both the shell fallback `a` test and the TUI apply-to-all test make this comparison.

Model carry-over rule (AR-007): changing a stage's runner to or from aws-bedrock leaves `<stage>.model` unchanged and unvalidated (never cleared, never rewritten). `m` validates the choice against the key store of the stage's current runner (aws-bedrock-keys.json for aws-bedrock stages, self-hosted-keys.json otherwise). The new shell test asserts, for both directions (self-hosted to aws-bedrock and aws-bedrock to self-hosted), that `<stage>.model` is byte-identical before and after the runner switch, and that a following `m` offers and accepts only models from the current runner's store.

Apply-to-all failure test (AR-001): in `aws-bedrock-configure-test.sh`, three cases where the source Bedrock stage lacks (a) the token, (b) the model, (c) the base_url. Each asserts a Bedrock-worded error on stderr, and that `.uncle/config`, aws-bedrock-keys.json and self-hosted-keys.json are byte-identical before and after (validate first, write nothing on failure). Sentinel token is absent from stdout and stderr. Traced under AC-3 and BH-4.

## 17. Regression-test strategy
Existing suites via the two baseline commands; dispatch test must still pass unmodified; Self hosted fallback `m`/`a`/`d` asserted unchanged in the new shell test.

## 18. Manual verification
Fallback walkthrough in a temp project with a fixture Bedrock keys file (no network): select aws-bedrock, `m`, `a`, `d`; then open the TUI Configure and confirm the same runner/model show. LIVE_VERIFICATION needs no credentials (model discovery not exercised).

## 19. Observability
None.

## Restrictions

| ID | source_kind | Source | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase | req IDs |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Out of scope | No change to wire protocols or discovery | Touch only profile-arg plumbing in self_hosted.py CLI | Scope | CAP-1 | self_hosted.py:1947-1982 inspected | CODING | BH-1..9 |
| R-2 | REPOSITORY | aws-bedrock-dispatch-test.sh | Dispatch unchanged | No edits to normalization lines | Existing test diffs vs HEAD | CAP-2 | stage-config.sh:311 inspected | CODING | INV-2, BH-8 |
| R-3 | REPOSITORY | self_hosted.py:33 | Separate key stores; the token never appears in stdout, stderr, .uncle/config or argv for any fallback action, including failures | Use `profile=aws-bedrock` for read/save keys; the apply-to-all token copy happens only inside `self_hosted.py apply-all`, never via shell variables, argv, env or output | Existing store design | CAP-1 | key_file inspected | CODING | INV-1, INV-5 |
| R-AR015 | DESIGN | AR-015 | Configure AWS Bedrock validates Base URL, redacts tokens, keeps key file private | The Bedrock connection setup path in self_hosted.py applies `_bedrock_url_ok` to the Base URL and rejects an invalid URL with a Bedrock-worded error, exit non-zero, writing nothing. All failure text passes through `redact_token`. `aws-bedrock-keys.json` is saved with mode 0600. | BH-6 left URL validation and failure redaction unspecified; an invalid URL or token-bearing error text would break INV-5. | CAP-1 | self_hosted.py:72 _bedrock_url_ok, :63 redact_token, :1960-1966 profile_menu takes URL unvalidated | CODING |  |
| R-5 | REPOSITORY | INV-5 | Bedrock token never in shell variables, argv, env or output during apply-to-all | Token copy is done only by `self_hosted.py apply-all <config> aws-bedrock` operating on aws-bedrock-keys.json | Prevents token leakage via shell | CAP-1 | AR-013 | CODING |  |
| R-4 | DESIGN | spec section 7 | Menu parity with TUI | Item 3 Bedrock, Misc 4 | Revisable DESIGN choice | CAP-2 | uncle:848 inspected | CODING | BH-6 |

CAP-1 python3 available; CAP-2 bash available (both used by existing suites). No live-authentication capability is needed.

## Audit of `self-hosted` special cases
| Site | Disposition |
|---|---|
| uncle:760,762,789,795,825,837,778,783 (configure_stage) | Extended to Bedrock |
| uncle:852 (menu item 2) | Self hosted only; item 3 added for Bedrock |
| uncle:887 (stages menu `m` = self-hosted models) | Intentionally Self hosted only (documented in docs) |
| uncle:875 (list shows normalized runner) | Extended: show raw runner |
| stage-config.sh:216,290,311,344,346 | Already Bedrock-aware; no change |
| stage-config.sh:330 effort default none | Covered via normalization; no change |
| stagegate.sh / change-workflow.sh `UNCLE_RESOLVED_RUNNER == self-hosted` | Covered via normalization; no change |
| uncle_tui.py:1418,1429 apply-to-all | Extended |
| uncle_tui.py:1230,1494-1497,1605 | Already Bedrock-aware |
| uncle_tui.py:1763-1780 per-stage connection/model migration | Intentionally Self hosted only: Bedrock models live in the Bedrock key store and have no per-stage base_url |
| uncle_tui.py:3356 status alias | Legacy opencode/aider alias only; Bedrock already reported as aws-bedrock; no change |

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle` | configure_stage + menu extended for Bedrock | BH-1..4,6,7,9 | Medium (Self hosted flow) | aws-bedrock-configure-test.sh |
| `scripts/lib/stage-config.sh` | Add `uncle_selectable_runners` only | D-1 | Low | dispatch test (unchanged), new shell test |
| `scripts/lib/self_hosted.py` | Optional profile arg for models/choose-model/set-key; new `apply-all` subcommand for in-Python Bedrock token copy | D-2 | Low | aws-bedrock-configure-test.py |
| `uncle_tui.py` | Generalize apply-to-all | BH-5 | Low | aws-bedrock-configure-test.py |
| `scripts/tests/aws-bedrock-configure-test.sh` | New | AC-1,2,3 | None | self |
| `scripts/tests/aws-bedrock-configure-test.py` | New; asserts sentinel token absent from stdout, stderr, .uncle/config and argv for all actions including failures | AC-3,4,6 | None | self |
| `docs/aws-bedrock.md` | Document fallback path and Self-hosted-only sites | AC-7 | None | grep |
| `README.md` | Add AWS Bedrock to runner lists (lines ~18, 142, 144) | AC-7 | None | grep |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: the fallback runner prompt lists installed runners in `uncle_installed_runners` order followed by `aws-bedrock` last, and accepts aws-bedrock case-insensitively, storing it lowercase. | BH-1, BH-9 | INV-3 | uncle, stage-config.sh | configure-test.sh (incl. model unchanged after switch to aws-bedrock; prompt order: installed runners then aws-bedrock; empty-PATH case lists only aws-bedrock and selecting it succeeds) | fallback walkthrough |
| AC-2 | BH-2, BH-3, BH-7 | INV-1 | uncle, self_hosted.py | configure-test.sh | fallback walkthrough |
| AC-3 (apply-to-all): apply-to-all sets runner/model/base_url on every stage in the explicit stage list and writes keys[stage]=token in aws-bedrock-keys.json for exactly those stages (the stages this action switches to aws-bedrock); after apply-to-all the stage keys in aws-bedrock-keys.json are exactly that set. The Bedrock token is never written to self-hosted-keys.json, which is untouched. | BH-4, BH-5 | INV-1, INV-5 | uncle, uncle_tui.py | configure-test.sh/.py, configure-test.py mixed-runner fixture (claude, codex, self-hosted and aws-bedrock stages, some with stale Bedrock keys): after `a`, every stage is aws-bedrock with runner/model/base_url overwritten, each Bedrock key entry replaced, and self-hosted-keys.json byte-identical, configure-test.py sentinel-token test: for apply-all and every fallback action, including failing ones, the sentinel token is absent from stdout, stderr, .uncle/config and recorded argv of a stubbed invocation, and present only in aws-bedrock-keys.json | TUI apply-to-all |
| AC-4 | BH-6 | INV-1 | uncle, self_hosted.py | configure-test.py (incl. invalid-profile rejection for models, choose-model, set-key: bad profile e.g. aws-bedrok, with a sentinel token for set-key, exits non-zero and leaves self-hosted-keys.json and aws-bedrock-keys.json byte-identical), configure-test.sh (menu mapping: 3 -> Configure AWS Bedrock, 4 -> Miscellaneous, 5 -> invalid choice; stages-menu `m` on a Bedrock stage prints pointer message and leaves .uncle/config byte-identical) | Configure menu item 3 |
| AC-5 | BH-8 | INV-2, INV-3 | all | existing suites | none |
| AC-6 | BH-2 | INV-4 | audit table, tui | configure-test.py (AC-6 calls the uncle_tui.py `stage_runner` reader on a fallback-written config and asserts == aws-bedrock) | cross-surface check |
| AC-7 | n/a | n/a | docs, README | grep | read docs |

AR-015 tests (aws-bedrock-configure-test.py, BH-6/AC-4, INV-1/INV-5): (1) an invalid Base URL (non-http scheme, no host, embedded credentials, query or fragment) is rejected with a non-zero exit and a Bedrock-worded message, and both key files and .uncle/config are byte-identical; (2) with a sentinel token, failure output on stdout and stderr does not contain the token; (3) after a successful save, aws-bedrock-keys.json has mode 0600 and self-hosted-keys.json is unchanged.

AR-021 tests (aws-bedrock-configure-test.py/.sh): `d` on a Bedrock stage with no stored key exits 0 and aws-bedrock-keys.json is byte-identical (or absent stays absent); `set-key ... aws-bedrock` with empty stdin removes only the named stage's key and leaves other stage keys and self-hosted-keys.json byte-identical.

Bug-style regression: BH-1 test (aws-bedrock accepted at fallback prompt) fails on HEAD and passes after.

## Implementation sequence

1. self_hosted.py profile argument for `models`, `choose-model`, `set-key` (default unchanged; Bedrock uses read_keys/save_keys with profile, Bedrock-worded messages). Shared profile validator: one function called before any read or write by all three subcommands; only absent or `aws-bedrock` accepted; any other value exits non-zero, writes nothing, and never falls back to the Self hosted store. Bedrock `choose-model` matches names exactly as stored without local_model(); an unknown, blank, EOF or empty-list choice exits non-zero with a Bedrock-worded stderr message and empty stdout; a stored name lacking the local/ prefix is valid and accepted as-is. Tests (configure-test.py) cover each case: empty list, EOF, blank choice, unknown name, no-prefix stored name, and invalid profile for models, choose-model and set-key. Bedrock key removal: `set-key <config> <stage> aws-bedrock` with empty stdin removes only that stage's entry from aws-bedrock-keys.json (fallback `d` uses this path); `d` with no stored key exits 0 and leaves aws-bedrock-keys.json byte-identical (no file created or rewritten when the key is absent). Other stages' keys and self-hosted-keys.json are never touched. Also new subcommand `apply-all <config> aws-bedrock <source-stage>` that copies the source stage's Bedrock token to each target stage's entry in aws-bedrock-keys.json inside Python only (nothing on argv, env or output; non-zero exit and no write if the source token is missing); it uses the same shared profile validator.
   Owns: `scripts/lib/self_hosted.py`
2. Shell fallback: `uncle_selectable_runners` helper (installed runners in uncle_installed_runners order, then aws-bedrock; only aws-bedrock when none installed, per D-6), configure_stage (raw runner, prompt, m, a, d, display), menu item 3, stages-menu display. `m` in per-stage configure writes only `<stage>.model` and never `aws-bedrock.model`; the shell test (step 4) asserts the `aws-bedrock.model` line in .uncle/config is byte-identical before and after `m`. Stages-menu `m` on a Bedrock stage prints a message pointing to per-stage configure and writes nothing. Stages-menu display shows `aws-bedrock` only for stages whose raw runner is aws-bedrock; opencode/aider keep displaying as self-hosted (asserted in the shell test). Fallback `a` sets runner/model/base_url in config, then calls `self_hosted.py apply-all <config> aws-bedrock <source-stage>` for the token; the shell never reads, stores or passes the token. If the shell test needs to source `uncle` to call its real functions, this step also owns adding the minimal source guard to `uncle` (the main flow runs only when executed directly, unchanged behavior otherwise). Relies on step 1's CLI contract (D-2) but not its code, so may run in parallel with step 1.
   Owns: `uncle`, `scripts/lib/stage-config.sh`
3. TUI apply-to-all generalization
   Owns: `uncle_tui.py`
4. Tests: shell and Python tests per section 16. The shell test must run the real `uncle` functions (source via the guard added in step 2, or drive the script). An awk-extracted copy is allowed only if the test asserts the extracted text matches the corresponding text in `uncle`. Step 4 must not edit `uncle`. The shell test also asserts the menu mapping: input 3 opens Configure AWS Bedrock, input 4 opens Miscellaneous, input 5 prints the existing invalid-choice message (traced to BH-6 / AC-4). configure-test.py includes an invalid-profile case: `models`, `choose-model` and `set-key` with an unknown profile (e.g. `aws-bedrok`, with a sentinel token on stdin for set-key) exit non-zero and leave both self-hosted-keys.json and aws-bedrock-keys.json byte-identical (or both absent). For AC-6, first confirm the exact name/signature of the existing `uncle_tui.py` stage-runner config reader (`stage_runner`), then have the Python test call that real function on the fallback-written config and assert aws-bedrock; step 4 only imports it and does not edit uncle_tui.py (owned by step 3, which does not modify that reader).
   Owns: `scripts/tests/aws-bedrock-configure-test.sh`, `scripts/tests/aws-bedrock-configure-test.py`
   Depends on: 1, 2, 3
5. Docs: `docs/aws-bedrock.md`, `README.md`
   
   Protected verification paths: `scripts/tests/aws-bedrock-dispatch-test.sh`, `scripts/tests/aws-bedrock-test.py`, `scripts/tests/aws-bedrock-protocols-test.py`, plus the two new test files. Verification commands: the two commands in BASELINE_REPORT.
   Owns: `docs/aws-bedrock.md`, `README.md`

## 21. Scope cuts under time pressure
Cut first: menu item 3 / Bedrock connection setup in the fallback (BH-6, AC-4), then the TUI apply-to-all (BH-5), then README edits. Last to cut: BH-1 and BH-3/BH-4 in the fallback.

## 22. Risks

- Menu renumbering (Misc 3 -> 4) could affect scripted users; accepted, documented risk (matches TUI order; Decision D-4, revisable). Defined behavior: input 3 opens Configure AWS Bedrock with no confirmation prompt (a stale scripted old '3' therefore opens Bedrock setup, not Miscellaneous), input 4 opens Miscellaneous, and any other number (e.g. 5) prints the existing invalid-choice message and changes nothing. The shell test asserts all three mappings (3 Bedrock, 4 Miscellaneous, and an out-of-range input such as 5 rejected).
- `uncle` may not be sourceable in tests; handled by a source guard owned by step 2 (step 4 depends on it), or by driving the script; a copied function body is allowed only with a test assertion that it matches the file text.
- Self hosted prompt text and stages-list display must stay identical for Self hosted stages, including legacy opencode and aider stages (still shown as self-hosted); the new shell test asserts a Bedrock stage lists as aws-bedrock while opencode and aider stages list as self-hosted.
- A stage switched to or from aws-bedrock keeps its previous model unvalidated (AR-003, AR-007), so a Self hosted model name may sit on a Bedrock stage (or vice versa) until the user runs `m`; accepted, documented in docs/aws-bedrock.md, and asserted by the shell test for both switch directions.
- Stages-menu `m` (Self hosted models, uncle:887) on a stage whose raw runner is aws-bedrock prints a message pointing the user to per-stage Configure (item 2/3 path) and writes nothing: no Self hosted model discovery, no write to .uncle/config or self-hosted-keys.json (INV-1). The new shell test asserts the pointer message and that .uncle/config is byte-identical before and after.
- Bedrock-only machine (no runner binaries on PATH): the picker must list only aws-bedrock and accept it; the shell test runs configure_stage with an empty runner PATH and asserts this (AR-010).

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Apply-to-all had no defined failure path for an incomplete Bedrock key store; a partial write would leave stages unusable. | Section 6 (data flow) gains a validate-first, write-nothing failure rule; section 16 gains a test for missing token, model or base_url. |
| AR-002 | Accepted | stage-config.sh:344-346 falls back to the global aws-bedrock.model, so writing that key would silently change every Bedrock stage. | Section 6 and step 2 state `m` writes only <stage>.model and never aws-bedrock.model; the shell test must assert the global line is byte-identical. |
| AR-003 | Partially accepted | Documenting that the model is kept unvalidated is accepted; clearing or validating on switch is rejected because a runner switch is a plain change, consistent with the AR-007 carry-over rule. | Added a model-carry-over rule to s7.1, a test assertion to s11.1, a risk note to s21, and extended AC-1 traceability tests. |
| AR-004 | Accepted | Stale scripted input after renumbering needs a defined outcome; renumbering is kept as an accepted, documented risk matching TUI order. | Section 22 risk i1 now states: item 3 opens Configure AWS Bedrock without confirmation, 4 opens Miscellaneous, other numbers show the existing invalid-choice message. |
| AR-005 | Accepted | Prompt order and the zero-installed-CLI case were unspecified and the Bedrock-only machine is a core use case. | D-1 (s1.1) gains order/zero-CLI rule; step-2 text and AC-1 row require tests for both cases. |
| AR-006 | Accepted | Stages-menu `m` is Self hosted only while the list now shows aws-bedrock stages; behavior on a Bedrock stage must be defined to protect INV-1. | Added rule to the audit/risks: stages-menu `m` on a Bedrock stage prints a pointer to per-stage configure and writes nothing; shell test added in step 2/AC-4 trace. |
| AR-007 | Accepted | A model carry-over rule is needed so Self hosted and Bedrock model names are never silently validated or cleared on runner switch, and `m` must use the current runner's store. | Add a model carry-over rule to section 16 and risks (s21), plus tests for both switch directions and `m` validation against the current runner's store. |
| AR-008 | Accepted | Menu renumbering changes scripted input meaning, so the mapping needs an owned automated test traced to BH-6. | Step 4 and section 16 add menu-mapping assertions (3 Bedrock, 4 Miscellaneous, 5 invalid); AC-4 traceability lists them; risk i1 updated. |
| AR-009 | Accepted | Apply-to-all scope for non-HTTP runners and existing per-stage keys was undefined; a single overwrite rule removes the ambiguity. | Section 6 states the overwrite rule; AC-3 gains a mixed-runner test case asserting every stage ends aws-bedrock and self-hosted-keys.json is byte-identical. |
| AR-010 | Accepted | The zero-installed-CLI case is the primary Bedrock-only use case and was unspecified and untested. | D-1 states the empty-PATH rule and order; shell test step and risk list gain the empty-PATH case. |
| AR-011 | Accepted | Showing the raw runner for every stage would regress opencode/aider display and contradict the Compatibility promise. | Compatibility (s8.1), step-2 and risk s21.1.i3 now state the list shows aws-bedrock only for Bedrock stages, opencode/aider still self-hosted, asserted in the shell test. |
| AR-012 | Accepted | A mistyped profile would silently write the Self hosted store, breaking INV-1; one shared validator is cheap. | Section 8 (s7.1) states the profile validation rule; step-1 owns it; step-4 tests it for models, choose-model and set-key. |
| AR-013 | Accepted | The plan named no mechanism for moving the Bedrock token during fallback apply-to-all, so the shell could route it through variables or argv and break INV-5. | Adds D-2 subcommand `apply-all <config> aws-bedrock` copying the token inside self_hosted.py; edits s6.1, s7.1, step-1, step-2, AC-3, s17.1.r3, R-3; adds a sentinel-token test and a restriction row. |
| AR-014 | Accepted | An unvalidated profile argument could route a Bedrock token to self-hosted-keys.json, violating INV-1; one shared validator removes the risk. | Section 8 (s7.1) and step-1 now require one shared profile validator that exits non-zero, writes nothing and never falls back to the Self hosted store; AC-4 gains a bad-profile test. |
| AR-015 | Accepted | Bedrock connection setup must validate the Base URL and redact tokens so INV-5 and the 0600 key file mode are enforced and tested. | Added restriction R-AR015 in section 15 and a test-mapping block in Traceability (s18) for URL rejection, redaction and 0600 mode. |
| AR-016 | Accepted | Token scope on apply-to-all was ambiguous for stages on other runners; restricting it to stages switched by this action makes it testable. | Added AC-3 invariant/test text: aws-bedrock-keys.json keys are exactly the stages switched by apply-to-all; plus section 16 assertion. |
| AR-017 | Accepted | Token-absence assertions did not name stderr, argv or failure paths; a leak there would go undetected. | Strengthened R-3 and AC-3, the section 16 test strategy, and the s17.1.r6 test row to assert a sentinel token is absent from stdout, stderr, .uncle/config and argv for every fallback action, including failures. |
| AR-018 | Accepted | AC-6 needs a concrete oracle; without a named TUI reader the test could use an ad hoc parser and prove nothing about the TUI. | Section 16 gains an AC-6 oracle block naming the TUI stage-runner reader, AC-6 tests and step 4 text name it, and step 3 is stated not to modify it. |
| AR-019 | Accepted | The per-stage key layout and the set of stages counted as 'all' were undefined, so exact-key-set assertions were impossible. | Section 6 now defines apply-to-all as keys[stage]=token for each enumerated stage; AC-3 and test strategy assert exactly that key set. |
| AR-020 | Accepted | Bedrock choose-model error behavior was unspecified and could reuse local/ prefixing or OpenCode wording. | Section 8 (s7.1) gains the Bedrock choose-model rule; step-1 text states it and requires tests for each error case. |
| AR-021 | Accepted | Delete-key and empty-stdin outcomes for Bedrock were unspecified, so test oracles could disagree. | Step 1 text states the rules; AC-2 requirement/tests and s18.2 add asserted cases. |
| AR-022 | Accepted | An awk-extracted copy could pass or fail independently of the shipped `uncle`, invalidating defect-injection evidence. | Section 16, step 2 and step 4 now require the shell test to run the real `uncle` functions; a copy is allowed only if asserted equal to the file text; any source guard is owned by step 2. |
| AR-023 | Accepted | Prompt order, separator and case handling were unspecified and untestable; fixing them is cheap and removes drift risk. | D-1 (s1.1) and AC-1 state order and lowercase rule; section 16 (s11.1) adds shell-test assertions for order and AWS-Bedrock input. |
