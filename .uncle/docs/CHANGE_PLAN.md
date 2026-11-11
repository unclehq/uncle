# Change plan — Issue 253

Seeded from [unclehq/uncle#253](https://github.com/unclehq/uncle/issues/253).

Issue 253

Omitted sections: Schema/persistence, Migration, Concurrency, Feature flag (none; behavior keyed off existing env), Observability (output labels only)

## 1-3. Approach
Decision D-1: add `hosted_run(env)` to `headless_preview.py` (true if `UNCLE_PREVIEW_MODE=='host'` or `UNCLE_HOSTED=='1'`, mirroring host_preview.is_host_mode and hosted.py without importing them). `enabled()` returns False when hosted. `uncle_headless._scan_announcements` skips the `Preview:` line when hosted (still records seen url) using `headless_preview.hosted_run(os.environ)`. D-2: relabel with `Local preview:` in `_scan_announcements` and all three `finish()` messages. D-3: edit SKILL.md rule 5 so it relays only https links, never local addresses, and says no link was provided when only local links appear under either `Preview:` or `Local preview:`; update chat-skill-test patterns to require both labels.
Alternatives: import host_preview.is_host_mode (adds a coupling; rejected); set WORKFLOW_PREVIEW_OPEN_BROWSER=0 in the runner env (does not stop the scan line; rejected). Chosen is smallest and in scope.

## 4. Change-impact table

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/headless_preview.py` | add hosted_run(); enabled() honors it; `Local preview:` labels | SB-1,2,4 | Low | headless-preview-test, -open-test |
| `scripts/lib/uncle_headless.py` | skip Preview in hosted; `Local preview:` label | SB-1,3 | Low | headless-preview-test |
| `skills/uncle-build/SKILL.md` | rule 5 https-only, no local addresses; no-link response for local-only `Preview:` or `Local preview:` | SB-6 | Low (line cap 60) | chat-skill-test |
| `scripts/tests/headless-preview-test.py` | update old-label asserts; add hosted cases | AC-1..4 | Low | self |
| `scripts/tests/headless-preview-open-test.py` | update label regex lines 292-293 | AC-3 | Low | self |
| `scripts/tests/chat-skill-test.py` | http-https-verbatim -> https; add no-local-links pattern requiring both `Preview:` and `Local preview:` with the no-link response, needle case, good-variant text, and a bad variant naming only `Preview:` | AC-5 | Low | self |

## 5. Not to modify
`host_preview.py`, `host_preview_hook.sh`, `stage-config.sh`, `preview_server.py`, TUI, `App:` handling.

## 6-8. Data flow / interfaces
Output label change only (`Preview:` -> `Local preview:` locally; none hosted). New helper `headless_preview.hosted_run(env=None)`.

## 10. Compatibility
Local consumers reading `Preview:` loopback must read `Local preview:`; mandated by request. Test updates are in-scope per request item 2 and Tests section (protected-path edits are intentional; flagged for reviewer).

## 12. Error and recovery
Unset env means non-hosted; behavior unchanged.

## 14. Rollback
Revert the change; no state migrated.

## 16-17. Test strategy
Regression tests (fail before, pass after): (a) announcement suppression: hosted host-mode case with live preview-server file asserting no Preview line (also for `UNCLE_HOSTED=1`); (b) start suppression: for each hosted flag (`UNCLE_PREVIEW_MODE=host`, `UNCLE_HOSTED=1`), run poll() and finish() with an otherwise eligible app, available page, NO live server and a start spy; assert zero start calls and finish()==[]; these must fail against pre-change code, plus a non-hosted control that does start (the live-server fixture is not used for this, as server_alive already suppresses starts); (c) local `Local preview:` case; (d) chat-skill: rule 5 must name both `Preview:` and `Local preview:` local-only cases with the no-link response; bad variants removing the local-address sentence, or naming only `Preview:`, must be rejected. Run via Verification commands in baseline (commands 3-4 run the touched suites explicitly).

## 18. Manual verification
Hosted `--noui` build prints exactly one `Preview:` (host signed https link); local build shows `Local preview:`. Requires hosted environment (LIVE_VERIFICATION, not a coding prerequisite).

## Restrictions
| R-ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 1 | AC-1,2 | no hosted Preview/server | hosted_run guard in enabled() and scan | env already set in runner (stage-config.sh:47-51 inspected) | CAP-ENV | CODING |
| R-2 | USER | Fix 2 | AC-3 | local label distinct | rename prefix | direct | CAP-TEXT | CODING |
| R-3 | USER | Fix 3 | AC-5 | https-only relay | SKILL.md + checker pattern | direct | CAP-TEXT | CODING |
| R-4 | REPOSITORY | chat-skill-test | AC-5 | skill <=60 lines | edit rule 5 in place | checker cap | CAP-TEXT | CODING |

## 20. Implementation sequence

## Implementation sequence

1. Hosted guard and relabel in runtime code — Owns: `scripts/lib/headless_preview.py`, `scripts/lib/uncle_headless.py`
2. Chat skill rule and checker — Owns: `skills/uncle-build/SKILL.md`, `scripts/tests/chat-skill-test.py`
3. Headless tests updated and added — Owns: `scripts/tests/headless-preview-test.py`, `scripts/tests/headless-preview-open-test.py` — Depends on: 1

Steps 1 and 2 are independent (no shared files).

## 21. Scope cuts
Cut first: the `UNCLE_HOSTED=1` test variant, then the `finish()` error-line relabel tests; never cut the host-mode suppression or the https-only rule.

## 22. Risks
- Unknown other docs/tests referencing `Preview: http://127.0.0.1`; step 3 greps before editing.
- `App:` loopback lines remain in hosted output (out of scope, not relayed by chat rules).

## Traceability
| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-1 | SI-1 | uncle_headless.py | headless-preview-test | hosted build one Preview |
| AC-2 | SB-2 | SI-1 | headless_preview.py | headless-preview-test | hosted build |
| AC-3 | SB-3,4 | SI-2 | both | headless-preview(-open)-test | local build |
| AC-4 | SB-5 | SI-4 | both | existing | n/a |
| AC-5 | SB-6 | SI-3 | SKILL.md | chat-skill-test | chat relays only https |
| AC-6 | all | all | all | driver commands | n/a |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real gap: rule 5 and its checker covered only the old `Preview:` label, leaving the new `Local preview:` output without a no-link fallback. | Edited Approach D-3, impact rows for SKILL.md and chat-skill-test, and test strategy so rule 5 names both labels and a one-label variant is rejected. |
| AR-002 | Accepted | A live-server fixture is already a no-start case, so it cannot detect a missing hosted guard. | Edited Test strategy: per-flag no-server poll()/finish() fixtures with start spy plus non-hosted control; live-server fixture only for announcement suppression. |
| AR-003 | Accepted | Duplicate of AR-002; same fixture flaw, resolved by the same change. | Same Test strategy edit, requiring these fixtures to fail against pre-change code. |
