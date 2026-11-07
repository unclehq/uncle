# Implementation notes

### Files changed

- `uncle_tui.py` — runners_for returns installed or ["self-hosted"]; Change-impact table row 1; C1, C2, V1
- `scripts/tests/runners-none-installed-test.py` — New isolated test: temp PATH, fake binaries, per-side checks, stage_runner default; Change-impact table row 2; C1, C2, C3, V1, V2

### Unresolved concerns

- Plan case (6) (unconfigured self-hosted default vs existing config guard) was not separately verified here; no guard was inspected in this pass.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | uncle_tui.py runners_for fallback | python3 scripts/tests/runners-none-installed-test.py: 5 tests OK; with fallback reverted, 3 fail |
| AC-2 | IMPLEMENTED | stage_runner uses runners_for fallback | same test run, OK |
| AC-3 | IMPLEMENTED | fallback fires only on empty list | same test run, OK (fake binaries case) |
| AC-4 | IMPLEMENTED | none beyond one-line fix | full suites are driver-owned; not run here (DRIVER PENDING) |
