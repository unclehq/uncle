# Manual checklist

### MC-101
- Exclusive resources: none
- Depends on: none
- Exact action: Create a temp config containing valid supervision keys plus `supervision.base_url SENTINEL-7f3a91`, then run `python3 scripts/lib/supervisor.py config --config <file>` capturing stdout, stderr and exit code separately.
- Expected result: Exit 0; stdout lists the supervision lines (enabled true, defaults/valid values) with no warning text; stderr contains `ignoring unknown supervision key: supervision.base_url` and the string SENTINEL-7f3a91 appears in neither stream.
- Evidence to capture: Command, exit code, stdout and stderr text.
- Actual result: 
- Status: NOT RUN

### MC-102
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CLI `config` action on a file with `supervision.bogus 1` and `supervision.max_interventions -1`, capturing stdout, stderr and exit code.
- Expected result: Exit 1; stdout shows the lines first; stderr shows the unknown-key warning then the 'Supervision corrections disabled' reason naming supervision.max_interventions; no warning text on stdout.
- Evidence to capture: Command, exit code, stdout and stderr in order.
- Actual result: 
- Status: NOT RUN

### MC-105
- Exclusive resources: none
- Depends on: none
- Exact action: With UNCLE_HOSTED=1 and OPENAI_BASE_URL, OPENAI_API_KEY and SEREN_MODEL set, start a supervised run through the normal run wrapper using a config containing `supervision.base_url x` and a trivial wrapped command that prints a marker to stdout; capture stderr and the marker ordering.
- Expected result: The unknown-key warning appears exactly once on stderr before the wrapped command's marker; supervision stays enabled (no disabled reason); the value x is not echoed.
- Evidence to capture: Combined output with timestamps or ordering, count of warning occurrences.
- Actual result: 
- Status: NOT RUN

### MC-106
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat the hosted supervised run with UNCLE_HOSTED=1 and no SEREN_MODEL/UNCLE_MODEL, plus a second run with a recognized invalid value (`supervision.max_interventions -1`); capture stderr.
- Expected result: Warnings (if any) print first, then one 'Supervision corrections disabled' line naming the missing-model error or invalid key, once each, before the wrapped command runs; the run is not aborted.
- Evidence to capture: stderr from both runs.
- Actual result: 
- Status: NOT RUN

### MC-107
- Exclusive resources: none
- Depends on: none
- Exact action: Run a supervised run WITHOUT UNCLE_HOSTED set, using a config with an unknown key; then edit the config mid-run (add another unknown key and an invalid value) and let a reload occur while observing stderr.
- Expected result: Non-hosted entry prints nothing to stderr; the mid-run reload emits no stderr notices, while status/disabled reason still updates in the TUI/status as before.
- Evidence to capture: Captured stderr (empty) and status text after reload.
- Actual result: 
- Status: NOT RUN

### MC-202
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CLI `config` on a file with `supervision.bogus 1` and `supervision.max_interventions -1`, capturing stdout/stderr/exit code; then rerun with only `supervision.max_interventions -1`.
- Expected result: Both runs exit 1; the invalid recognized value still yields a 'Supervision corrections disabled' reason on stderr and no default substituted. In the mixed run stdout lines come first, then the warning on stderr, then the disabled reason; warnings never appear on stdout.
- Evidence to capture: Captured stdout, stderr (ordered) and exit codes for both runs.
- Actual result: 
- Status: NOT RUN

### MC-203
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CLI `config` on a file with duplicate `supervision.bogus` lines, a bare `supervision.` line with a value, a key with ANSI escape/non-ASCII characters, a 200-character key, and 25 distinct unknown keys, capturing stderr.
- Expected result: Each distinct key warns once; keys contain only [A-Za-z0-9._-] with '?' substitutes and are truncated to 64 characters; the bare key is warned and not an error; warnings cap at 20 lines plus '... and N more'; exit 0.
- Evidence to capture: Stderr capture (viewed with cat -v) and exit code.
- Actual result: 
- Status: NOT RUN

### MC-205
- Exclusive resources: none
- Depends on: none
- Exact action: With UNCLE_HOSTED=1 and no SEREN_MODEL/UNCLE_MODEL, start a supervised run with a config containing an unknown key and no runner key; separately start one with a recognized invalid value.
- Expected result: Stderr shows warnings first (file order), then one 'Supervision corrections disabled: ...' line (including the missing-model error in the first case), once each; the run still starts and no config values are echoed.
- Evidence to capture: Ordered stderr captures for both runs.
- Actual result: 
- Status: NOT RUN

### MC-206
- Exclusive resources: none
- Depends on: none
- Exact action: Without UNCLE_HOSTED set, start a supervised run with a config containing an unknown key and observe stderr; then in a hosted run, rewrite the config mid-run to add a new unknown key and an invalid value, triggering a reload.
- Expected result: Non-hosted entry prints no notice to stderr; in the hosted run the entry notice appears once and the reload adds no stderr output, though status reflects the new disabled reason.
- Evidence to capture: Stderr captures before and after the reload, and status text.
- Actual result: 
- Status: NOT RUN

