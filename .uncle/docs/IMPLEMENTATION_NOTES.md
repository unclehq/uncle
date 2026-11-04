# Implementation notes

### Files changed

- `scripts/lib/housekeeping_policy.py` — Pure policy: tokenized disallow/locked-floor matching, allowlist exact command shapes, unparseable-construct refusal, verify templates; 1; I-1, I-2, I-7; AC-7, AC-8, AC-9
- `scripts/lib/housekeeping_config.py` — Load/save housekeeping.disallow in .uncle/config; invalid pattern rejected keeping old list; corrupt/missing falls back to defaults; floor merged; 1; I-4, I-7; AC-12
- `scripts/lib/housekeeping_input.py` — Validate request text (UTF-8, <=1048576 bytes, non-empty, no NUL/control chars); 2; AC-1, AC-2
- `prompts/housekeeping-plan.md` — Plan-stage prompt for the housekeeping-plan agent; 3; AC-4
- `scripts/housekeeping-workflow.sh` — New driver: plan, policy, approval, execute, verify, report; shared lock; records under .uncle/workflow/housekeeping/; 3; I-1, I-2, I-3, I-5, I-6, I-8; AC-4, AC-5, AC-6, AC-10, AC-11
- `uncle` — --housekeeping flag, stdin/argument input, mutual exclusion, usage, did-you-mean, line-menu Configure entry for disallow list; 4; AC-1, AC-12
- `uncle_tui.py` — /housekeeping slash command, startup action, completion, Misc menu entry for disallow list; 5; AC-3, AC-12
- `scripts/tests/housekeeping-policy-test.py` — Unit tests for policy and config; 1; AC-7, AC-8, AC-9, AC-12
- `scripts/tests/housekeeping-input-test.py` — Unit tests for input validator; 2; AC-2
- `scripts/tests/housekeeping-workflow-test.sh` — Driver tests with stub agent/gh/git incl. lock, decline, unattended failure stop, verify mismatch, static AC-13 check and mutation check; 3; AC-4, AC-5, AC-6, AC-10, AC-11, AC-13
- `scripts/tests/housekeeping-launcher-test.sh` — Launcher flag, exclusivity, did-you-mean and menu tests; 4; AC-1, AC-12
- `scripts/tests/tui-housekeeping-test.py` — Source-level TUI checks for slash command, startup action, Misc entry; 5; AC-3, AC-12
- `README.md` — Document --housekeeping and disallow list; 6; documentation

### Unresolved concerns

- TUI test is source-level (string checks), not a dispatch test with the driver stubbed; AC-3 and the TUI half of AC-12 have static evidence only.
- AC-15 is a manual scratch-GitHub-repository rename and has not been performed.
- Full shell and Python suites are driver-owned and were not run in this stage.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | uncle (--housekeeping flag, stdin/arg, exclusivity, usage, did-you-mean); scripts/lib/housekeeping_input.py | bash scripts/tests/housekeeping-launcher-test.sh exit 0 (PASS lines for did-you-mean, unknown flag unchanged) |
| AC-2 | IMPLEMENTED | scripts/lib/housekeeping_input.py validator | python3 scripts/tests/housekeeping-input-test.py: Ran 8 tests OK |
| AC-3 | IMPLEMENTED | uncle_tui.py /housekeeping handler, _start_housekeeping, startup action, completion list | python3 scripts/tests/tui-housekeeping-test.py: PASS static checks (source-level only) |
| AC-4 | IMPLEMENTED | scripts/housekeeping-workflow.sh sourcing shared scripts/lib helpers | bash scripts/tests/housekeeping-workflow-test.sh: all passed |
| AC-5 | IMPLEMENTED | scripts/housekeeping-workflow.sh approve/decline/execute/report | bash scripts/tests/housekeeping-workflow-test.sh: all passed |
| AC-6 | IMPLEMENTED | scripts/housekeeping-workflow.sh unattended path, same policy call, stop on first failure | bash scripts/tests/housekeeping-workflow-test.sh: all passed |
| AC-7 | IMPLEMENTED | scripts/lib/housekeeping_policy.py disallow matching | python3 scripts/tests/housekeeping-policy-test.py exit OK |
| AC-8 | IMPLEMENTED | scripts/lib/housekeeping_policy.py allowlist shapes | python3 scripts/tests/housekeeping-policy-test.py exit OK |
| AC-9 | IMPLEMENTED | scripts/lib/housekeeping_policy.py unparseable refusal | python3 scripts/tests/housekeeping-policy-test.py exit OK |
| AC-10 | IMPLEMENTED | scripts/housekeeping-workflow.sh verify with NOT VERIFIED/FAIL/PASS | bash scripts/tests/housekeeping-workflow-test.sh: all passed |
| AC-11 | IMPLEMENTED | scripts/housekeeping-workflow.sh uses shared driver.lock | bash scripts/tests/housekeeping-workflow-test.sh: all passed |
| AC-12 | IMPLEMENTED | scripts/lib/housekeeping_config.py; uncle line menu; uncle_tui.py Misc entry | housekeeping-policy-test.py OK; housekeeping-launcher-test.sh PASS configure menu entry; TUI entry static check only |
| AC-13 | IMPLEMENTED | static and mutation tests in scripts/tests/housekeeping-workflow-test.sh | ok: ac13-static; ok: mutation-detected |
| AC-14 | IMPLEMENTED | additive hunks only in uncle and uncle_tui.py | targeted housekeeping suites pass; full suites are driver-owned (DRIVER PENDING) |
| AC-15 | BLOCKED | Behavior exists in driver; manual end-to-end check not performed | BLOCKED-HUMAN: needs a person with a scratch GitHub repository to rename attended and unattended |
