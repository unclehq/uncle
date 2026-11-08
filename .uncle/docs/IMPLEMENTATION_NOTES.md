# Implementation notes

### Files changed

- `uncle_tui.py` — Claude catalog replaced with the 12 ordered models; claude default set to claude-sonnet-5-5; stale opus comment rewritten; 1; SB-1, SB-2, SB-4, SI-3
- `scripts/stagegate.sh` — DEFAULT_MODEL set to claude-sonnet-5-5; 2; SB-3, SI-2
- `scripts/reviewer-claude.sh` — DEFAULT_MODEL fallback set to claude-sonnet-5-5; 2; SB-3, SI-2
- `scripts/tests/claude-model-defaults-test.py` — New test: exact catalog, default agreement, allowlist (bash case), comment, other runners unchanged. Fixed the bash case helper so the pattern is interpolated into the script (alternation is not honored via parameter expansion).; 3; SI-1, SI-2, SI-3, SI-4

### Unresolved concerns

- Full shell and Python suites are run by the driver, not here.
- The Bedrock items in DEFECTS.md and TEST_REVIEW.md belong to an earlier unrelated change, not issue 185.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | uncle_tui.py MODEL_CATALOG_CLAUDE: 12 ordered pairs | python3 scripts/tests/claude-model-defaults-test.py: 6 tests OK (catalog exact test) |
| AC-2 | IMPLEMENTED | uncle_tui.py DEFAULT_MODEL_FOR_RUNNER, scripts/stagegate.sh:282, scripts/reviewer-claude.sh:37 | same test run, default agreement test OK |
| AC-3 | IMPLEMENTED | scripts/tests/claude-model-defaults-test.py allowlist test | initially failed (test harness bug), fixed; now OK for all 12 ids via bash case and fnmatch |
| AC-4 | IMPLEMENTED | uncle_tui.py comment near line 485 | comment test OK |
| AC-5 | IMPLEMENTED | no Codex/Kimi edits; test_other_runners_unchanged added | snapshot test OK; full suites pending in driver green check |