### MC-207
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CLI `config` with stderr closed (`2>&-`) for a warnings-only file and for an errors file.
- Expected result: Warnings-only exits 0 and errors-only exits 1; no crash or traceback despite the closed stderr.
- Evidence to capture: Exit codes and stdout from both runs.
- Actual result: 
- Status: NOT RUN

### MC-301
- Exclusive resources: none
- Depends on: none
- Exact action: Create a temp config with `supervision.base_url SENTINEL-7f3a91` plus `supervision.max_interventions 3`, then run `python3 scripts/lib/supervisor.py config --config <file>` capturing stdout, stderr and exit code separately.
- Expected result: Exit 0; stdout lists the supervision lines with max_interventions 3 and no warning; stderr has exactly one line `ignoring unknown supervision key: supervision.base_url`; SENTINEL-7f3a91 appears nowhere.
- Evidence to capture: Captured stdout, stderr and exit code.
- Actual result: 
- Status: NOT RUN

### MC-302
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CLI `config` action on a temp file containing an unknown key `supervision.bogus x` plus an invalid recognized line `supervision.max_interventions -1`; capture stdout, stderr and exit code.
- Expected result: Exit 1; stdout has the lines only; stderr shows the bogus warning first, then the 'Supervision corrections disabled' reason naming supervision.max_interventions; no warning on stdout.
- Evidence to capture: Captured stdout, stderr and exit code.
- Actual result: 
- Status: NOT RUN

### MC-303
- Exclusive resources: none
- Depends on: none
- Exact action: Start a supervised run with `UNCLE_HOSTED=1` and a config containing `supervision.base_url SENTINEL-7f3a91`, using a trivial wrapped command; capture stderr.
- Expected result: The unknown-key warning appears on stderr exactly once before the wrapped command output, supervision stays enabled, and the sentinel value is absent from all output.
- Evidence to capture: Captured stderr and stdout with ordering relative to the command output.
- Actual result: 
- Status: NOT RUN

### MC-304
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat the supervised run with `UNCLE_HOSTED=1` and a config with an unknown key plus `supervision.effort max`; then repeat with UNCLE_HOSTED unset and only an unknown key.
- Expected result: Hosted run prints the warning then the disabled reason once on stderr; the non-hosted run prints nothing about the unknown key at entry.
- Evidence to capture: Captured stderr of both runs.
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: none
- Depends on: none
- Exact action: Create a temp config containing valid supervision keys (e.g. supervision.max_interventions 3) and no unknown keys; run `python3 scripts/lib/supervisor.py config --config <file>` and note stdout, stderr and exit code.
- Expected result: Exit 0, the 13 supervision.* lines on stdout with the configured values, and nothing on stderr (no warnings).
- Evidence to capture: Command, exit code, captured stdout and stderr.
- Actual result: 
- Status: NOT RUN

### MC-402
- Exclusive resources: none
- Depends on: none
- Exact action: Create a temp config with `supervision.max_interventions -1` (recognized key, invalid value) and also `supervision.bogus x`; run `python3 scripts/lib/supervisor.py config --config <file>` capturing stdout and stderr separately.
- Expected result: Exit 1; stdout shows the lines with default values (no substituted limit); stderr shows the warning for supervision.bogus then the 'Supervision corrections disabled' reason naming supervision.max_interventions.
- Evidence to capture: Exit code, stdout, stderr with ordering.
- Actual result: 
- Status: NOT RUN

### MC-403
- Exclusive resources: none
- Depends on: none
- Exact action: With UNCLE_HOSTED=1 and no SEREN_MODEL/UNCLE_MODEL set, and a config with no runner key, run `python3 scripts/lib/supervisor.py config --config <file>`; then repeat with SEREN_MODEL=test-model set.
- Expected result: Without a model: exit 1 with the 'Hosted mode has no model' disabled reason on stderr. With the model: exit 0, runner self-hosted and model test-model in the stdout lines, no warnings.
- Evidence to capture: Both invocations' exit codes, stdout and stderr.
- Actual result: 
- Status: NOT RUN

### MC-404
- Exclusive resources: none
- Depends on: none
- Exact action: Create a config with `supervision.runner` unset, top-level `runner codex`, and an unknown `supervision.bogus 1`; run the CLI config action.
- Expected result: The unknown key does not disturb runner/model fallback: supervision.runner shows codex (global runner followed), exit 0, one warning on stderr.
- Evidence to capture: stdout lines, stderr, exit code.
- Actual result: 
- Status: NOT RUN

### MC-405
- Exclusive resources: none
- Depends on: none
- Exact action: Start a real supervised run through the normal Uncle wrapper in non-hosted mode with a config containing an unknown supervision key, then edit the config mid-run to add another unknown key and an invalid recognized value.
- Expected result: Interactive run starts normally with no stderr notice at entry; the mid-run reload prints nothing to stderr but status/TUI reflects the disabled reason after the invalid value is added.
- Evidence to capture: Captured stderr of the run and the status text before and after the edit.
- Actual result: 
- Status: NOT RUN
