## Findings

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|---|---|---|---|---|---|---|
| FA-1 | Medium | VERIFICATION_REPORT.md MC-011; `/tmp/uncle-verification/MC-011-menu-input-test.py.log`: four failures at `scripts/tests/menu-input-test.py:243`; DEFECTS.md D-002 lacks owner disposition. | Issue-based workflow launch fails existing expectations on delivery and rollback. | MANUAL_CHECKLIST.md MC-011 requires assertion-level baseline allowances. | Record owner acceptance of this existing failure or resolve it under separately approved scope and rerun. | YES |
| FA-2 | Medium | `/tmp/uncle-verification/MC-011-waiver-popup-test.sh.log`: `drive` raises `Input/output error`; DEFECTS.md D-003 leaves the cause unresolved. | Waiver interaction verification fails on delivery and rollback. | MANUAL_CHECKLIST.md MC-011 requires resolved results or explicit allowances. | Diagnose and rerun the terminal interaction, or record an explicit owner disposition of the unresolved failure. | YES |
| FA-3 | Medium | VERIFICATION_REPORT.md MC-011–015 and DEFECTS.md B-001–004 record unavailable lint, Windows, authenticated reviewer/probe, descriptor, process-inspection and socket prerequisites; the recommendation still holds approval. | Required environmental verification remains incomplete. | MANUAL_CHECKLIST.md MC-011–015 retains blocked checks; CHANGE_PLAN.md P-12 permits deferring live/platform smoke tests only. | Complete blocked checks on suitable hosts with required tools/settings, or record authorized deferrals individually, distinguishing P-12 allowances from additional exceptions. | YES |

NOT READY
