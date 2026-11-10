# Change plan — Issue 226

Seeded from [unclehq/uncle#226](https://github.com/unclehq/uncle/issues/226).

Issue 226

Omitted sections: Schema (none); Migration (none); Concurrency (none); Feature flag (none, behavior is the fix); Observability (covered by stderr warnings)

## 1. Selected technical approach

D-1 In `load_config`, test `key not in KINDS` before the `seen.add(key)` line: unknown keys are skipped, are NOT added to `seen`, and never affect the `runner`/`model` fallback or `_hosted_defaults` (which read `seen`). Each unknown key appends an `unknown supervision key` text to a new `warnings` list instead of `errors`; duplicate unknown keys warn once (tracked in a separate set of unknown keys, not `seen`). Leave `parse_value` raising for direct callers.
D-2 `Config(values, errors, warnings)`; `warnings` attribute, default empty. Message omits the value.
D-3 Add pure helper `config_notices(config, environ)` returning stderr lines: all warnings; plus `disabled_reason` when hosted (`hosted.is_hosted`) and errors exist. Called once at the supervised-run entry (`supervisor.py:~1816`) before the command runs, and the CLI `config` action prints warnings to stderr.
D-4 Docs in README.md and docs/supervision.md. `.uncle/config.example` is untracked here and the build script is external: not changed (deviation recorded in IMPLEMENTATION_NOTES.md).

## 2. Alternatives
A: abort the run before the first paid stage on any config error. B: warn on stderr (chosen). A is a behavior change for interactive users and conflicts with 'keep supervision on'.

## 3. Why preferred
Smallest change, matches request options, preserves error semantics for recognized keys.

## 4. Components to modify
See Change-impact table.

## 5. Not to modify
`_hosted_defaults`, hosted.py, supervision.sh, uncle_tui.py, journal and worker logic.

## 6. Data flow
config file -> load_config -> Config(values, errors, warnings) -> notices to stderr (hosted or CLI). Status/TUI continue to read `disabled_reason` only.

## 8. Interfaces

`Config.warnings` added; CLI `config` stderr gains warning lines; exit code only 1 for errors. Unknown-key warning rule: `warnings` holds one entry per distinct unknown supervision key, in file order; a repeated unknown key gets no second warning (first wins, as for recognized keys). The key text is the part after `supervision.` verbatim, and a bare `supervision.` line (empty name) is treated as unknown and warned. Unknown keys never enter `seen` and never change `values`, runner/model fallback, or `_hosted_defaults`. Warning volume: `Config.warnings` holds at most 20 key warnings, followed when more exist by one line '... and N more' where N is the number of omitted distinct unknown keys.

## 10. Compatibility

All existing consumers read `errors`/`disabled_reason`; unchanged shape. The existing test case `('bogus','1')` in the roundtrip error loop expects an error and conflicts with the requirement; it is the one test change, authorized by the change request (item 1). It is removed from the error loop and asserted separately in the same test: a file containing only `supervision.bogus 1` loads with `errors == []`, `disabled_reason == ''`, `values` equal to `DEFAULTS`, and `warnings` containing one entry that names `supervision.bogus`.

## 12. Error and recovery

Recognized-invalid values: unchanged disable. Unknown key: warning only. CLI `config` with both warnings and errors: stdout lines unchanged, then each warning on stderr, then disabled_reason on stderr, exit 1; with warnings only, exit 0. Notice printing failures (closed or broken stderr) are swallowed and never change the exit code or abort the run.

## 14. Rollback
Revert the commit; no state.

## 16. Automated-test strategy

In `scripts/tests/supervisor-test.py` (already in critical-suites): unknown key ignored (AC-1, AC-2); unknown plus invalid recognized still disabled (AC-3); CLI exit codes/stderr (AC-4): warnings-only exits 0 with warnings on stderr; errors-only exits 1 with disabled_reason on stderr; AC-4b with both warnings and errors the CLI prints stdout `lines` first, then each warning on stderr, then disabled_reason on stderr, exits 1, and warnings never appear on stdout; hosted run notice (AC-5), using temp configs and a subprocess with `UNCLE_HOSTED=1`: run-entry notices (warnings, then disabled_reason) are emitted by config_notices exactly once per process at run entry before the first stage starts, and the test asserts one occurrence in stderr; a non-hosted run with an unknown key asserts nothing is printed to stderr at entry (the CLI `config` action always prints warnings regardless of hosting); a reload test rewrites the config mid-run (calls reload_config with a changed file) and asserts reload_config prints nothing and no additional stderr output appears. No-value-echo (AC-2, R-3): a config with an unknown key whose value is a unique sentinel string (e.g. `supervision.bogus SENTINEL-7f3a91`) is loaded and run through the CLI `config` action and the hosted run entry; the test asserts the sentinel appears in none of captured stdout, captured stderr, or `Config.warnings`. Fixtures use no git signing.

AR-002 test: start a supervised run with an unknown key, then change the config file (new unknown key / new invalid value) and trigger reload_config; assert stderr contains the entry notice exactly once and reload adds no stderr output, while reload still updates status/disabled_reason as before. AR-012 sanitization test: a config line whose key contains an ESC/ANSI sequence and non-ASCII characters yields a warning containing only [A-Za-z0-9._-] characters plus '?' substitutes (every other character is replaced with '?'); a key longer than 64 characters is truncated to 64; a sentinel value appears in no output.

## 17. Regression-test strategy
Regression test that fails before fix: AC-1 test (unknown key currently yields errors). Existing roundtrip, hosted-mode and default-runner suites cover B-2..B-5. Run the baseline commands.

## 18. Manual verification
Run `python3 scripts/lib/supervisor.py config --config <file with supervision.base_url x>` and `UNCLE_HOSTED=1` run wrapper; observe stderr warning and enabled supervision. Check README/doc text.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/supervisor.py` | warnings in Config/load_config, config_notices, entry and CLI printing | AC-1..AC-5 | Medium: gating on errors | supervisor-test.py, hosted-mode-test.py |
| `scripts/tests/supervisor-test.py` | replace bogus-key error case; add new tests | AC-1..AC-5 | Low | itself |
| `README.md` | hosted supervision env vars note; warn not to put credentials (api keys, base_url secrets) in .uncle/config | AC-7 | None | grep |
| `docs/supervision.md` | same note plus unknown-key behavior (warning names the key only, value never printed); do not put credentials in .uncle/config | AC-7 | None | grep |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| Request 1 | B-1, B-2 | I-1, I-2, I-5, I-6 | supervisor.py | AC-1..AC-3 tests, duplicate unknown key yields exactly one warning, bare `supervision.` yields one warning and no error, file with only unknown keys: values equal DEFAULTS, errors==[], unknown `supervision.runner`-adjacent key does not alter runner/model fallback | CLI config run |
| Request 2: hosted visibility. config_notices runs once per process at run entry, before the first stage, and is gated on hosted.is_hosted: non-hosted supervised runs print nothing at entry; hosted runs print warnings (file order) then disabled_reason (if errors) to stderr. reload_config prints nothing. The CLI `config` action prints warnings independently of hosted mode. Warnings go only to stderr, never to stdout or Config.lines; exit 1 iff errors exist, else 0. | B-6, B-7 | I-6 | supervisor.py | AC-4 (warnings-only exit 0; errors-only exit 1), AC-4b (both: stdout lines, then warnings, then disabled_reason on stderr, exit 1), AC-5 tests, including hosted missing-model case: warnings first, then disabled_reason line, AC-5 non-hosted: no stderr notice at entry with warnings present, reload test: notice appears exactly once; reload_config emits no stderr (config changed mid-run to add unknown key or invalid value) | hosted run |
| Request 3 | B-8 | none | README.md, docs/supervision.md | grep (AC-7), sentinel test: credential-like unknown key (e.g. supervision.api_key with a sentinel value) yields a key-only warning; the sentinel appears in none of stdout, stderr or warnings | read docs |
| Request 4 | n/a (external build script) | none | none | none | deviation noted |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST item 1 | AC-1, AC-3 | unknown ignored, invalid recognized still disables | skip KINDS-miss in load_config | minimal | CAP-py | supervisor.py:203-224 inspected | CODING |
| R-2 | USER | item 2 | AC-5 | hosted: warnings then disabled_reason visible exactly once before paid stage; non-hosted: no entry output; mid-run reloads add no stderr notices | config_notices called once per process at run entry, before the first stage, on stderr, only when hosted.is_hosted(environ); non-hosted entry prints nothing; CLI config always prints warnings; reload_config never prints | host reads stderr | CAP-py | supervisor.py:1816-1822 inspected | CODING |
| R-3 | DESIGN | spec section 10 | AC-2 | no value echoed: sentinel value appears in none of stdout, stderr or Config.warnings; key text bounded to 64 characters and redacted when it matches secret patterns | warning text contains the key name only, never the value; key name truncated to 64 characters, then the warning line passed through the existing redact() (with known_secret_values(environ)) so secret-matching key text prints as the redacted-line marker; test writes `supervision.<unknown> <sentinel>` and asserts the sentinel is absent | secrets safety: a key such as supervision.sk-... must not reach stderr verbatim, and key length is unbounded in the file; tests use a sentinel value plus a 200-character key and a secret-like key and assert the sentinel and full key appear nowhere in stdout, stderr or Config.warnings | CAP-py | message built from key | CODING |
| R-4 | DESIGN | AR-012 | AC-2 | warning key text cannot inject control or ANSI characters into stderr | warning builder passes the key through a sanitizer: characters outside [A-Za-z0-9._-] become '?', result truncated to 64 characters | key is raw file text printed to hosted logs | CAP-py | supervisor.py:172-173 takes parts[0] unfiltered | CODING |

## 20. Implementation sequence

1. Supervisor core: add `warnings` to Config and load_config (D-1, D-2); add `config_notices` and wire entry and CLI `config` printing (D-3). Unknown-key rule in load_config: an unknown key (including the empty name from a bare `supervision.` line, warned like any other unknown key) is checked against KINDS BEFORE `seen.add`, so it is never added to `seen` and never affects the runner/model fallback or `_hosted_defaults`; distinct unknown keys are tracked in a separate set so N occurrences yield exactly one warning, in file order, duplicates silent; when every supervision key is unknown the result is defaults, errors==[] and one warning per distinct key. Warning text: key text sanitized (characters outside [A-Za-z0-9._-] replaced with '?', truncated to 64 characters, R-4), config value never included; warnings are capped at 20 lines plus a '... and N more' line. Warnings go only to stderr, never to Config.lines or stdout. `config_notices` passes every line it returns (warnings and disabled_reason) through `redact()` with `known_secret_values(environ, config_path)`. Run-entry rule: `config_notices` is called exactly once per process, at supervised-run entry before the first stage starts, and returns no lines when not hosted (non-hosted supervised runs print nothing at entry); when hosted it returns all warnings in file order, then `disabled_reason` if `errors` is non-empty (errors include the hosted missing-model error appended by `_hosted_defaults`, so that line follows any warnings), one stderr line each. `reload_config` (supervisor.py:991-1009) is left unchanged in this respect: it may update `self.config` and status as today but prints nothing to stderr and never calls `config_notices`, so a mid-run reload cannot re-emit warnings or the disabled reason. CLI `config` action (supervisor.py:1923-1929): print `lines` to stdout, then each warning to stderr (regardless of hosted mode), then `disabled_reason` to stderr if errors exist; exit 1 if any error exists, else 0, regardless of warnings. Reqs AC-1..AC-5.
   Owns: `scripts/lib/supervisor.py`
2. Tests: remove ('bogus','1') from the roundtrip error loop and assert it separately as warning-only for a file containing only `supervision.bogus 1`: errors == [], disabled_reason == '', warnings == ['ignoring unknown supervision key: supervision.bogus'], values equal DEFAULTS. Keep a direct assertion that parse_value('bogus','1') still raises ValueError('unknown supervision key: supervision.bogus'). Add tests for AC-1..AC-5. Builds on step 1 for API names; separate file.
   Owns: `scripts/tests/supervisor-test.py`
   Depends on: 1
3. Docs: README.md and docs/supervision.md hosted note (D-4). Both files must state that credentials (api keys, secrets) must not be put in .uncle/config and that unknown-key warnings name only the key. Independent of 1-2.
   Owns: `README.md`, `docs/supervision.md`
4. Record deviation (config.example, build script) and run tests.
   
   Live-verification check IDs: none requiring credentials; verification commands are the baseline's two runners.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 2, 3

AC-4 additional tests: (a) CLI `config` on a file with an unknown key plus an invalid recognized value emits stdout lines, then the warning, then disabled_reason on stderr, with exit 1; (b) with stderr closed (subprocess started with stderr closed), warnings-only exits 0 and errors exit 1, unchanged by the closed stream.

## 21. Scope cuts
Cut first: hosted stderr notice for disabled reasons (keep warnings), then docs in docs/supervision.md. Never cut the load_config change.

## 22. Risks
- Typos of recognized keys are silently demoted to warnings (accepted, requested).
- `.uncle/config.example` and build script are not in this repo (recorded, not blocking).

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real gap: plan did not define dedup, seen/fallback handling, or empty-key behavior for unknown keys. | Edit step-1 and s7.1 to define: unknown keys not added to seen, one warning per distinct key, empty key treated as unknown; add traceability row note. |
| AR-002 | Accepted | reload_config re-calls load_config mid-run and the plan was silent on printing; stating it prints nothing removes the ambiguity. | Step 1, R-2, traceability row for Request 2 and section 16 now state reload_config prints nothing; notices print once at entry, with a test. |
| AR-003 | Accepted | B-7/AC-5 scope the entry notice to UNCLE_HOSTED=1, so D-3 printing warnings always was inconsistent; hosted-only for entry notices resolves it (matches AR-017). | R-2, step-1 and s11.1 now state: run-entry notices (warnings then disabled_reason) print only when hosted; non-hosted entry prints nothing; CLI config always prints warnings. |
| AR-004 | Accepted | CLI config output with both errors and warnings was unspecified; the decision is stdout lines, then warnings, then disabled_reason on stderr, exit 1. | Added CLI output-order rule to s11.1 tests, step-1, and a new AC-4b test line in the s15.1.r2 traceability row. |
| AR-005 | Accepted | Key text comes unvalidated from the config file, so it needs a length bound and secret redaction using the existing redact() machinery. | R-3 now requires keys truncated to 64 characters and passed through redact() before printing, with a test for a long and a secret-like key. |
| AR-006 | Accepted | The replaced roundtrip assertion for a file containing only an unknown key must be stated explicitly; parse_value keeps raising for direct callers. | Step 2 text now specifies the bogus-key assertions (errors, disabled_reason, warnings, values equal DEFAULTS) and that parse_value still raises. |
| AR-007 | Accepted | The plan named only run entry and CLI config as print sites and was silent on reload_config, which also calls load_config mid-run. | Step 1 and the Request 2 traceability row now state reload_config prints nothing; config_notices runs only at run entry and in the CLI config action, with a test. |
| AR-008 | Accepted | The hosted missing-model error from _hosted_defaults lands in errors, so the notice order and that case must be stated. | Step 1 text and traceability row s15.1.r2 now fix the hosted notice order (warnings in file order, then disabled_reason) and cover the missing-model error. |
| AR-009 | Accepted | load_config adds keys to `seen` before parse and _hosted_defaults/runner fallback read it, so the plan must say unknown keys stay out of `seen`. | D-1 in section 1 states unknown keys are not added to seen, do not affect runner/model fallback, and duplicates warn once; step-1 text updated to match. |
| AR-010 | Accepted | Plan did not state that warnings stay off stdout and Config.lines, nor the exit code with mixed warnings and errors. | Edit step 1 and Request 1 traceability row to require warnings only on stderr, never in Config.lines or stdout, and exit 1 iff errors exist. |
| AR-011 | Accepted | The plan only said the bogus case is replaced; the exact test change must be specified. | Section 10 (s8.1) now states the bogus case is removed from the error loop and asserted separately as warning-only with default values; step-2 matches. |
| AR-012 | Accepted | The key comes raw from the config file and is printed to stderr, so control or ANSI characters could inject into hosted logs; sanitizing is cheap. | Add restriction R-4, step-1 text, and a section 16 test: key sanitized to [A-Za-z0-9._-], truncated to 64 chars, others replaced with '?'. |
| AR-013 | Accepted | disabled_reason embeds error text and was unredacted; the existing redact()/known_secret_values machinery can cheaply cover every printed notice line. | Step 1 now requires config_notices to pass every line through redact() with known_secret_values(environ, config_path) and never include config values. |
| AR-014 | Accepted | Credential-like unknown keys (supervision.api_key, base_url) are plausible; the warning must name only the key and docs must warn, with a test proving a sentinel value never reaches stderr. | Docs rows (README, supervision.md) gain a no-credentials-in-.uncle/config note; Request 3 traceability adds a sentinel-absent-from-stderr test. |
| AR-015 | Accepted | Warning volume must be bounded and duplicate unknown keys must not multiply output. | Interfaces (s7.1) and step 1 now state one warning per distinct unknown key, capped at 20 lines plus a '... and N more' line. |
| AR-016 | Accepted | The 'once' rule had no defined hook or count; fixing it to one run-entry call with no reload printing makes AC-5 testable. | Edit step-1, s11.1, R-2 and s15.1.r2: config_notices runs once per process at run entry before the first stage, reload_config never prints, tests assert one occurrence. |
| AR-017 | Accepted | D-3 printed warnings unconditionally while B-7/AC-5 scope the notice to hosted runs; the rule must be single and explicit. | Traceability row Request 2 and step-1 now state non-hosted entry prints nothing; hosted prints warnings then disabled_reason; CLI config unaffected. |
| AR-018 | Accepted | Duplicate and odd unknown keys were unspecified; first-wins with one warning per distinct key matches existing duplicate handling. | Section 8 (s7.1) and step-1 now state one warning per distinct unknown key in file order, duplicates silent, key text verbatim after 'supervision.'. |
| AR-019 | Accepted | A no-value-echo rule needs a concrete observable assertion; a sentinel value checked across all outputs makes it testable. | Edit R-3 property/mechanism and s11.1 to require a sentinel-value test asserting absence from stdout, stderr and warnings. |
| AR-020 | Accepted | load_config adds keys to seen before parse_value, so skipped unknown keys must be explicitly kept out of seen to avoid affecting runner/model fallback and _hosted_defaults. | D-1 in section 1 and step-1 now state unknown keys are skipped before seen.add and never affect runner/model fallback or _hosted_defaults. |
| AR-021 | Accepted | CLI errors-plus-warnings output and closed-stderr handling are real gaps and need explicit rules and a test. | Section 12 (s9.1) states CLI ordering, exit code and closed-stderr rule; section 17 gains an AC-4 test for mixed output and closed stderr. |
