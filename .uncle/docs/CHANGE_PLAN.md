# Change Plan

Omitted sections: Schema/persistence (none); Concurrency (none); Migration (none); Feature flag (none); Observability (none); State-transition changes (none)

## 1. Selected technical approach

Decision D1: in `runners_for` (uncle_tui.py:690), after the scan, `return installed or ["self-hosted"]`. Every consumer (stage_runner default, runner pickers, description text) then sees the fallback with no further edits. The fallback applies independently per side (agent and reviewer); no agent-reviewer distinctness rule filters it.

Clarified semantics: (a) With no runner installed, runners_for returns ["self-hosted"]. stage_runner is unchanged and still returns a configured runner or DEFAULT_RUNNER if set, even if that runner is absent from runners_for; only an unset value yields self-hosted. (b) The fallback fires only when the scanned list is empty and never appends to a non-empty list, so self-hosted cannot appear twice. With only opencode on PATH (opencode maps to self-hosted), runners_for returns exactly ["self-hosted"] once.

## 2. Alternatives considered
- A: patch `stage_runner` and each picker site separately (3+ edits; can diverge).
- B: add a new helper wrapping runners_for (extra surface).

## 3. Why preferred
One-line, minimal diff, single source of truth; installed case is untouched because the fallback only fires on an empty list.

## 4. Components to modify
See change-impact table.

## 5. Not to modify

self-hosted config flow, shims, `stage_runner` logic, DEFAULT_RUNNER, supervision_lib, existing tests.

Explicit rule for `stage_runner` (unchanged): a configured runner, or DEFAULT_RUNNER if set, is still returned even when it is absent from `runners_for` output (for example claude configured but nothing installed). Only an unset value falls back to self-hosted, via the runners_for fallback. The picker and the default may therefore differ for a configured-but-uninstalled runner; this is preserved existing behavior (C4) and is out of scope.

## 6. Data-flow changes

`runners_for` result is non-empty. The fallback fires only when the scan finds nothing and never appends to a non-empty list, so self-hosted cannot be duplicated (opencode-only installed gives exactly ["self-hosted"], since opencode maps to self-hosted). With no runners installed the description text lists "Self hosted" and never shows "No agents installed"; that label at line 1297 becomes unreachable and is left as-is (minimal diff). Defaulting to self-hosted does NOT bypass the existing self-hosted configuration requirement: an unconfigured self-hosted runner remains subject to whatever existing config gate applies at launch. Before editing, step 1 audits uncle_tui.py for any other guard keyed on an empty runner list or runner=="" and records the result in IMPLEMENTATION_NOTES.md.

## 8. Interface changes
None in signature; return value gains a fallback.

## 10. Compatibility
Preserved whenever one runner is detected (C3, C4).

## 12. Error and recovery
PATH stderr diagnostics unchanged.

## 14. Rollback plan
Revert the fallback line and delete the new test.

## 16. Automated-test strategy

New `scripts/tests/runners-none-installed-test.py` (hyphenated so run-python-tests.sh collects it), modelled on how scripts/tests/home-actions-test.py imports uncle_tui. Isolation (binding): every test sets os.environ["PATH"] to a fresh temp directory only (never the host PATH, never appended), patches uncle_tui.DEFAULT_RUNNER to "", and uses an empty/temp config so no configured runner is read from the host; all env, module-attribute and config changes are restored in tearDown and only temp dirs are used. runners_for reads PATH on every call (verified against the source when writing the test; if it caches, the test resets the cache). Fake binaries are created portably: on POSIX, executable files with chmod 0o755; on Windows, `.bat`/`.cmd` stubs with PATHEXT honoured, and if the scan cannot detect them the cases needing fake binaries are skipped with a stated reason rather than silently passing. Cases: (AC-1) with PATH set to an empty temp dir, call `runners_for` once for each side value the real signature accepts (the implementer reads the signature at uncle_tui.py:690 and the test enumerates exactly those values, i.e. the agent side and the reviewer side), each side independently with no distinctness filtering, and assert the result equals ["self-hosted"] for each; an unset/empty PATH value also gives ["self-hosted"] and launches nothing (AR-011); with no runners installed the description text lists "Self hosted" and never contains "No agents installed" (AC-1); (AC-2) stage_runner default gives self-hosted with no configured runner and DEFAULT_RUNNER empty; a configured runner (e.g. claude) that is not installed is still returned by stage_runner while runners_for returns ["self-hosted"]; (AC-2, V1) with no runner installed and self-hosted unconfigured, the existing self-hosted configuration requirement still applies, i.e. defaulting does not start a run or bypass the existing gate (if the gate is not unit-reachable, assert the existing predicate returns the same result as for an explicitly selected unconfigured self-hosted; if no such guard exists today, record that in IMPLEMENTATION_NOTES.md as a pre-existing gap and do not fix it here); (AC-3) temp dir with executable fake `claude` and `opencode` makes `runners_for` return exactly ["claude","self-hosted"], self-hosted appearing once (opencode maps to self-hosted, no extra entries); temp dir with only fake `opencode` returns exactly ["self-hosted"] once, no duplicate; the fallback fires only on an empty list and never appends to a non-empty one. Fails before the fix (empty list), passes after: this is the regression test.

