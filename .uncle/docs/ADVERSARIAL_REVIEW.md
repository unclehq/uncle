## AR-001: Plan does not say how unknown-key detection treats the 'runner'/'model' fallback and the case when ALL supervision keys

- Severity: HIGH
- References: CHANGE_SPEC B-1/section 8 'Duplicate keys: first wins'; supervisor.py load_config adds key to `seen` before parse. Decision needed: 'An unknown key appearing N times yields exactly one warning; an empty key name `supervision.` is treated as unknown and warned.'
- Failure: Plan does not say how unknown-key detection treats the 'runner'/'model' fallback and the case when ALL supervision keys are unknown or the key is bare (e.g. 'supervision.' with empty name) or a duplicate unknown key. Warning count/dedup is unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: B-7/AC-5 say the notice prints 'once' at supervised-run start, but config reload (reload_config) re-reads the file mid-r

- Severity: HIGH
- References: supervisor.py:991-1009 reload_config calls load_config; plan D-3 only calls config_notices at entry (~1816). State: 'reload_config emits no stderr notices; only the entry call prints, exactly once per process start.'
- Failure: B-7/AC-5 say the notice prints 'once' at supervised-run start, but config reload (reload_config) re-reads the file mid-run and can newly produce warnings or errors; plan is silent on whether reloads print warnings/disabled reasons, and how 'once' is defined across reloads and resumed runs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Non-hosted (interactive) supervised runs with warnings are unspecified: D-3 prints warnings at entry (all warnings) but

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 'returning stderr lines: all warnings; plus disabled_reason when hosted' vs CHANGE_SPEC B-7 trigger 'with UNCLE_HOSTED=1'. Decide: 'Warnings print at run entry in both hosted and non-hosted modes; disabled_reason prints only when hosted.' (or hosted-only for both).
- Failure: Non-hosted (interactive) supervised runs with warnings are unspecified: D-3 prints warnings at entry (all warnings) but B-7 and AC-5 scope the stderr print to UNCLE_HOSTED=1 only, and the 'hosted' disabled_reason is gated while warnings are not.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: CLI `config` with errors AND warnings: ordering/streams and whether warnings are printed when exit is 1 are unspecified;

- Severity: MEDIUM
- References: supervisor.py:1923-1929 prints lines then disabled_reason; AC-4 covers only warnings-only and errors-only. State: 'With both, stdout lines, then each warning, then disabled_reason on stderr, exit 1.'
- Failure: CLI `config` with errors AND warnings: ordering/streams and whether warnings are printed when exit is 1 are unspecified; also `lines` output on stdout when disabled.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Warning text embeds the key name verbatim from the config file; key names may contain control characters/newlines-free b

- Severity: MEDIUM
- References: CHANGE_SPEC section 10 and R-3 'message key only'; read_config_lines takes parts[0] unvalidated. Decide: 'Key names are truncated to 64 characters and redacted via the existing redact() when matching secret patterns.'
- Failure: Warning text embeds the key name verbatim from the config file; key names may contain control characters/newlines-free but arbitrary long or secret-like tokens (e.g. 'supervision.sk-...'), contradicting the 'never echo secrets' rationale and unbounded length is unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Existing parse_value still raises 'unknown supervision key', and the retained roundtrip test/other consumers (e.g.

- Severity: LOW
- References: supervisor-test.py:925,930-932 loops assert errors, disabled_reason and values default. State: 'For bogus key: errors==[], disabled_reason=="", warnings==["ignoring unknown supervision key: supervision.bogus"], values equal DEFAULTS.'
- Failure: Existing parse_value still raises 'unknown supervision key', and the retained roundtrip test/other consumers (e.g. TUI writing keys, status) may rely on that; plan says test expectation of ('bogus','1') changes but doesn't say what the replaced assertion checks for values/disabled_reason when the file contains only an unknown key.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: reload_config also calls load_config mid-run, but the plan never says whether warnings or errors print on reload.

- Severity: HIGH
- References: supervisor.py:991-1009 reload_config; plan D-3 names only run entry (~1816) and CLI config. B-7 says 'printed once'.
- Failure: reload_config also calls load_config mid-run, but the plan never says whether warnings or errors print on reload. Add: 'reload_config prints nothing to stderr; config_notices runs only at run entry and in the CLI config action.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The hosted notice is unspecified for errors from _hosted_defaults (missing model) and for ordering relative to warnings.

- Severity: MEDIUM
- References: supervisor.py:242 appends the hosted missing-model error; D-3 and B-7 don't specify ordering or this case.
- Failure: The hosted notice is unspecified for errors from _hosted_defaults (missing model) and for ordering relative to warnings. Add: 'Hosted notices are warnings in file order, then disabled_reason if errors is non-empty, one stderr line each, including the missing-model error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan doesn't say whether unknown keys enter `seen`, which drives runner/model fallback and _hosted_defaults.

- Severity: MEDIUM
- References: supervisor.py:205-212 adds key to seen before parse_value; _hosted_defaults reads seen at line 231. D-1 says only 'skip keys not in KINDS'.
- Failure: The plan doesn't say whether unknown keys enter `seen`, which drives runner/model fallback and _hosted_defaults. Add: 'Unknown keys are not added to seen and do not affect runner or model fallback; duplicate unknown keys warn once.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The plan doesn't say warnings stay out of stdout and Config.lines, nor the exit code for mixed warnings and errors.

- Severity: MEDIUM
- References: supervisor.py:1925-1929 prints lines to stdout and the reason to stderr; the plan says 'lines output unchanged' only in the B-6 row.
- Failure: The plan doesn't say warnings stay out of stdout and Config.lines, nor the exit code for mixed warnings and errors. Add: 'Warnings go only to stderr, never to Config.lines or stdout; exit is 1 if any error exists, else 0.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The plan doesn't say how the roundtrip test changes beyond 'replaced by a warning assertion'.

- Severity: LOW
- References: supervisor-test.py:923-932 asserts loaded.errors for ('bogus','1'); plan section 10 is the only mention.
- Failure: The plan doesn't say how the roundtrip test changes beyond 'replaced by a warning assertion'. Add: 'The bogus case is removed from the error loop and asserted separately as warning-only with values equal to the defaults.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan says warnings omit the value but not whether the key text is sanitized; the key comes raw from the file and is prin

- Severity: HIGH
- References: CHANGE_SPEC AC-2 and section 10 say 'key only'; supervisor.py:172-173 takes parts[0] unfiltered from the file.
- Failure: Plan says warnings omit the value but not whether the key text is sanitized; the key comes raw from the file and is printed to stderr, so control or ANSI characters could inject into hosted logs. Decision: warnings print the key only after restricting it to [A-Za-z0-9._-], truncated to 64 chars, other characters replaced with '?'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The hosted notice prints disabled_reason, which embeds error text.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 prints disabled_reason; supervisor.py:195 joins errors; secrets machinery at supervisor.py:247-270 is not referenced in the plan.
- Failure: The hosted notice prints disabled_reason, which embeds error text. The secret-safety rule covers values only, so the plan never says printed text is redacted. Decision: config_notices passes every line through redact() with known_secret_values(environ), and no message contains a config value.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The plan does not say how credential-like unknown keys such as supervision.api_key or supervision.base_url are treated;

- Severity: MEDIUM
- References: CHANGE_SPEC non-goal 'Supporting base_url/api_key keys' and AC-7 docs; no test requirement that a secret-like value is absent from stderr.
- Failure: The plan does not say how credential-like unknown keys such as supervision.api_key or supervision.base_url are treated; users may put real secrets there and the plan only warns. Decision: the warning names only the key, and the docs tell users not to put credentials in .uncle/config. A test must show a secret-like value never appears on stderr.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Unspecified duplicate unknown keys and warning volume: it is unclear whether a repeated or numerous unknown key emits on

- Severity: LOW
- References: CHANGE_SPEC section 8 'Duplicate keys: first wins'; load_config seen-set at supervisor.py:206-208 skips duplicates before parse.
- Failure: Unspecified duplicate unknown keys and warning volume: it is unclear whether a repeated or numerous unknown key emits one warning or many. Decision: emit one warning per distinct unknown key and cap the list at 20 lines with a '... and N more' line.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Hosted notice 'once before the command' has no defined hook or count rule.

- Severity: HIGH
- References: CHANGE_PLAN D-3, AC-5; supervisor.py:991-1009 reload_config reloads config and could re-warn.
- Failure: Hosted notice 'once before the command' has no defined hook or count rule. Settle: 'config_notices prints exactly once per process at run entry before the first stage starts; reload_config never reprints; tests assert one stderr occurrence.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Non-hosted runs with warnings/errors unspecified: D-3 prints warnings always but B-7 is hosted-only.

- Severity: HIGH
- References: CHANGE_PLAN D-3 vs CHANGE_SPEC B-7 trigger.
- Failure: Non-hosted runs with warnings/errors unspecified: D-3 prints warnings always but B-7 is hosted-only. Settle: 'Non-hosted supervised runs print nothing at entry; hosted runs print warnings then disabled_reason.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Duplicate or odd unknown keys unspecified.

- Severity: MEDIUM
- References: CHANGE_SPEC section 8 duplicates first-wins; supervisor.py:203-211.
- Failure: Duplicate or odd unknown keys unspecified. Settle: 'One warning per distinct unknown key in file order; duplicates get no second warning; key text is the part after supervision. verbatim.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: No-value-echo is untestable as written.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2, section 10; CHANGE_PLAN R-3.
- Failure: No-value-echo is untestable as written. Settle: 'Test uses a sentinel value and asserts it appears in none of stdout, stderr or warnings.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Unclear whether skipped unknown keys enter `seen`, affecting runner fallback and ordering vs hosted errors.

- Severity: MEDIUM
- References: supervisor.py:204-224 seen.add precedes parse_value; CHANGE_PLAN D-1.
- Failure: Unclear whether skipped unknown keys enter `seen`, affecting runner fallback and ordering vs hosted errors. Settle: 'Unknown keys are not added to seen and never affect runner/model fallback.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: CLI output with errors plus warnings, and closed-stderr swallowing, have no AC.

- Severity: LOW
- References: supervisor.py:1923-1929; CHANGE_PLAN section 12.
- Failure: CLI output with errors plus warnings, and closed-stderr swallowing, have no AC. Settle: 'Warnings print first then disabled_reason to stderr, exit 1; closed stderr never changes the exit code.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