Binding test-case supplement (applies in addition to the cases above; all cases live in runners-none-installed-test.py): (1) Isolation: PATH is set to a fresh temp dir only, uncle_tui.DEFAULT_RUNNER is patched to "", config is empty/temp, all restored in tearDown. (2) Per-side: assert ["self-hosted"] for each side value separately, naming the side in the assertion message. (3) Description text: with nothing installed it contains "Self hosted" and not "No agents installed". (4) Configured-but-uninstalled: with claude configured and nothing installed, stage_runner returns "claude" while runners_for returns ["self-hosted"]. (5) Exact lists via assertEqual: fake claude+opencode gives ["claude","self-hosted"]; opencode only gives ["self-hosted"] once. (6) Unconfigured self-hosted default does not start a stage and hits the existing configuration-required path (if no such guard exists, record as a pre-existing gap in IMPLEMENTATION_NOTES.md). (7) runners_for reads PATH on every call; fake binaries are chmod 0o755 files on POSIX, .cmd stubs on Windows, with a stated skip reason if undetectable.

## 17. Regression strategy
Run baseline commands: `bash scripts/run-shell-tests.sh`, `bash scripts/run-python-tests.sh` (from baseline), compared to the pre-change baseline.

## 18. Manual verification

Run uncle with a PATH holding none of the four binaries, open Configure, and inspect the runner picker for a stage: only "Self hosted". The manual check covers the stage runner pickers only; the supervision picker is excluded from pass/fail (it may remain empty if SUPPORTED_RUNNERS excludes self-hosted, per section 22).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` `runners_for` | return `installed or ["self-hosted"]` | single fallback point | Low: callers get a non-empty list | new test + existing suites |
| `scripts/tests/runners-none-installed-test.py` | new test file, isolated: PATH set to a temp dir only (read per call), DEFAULT_RUNNER patched to "", empty config, restored in tearDown; portable fake binaries (.bat/.cmd on Windows, else skip with reason); includes unset/empty PATH case and an assertion that the unconfigured self-hosted default does not bypass the existing configuration guard | cover no-runner and preserved cases | None | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: with no runner on PATH, runners_for returns exactly ["self-hosted"] (self-hosted appearing once) independently for each side value the real signature accepts (agent and reviewer; the test names the actual values from the signature), with no distinctness rule filtering it; the description text lists "Self hosted" and never shows "No agents installed". | C1 | V1 | runners_for | runners-none-installed-test.py | picker shows only Self hosted |
| AC-2: with no configured runner and DEFAULT_RUNNER empty, stage_runner returns self-hosted; a configured runner (e.g. claude) absent from runners_for output is still returned unchanged; an unconfigured self-hosted default does not start a stage and surfaces the existing configuration-required behavior. | C2 | V1 | runners_for via stage_runner | runners-none-installed-test.py | stage default shown as Self hosted; selecting it while unconfigured does not start a stage and shows the existing configuration-required behavior |
| AC-3: when any non-self-hosted runner is detected, behavior is unchanged: with fake claude and opencode on PATH, runners_for returns exactly ["claude","self-hosted"] (self-hosted appearing once); with only opencode it returns exactly ["self-hosted"] (once, no duplicates); the fallback fires only on an empty list and never appends to a non-empty list. | C3, C4 | V2 | runners_for | runners-none-installed-test.py (claude+opencode case, opencode-only case) | n/a |
| AC-4 | C3, C4 | V2 | whole TUI | both baseline commands | n/a |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Constraints | AC-3, AC-4 | Behavior unchanged when any runner installed | fallback only on empty list; no other behavior change, and PATH contents never select or auto-launch a runner beyond the existing scan | minimal | none | inspected uncle_tui.py:690-709 | CODING |
| R-2 | USER | CHANGE_REQUEST.md Constraints | AC-4 | Do not weaken existing tests | add new test only | requested | none | no existing test references runners_for | CODING |

No live-authentication prerequisites; no capability IDs needed. The empty-list fallback is the only behavior change: PATH contents (empty, unset, or unreadable/untrusted directories) never select or auto-launch a runner beyond the existing scan.

## 20. Implementation sequence

1. Audit uncle_tui.py for other guards keyed on an empty runner list or runner=="" (and whether an unconfigured self-hosted default can start a run); record findings in IMPLEMENTATION_NOTES.md. Then add the fallback to `runners_for` (D1; R-1).
   Owns: `uncle_tui.py`
2. Add regression test AC-1..AC-3; independent of step 1 file-wise (it only imports uncle_tui), so can be written concurrently.
   Owns: `scripts/tests/runners-none-installed-test.py`
3. Run the new test and confirm the baseline commands show no new failures.
   Depends on: 1, 2

## 21. Scope cuts under time pressure

Cut the preserved-case AC-3 assertions last-first (opencode-only and claude+opencode cases), then the Windows-specific fake-binary variants (skipped with a stated reason); never cut the AC-1/AC-2 test, the guard audit in step 1, the unconfigured self-hosted guard assertion, or the fallback.

## 22. Risks and unresolved questions

- The unreachable "No agents installed" label is left untouched deliberately.
- V1 (runners_for never empty) applies only to `runners_for` output. The supervision picker, filtered by SUPPORTED_RUNNERS, may still be empty if that list excludes self-hosted; out of scope per the request and excluded from pass/fail.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real gap: configured-but-absent runner behavior was unstated; stage_runner is untouched so it keeps returning configured/DEFAULT_RUNNER. | Add s1 block stating stage_runner still returns a configured runner or DEFAULT_RUNNER even if absent from runners_for; add test case in s11.1. |
| AR-002 | Accepted | Opencode-only and duplicate cases were unspecified; the fallback only fires on an empty list so it cannot duplicate. | Specify opencode-only returns ["self-hosted"] once and no duplicates in s1 block, AC-3 row, and s11.1 test cases. |
| AR-003 | Accepted | The fallback is a single post-scan line, so independence per side and exemption from distinctness rules should be stated explicitly. | s1.1 states per-side independence with no distinctness filtering; AC-1 test wording updated to match. |
| AR-004 | Accepted | Description text consumes runners_for, so with the fallback it lists Self hosted; the label should be stated unreachable and tested. | s6.1 specifies description text with no runners; s11.1 adds an assertion that the text never shows No agents installed. |
| AR-005 | Accepted | V1 'never empty' was unscoped while the plan admits the supervision picker may stay empty; scoping removes the contradiction. | Section 22 item 2 now states V1 applies only to runners_for output; the supervision picker filtered by SUPPORTED_RUNNERS may be empty. |
| AR-006 | Accepted | Plan left unstated what happens when a configured runner is absent from runners_for; stage_runner is unchanged by design, so say so. | Section 5 gains an explicit rule: stage_runner still returns a configured runner or DEFAULT_RUNNER even if absent from runners_for; only an unset value falls back to self-hosted. |
| AR-007 | Accepted | Opencode-only result and no-duplicate behavior are real gaps in the spec and test. | s11.1 adds an opencode-only case asserting exactly ["self-hosted"]; s6.1 states the fallback only fires on an empty list and never appends. |
| AR-008 | Partially accepted | Plan should state defaulting does not bypass self-hosted configuration and have step 1 audit other empty-runner guards; changing launch gating itself is out of scope. | s6.1 and step-1 require auditing guards keyed on empty runner lists or runner==""; s11.1 tests that unconfigured self-hosted is still gated; s18.1 notes the cut order. |
| AR-009 | Accepted | Real gap: the test must not depend on caching or on POSIX executable bits unstated. | s11.1 states PATH is read per call and fake binaries are portable (.bat/.cmd on Windows, else skip with reason). |
| AR-010 | Partially accepted | Changing the self-hosted config flow is out of scope, but the plan should assert that it is not bypassed and test the existing guard. | s11.1 and AC-2 add a test that the unconfigured self-hosted default does not bypass the existing configuration guard; no production change. |
| AR-011 | Accepted | Stating that the fallback is the only behavior change and PATH contents never auto-select or launch a runner is cheap, accurate, and testable. | Added restriction R-1 wording and a s16 prose note that the fallback is the only behavior change; test also covers unset/empty PATH. |
| AR-012 | Accepted | The test must be isolated from the host environment or results depend on installed binaries and config. | s11.1 now specifies PATH set to a temp dir only, DEFAULT_RUNNER patched to empty, empty config, with restoration in tearDown. |
| AR-013 | Accepted | The AC-3 expected shape was ambiguous; fixing it to exactly ["claude","self-hosted"] with self-hosted once is testable. | Edit s11.1 and AC-3 to state the exact result with self-hosted appearing once. |
| AR-014 | Accepted | The 'both sides' wording gave no argument values; the test must name them. | Edit s11.1 and AC-1 so the test iterates over the side values the real runners_for signature accepts and asserts ["self-hosted"] for each. |
| AR-015 | Accepted | The manual check did not say whether the supervision picker is in scope, though the plan admits it may stay empty; scoping it removes the ambiguity. | Section 18 (s13.1) now limits the manual check to stage runner pickers and excludes the supervision picker from pass/fail. |
