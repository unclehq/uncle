# Change Plan

Omitted sections: Schema (none); Migration (none); Concurrency (none); Feature flag (none); Observability (none); Data-flow/state/API changes (none)

Issue 235

Seeded from [unclehq/uncle#235](https://github.com/unclehq/uncle/issues/235).

## 1. Selected approach
In-repo scope only: add a warning-page rule to the chat skill, pin it with a test pattern, and strengthen the wildcard-host test. Decision D-1: no change to `host_preview.py` (default stays 127.0.0.1; the 0.0.0.0 choice is the external build script's after a live test). Decision D-2: the warning rule is rule 6, worded without 'will open'-type phrases.

## 2/3. Alternatives
Change default host to 0.0.0.0: rejected, widens exposure without live evidence. Put the note in the build script: out of repo.

## 4/5. Components
Modify: SKILL.md, chat-skill-test.py, host-preview-test.py. Not modified: host_preview.py, hook, drivers, stage-config.sh.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `skills/uncle-build/SKILL.md` | Add rule 6 as one conditional line: if Daytona shows a warning page, continue past it. It applies only to the Preview link from the build output (every relayed Preview link, including non-Daytona hosts and already-opened links where no warning appears); never advise continuing past a warning for any other URL; no quoted button name. | Issue Fix 5 | Forbidden-phrase / line cap; unconditional wording (e.g. 'on first open of each link') would be wrong when no warning appears; wording must not extend to non-Preview URLs | chat-skill suite |
| `scripts/tests/chat-skill-test.py` | Add `warning-page` REQUIRED pattern, case-insensitive, matching `warning\s+page` only on the rule-6 line that also contains `continue`; quoted button labels fail the forbidden-phrase check. Append the `('warning page','warning-page')` removal case after the existing five, deleting exactly that line and no other. | Pin rule | Pattern too loose; mitigated by the fixed case-insensitive match rule `warning\s+page` anchored to the rule-6 line (both 'warning page' and 'continue'), shared by skill text, regex and removal case; removal case must delete exactly that line | chat-skill suite |
| `scripts/tests/host-preview-test.py` | Extend wildcard test: assert record host `0.0.0.0`; assert the recorded url host is exactly `127.0.0.1` and `0.0.0.0` appears only in the host field of preview.json (not in url or chat output). Then probe the first non-loopback, non-link-local IPv4 address of a local interface (2s connect timeout; local interface addresses only, no outbound calls). If one exists, the connection must succeed; refusal or timeout FAILS the test. If none exists (including IPv6-only hosts), print `SKIP: no non-loopback IPv4`; the probe is not counted as passed, and the record-host and url assertions still run and can fail. The server is stopped on pass and on failure. | Issue Tests step 4 | Hosts with no non-loopback IPv4: explicit SKIP (never a silent pass, not counted as a pass); record-host and url assertions still run. Multiple interfaces: only the first qualifying address is probed. Leaked server on failure is mitigated by stopping the server in a finally path. | host-preview suite |

Scope check (AC-5): passes when the changed paths from `git diff --name-only`, plus untracked files, ignoring `.uncle/` workflow files, are exactly `skills/uncle-build/SKILL.md`, `scripts/tests/chat-skill-test.py` and `scripts/tests/host-preview-test.py`. Any other changed path fails the check.

## 10. Compatibility
No interface changes.

## 12. Error behavior
None changed.

## 14. Rollback plan
Revert the three files with git; no persisted state.

## 16/17. Automated and regression tests
Commands live in the baseline: `bash scripts/run-python-tests.sh` (default tier incl. host-preview) and `bash scripts/run-python-tests.sh -- chat-skill` (not in the critical tier). Bug-style regression: removing the new SKILL.md rule makes the `warning-page` removal case and REQUIRED check fail before the edit, pass after.

## 18. Manual verification
Live, outside this repo (LIVE_VERIFICATION phase, not a coding prerequisite): issue Checks 1-5 against real Daytona, after the external script and release (#236) exist. Not performable here; must be recorded BLOCKED, never PASS.

## Restrictions

| ID | Source | Property | Mechanism | CAP | Phase | Requirement |
|---|---|---|---|---|---|---|
| R-1 | USER (issue Fix 5) | Rule 6 is conditional ('if Daytona shows a warning page, continue past it'), applies to every relayed Preview link, names the phrase 'warning page' and quotes no button name | SKILL.md rule 6 plus case-insensitive `warning\s+page` regex that matches only the rule-6 line containing both 'warning page' and 'continue'; a forbidden pattern rejects quoted button labels in the skill body; a removal case deleting exactly that rule-6 line, and a case containing a quoted button label, are both rejected | CAP-SKILL | CODING | AC-1 |
| R-2 | REPOSITORY (chat-skill-test.py:13) | Body <= 60 lines (body only), no forbidden phrases; rule 6 positioned after rule 5; the chat-skill test asserts numbered rules 1 to 6 appear in order (existing rules 1-5 retained) and the body is at most 60 lines; the current line count is recorded in implementation notes | Rule 6 is one line appended after rule 5 (keep rule to 1-2 lines); the body (not the whole file) stays at or under 60 lines. Record the current body line count in implementation notes. If rule 6 would push the body over 60 lines, condense an existing non-rule line; never raise the cap and never drop rule 6. Add ordered-rules and line-cap assertions to chat-skill-test.py. | CAP-SKILL | CODING | AC-1 |
| R-3 | USER (issue Tests) | Wildcard host recorded as 0.0.0.0; recorded url host stays exactly 127.0.0.1 and 0.0.0.0 appears only in preview.json's host field; when a non-loopback IPv4 exists, GET http://<first non-loopback IPv4>:<port>/ returns HTTP 200 with the same body as loopback within 5 seconds; the probe reports its outcome explicitly (PASS, FAIL or SKIP), is local-only, and stops the server on pass and failure | Test edit; run via python runner. Probe target is the first non-loopback, non-link-local IPv4 address from local interfaces. Probe makes a local-only GET http://<address>:<port>/ with a 5s timeout and no outbound calls; it passes only if it returns HTTP 200 with the same body as loopback. A failed connection or mismatch to an existing address FAILS. With no such address (e.g. IPv6-only) the test prints SKIP, does not count the probe as passed, and does not fail. The record-host assertions always run, and the server is stopped on pass and failure. | CAP-PYRUN | CODING | AC-3 |

Feasibility: `scripts/run-python-tests.sh` supports `-- suite` (usage line 14, inspected). CAP-PYRUN and CAP-SKILL need no credentials.

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: rule 6 is conditional (if Daytona shows a warning page, continue past it), applies to every relayed Preview link, matches case-insensitive `warning\s+page`, and quotes no button name | B-4 | I-1 | SKILL.md | chat-skill suite: REQUIRED pattern matches the phrase 'warning page' (case-insensitive, `warning\s+page`), chat-skill suite: forbidden pattern rejects quoted button labels, chat-skill suite: removal case proves a skill containing a quoted button label is rejected | Live Check 1 |
| AC-2 | B-4 | I-1 | chat-skill-test.py | chat-skill suite: existing five removal cases (rules 1-5) stay unchanged; the new warning-page removal case is appended after them, chat-skill suite: the `warning-page` removal case fails the suite when the 'warning page' phrase is removed, chat-skill suite: the quoted-button-label removal case fails the suite | none |
| AC-3: the wildcard-host test asserts the record host is `0.0.0.0`. It probes the first non-loopback, non-link-local IPv4 address: GET http://<that address>:<port>/ must return HTTP 200 with the same body as loopback within 5 seconds; a failed connection, non-200 status, differing body or timeout fails the test. When no such IPv4 address exists (including IPv6-only hosts), the test prints SKIP and passes. | B-2 | I-3 | host-preview-test.py | host-preview suite: record host is 0.0.0.0; non-loopback probe passes if an IPv4 exists, else prints SKIP, is not counted as passed, and does not fail | Live address check |
| AC-4: existing behavior is preserved; the chat-skill test asserts numbered rules 1 to 6 appear in order (rules 1-5 remain) and the body is at most 60 lines, with the current line count recorded. | B-1, B-3 | I-2 | all | default python tier | none |

## Implementation sequence

1. Skill rule and its test pattern (shared contract, edited together so the suite never sits half-changed). Order: first add the test pattern and removal case, run `bash scripts/run-python-tests.sh -- chat-skill` explicitly (the suite is outside the critical tier) and record the failing run ("missing rule: warning-page") in .uncle/docs/IMPLEMENTATION_NOTES.md; then edit SKILL.md, rerun the same command and record the passing run.
   Owns: `skills/uncle-build/SKILL.md`, `scripts/tests/chat-skill-test.py`
2. Wildcard host test strengthening (independent of step 1)
   Owns: `scripts/tests/host-preview-test.py`

## 21. Scope cuts

Cut first: the non-loopback IPv4 probe in step 2 (keep the record-host and recorded-url assertions). If cut, AC-3's non-loopback clause must be recorded as unverified in implementation notes, never as passed; a probe that runs and finds no address prints SKIP instead. Never cut step 1.

## 22. Risks
- The end-to-end path stays unproven until external work and live checks happen; this change does not close issue 235 alone.
- Out-of-repo items (#236 release, build script autoStopInterval/autoDeleteInterval, 3600s lifetime) are not delivered here; state this in implementation notes.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan left the no-warning case undefined; a conditional wording applies safely to any relayed Preview link. | Row s4.1.r1 and R-1 now require conditional wording: if Daytona shows a warning page, continue past it; it applies to every relayed Preview link. |
| AR-002 | Accepted | An undefined match rule lets skill text, regex and removal case diverge; fixing it removes ambiguity. | Row s4.1.r2 defines the warning-page pattern as case-insensitive warning\s+page; quoted button labels fail the forbidden-phrase check. |
| AR-003 | Accepted | AC-3 needs a defined outcome when no non-loopback IPv4 exists: SKIP is printed, test passes; a failed connect on an existing address fails. | Edited s4.1.r3, R-3 and AC-3 to define SKIP-pass when no address exists and FAIL on connection failure. |
| AR-004 | Accepted | The probe target and failure handling must be deterministic to avoid ambiguity and flakiness. | Edited s4.1.r3 and R-3 to probe the first non-loopback, non-link-local IPv4 with a 2s timeout; IPv6-only is SKIP. |
| AR-005 | Accepted | Placement and cap scope were unstated; fixing both removes ambiguity. | R-2 and s4.1.r1-adjacent text now say rule 6 is one line appended after rule 5 and the body stays at or under 60 lines. |
| AR-006 | Accepted | A loose pattern could match unrelated text; anchoring it to the rule-6 line prevents false passes. | s4.1.r2 and R-1 now require the pattern to match only the rule-6 line with 'warning page' and 'continue', and the removal case to delete exactly that line. |
| AR-007 | Accepted | The 60-line cap and a new rule can collide; a stated resolution order removes the ambiguity. | R-2 mechanism now says: if rule 6 pushes the body over 60 lines, condense an existing non-rule line; never raise the cap or drop rule 6. |
| AR-008 | Accepted | The probe's find, fail and skip behavior must be explicit so a skip cannot pass silently or hide a refusal. | s4.1.r3 now defines the non-loopback IPv4 probe: connect and fail on refusal; with none, print SKIP while record-host assertions still run. |
| AR-009 | Accepted | The plan was silent on existing removal cases; keeping them unchanged protects AC-4 preservation. | Traceability row AC-2 tests now state the five existing removal cases stay unchanged and the new case is appended after them. |
| AR-010 | Accepted | Unbounded 'continue past it' could be read as advice to bypass warnings for any URL, weakening untrusted-output handling. | Change-impact row s4.1.r1 now limits rule 6 to the Preview link from the build output and forbids advising continuing past warnings for any other URL. |
| AR-011 | Accepted | The probe's locality and cleanup were unstated; local-only, skip-when-none and server shutdown are cheap, real constraints. | Row s4.1.r3 change and risk now require local-only addresses, no outbound calls, skip when none, and server stop on pass and failure. |
| AR-012 | Accepted | I-3 (url stays on loopback) had no test pinning it; asserting the recorded url host closes that gap. | Row s4.1.r3 adds an assertion that the recorded url host is 127.0.0.1 and 0.0.0.0 appears only in preview.json's host field; R-3 property updated. |
| AR-013 | Accepted | A silent skip is indistinguishable from a pass; the test must report SKIP explicitly and not count it as passed. | R-3 and AC-3 now state: with no non-loopback IPv4 the test prints SKIP, does not count the probe as passed, and does not fail. |
| AR-014 | Accepted | The match wording and the quoted-button check need to be fixed so the test can reject a skill that names a button. | R-1, AC-1 and AC-2 now fix the regex on 'warning page', add a forbidden pattern for quoted button labels, and add a removal case proving such a skill is rejected. |
| AR-015 | Accepted | Plan did not say how the test confirms rules 1-5 remain and rule 6 follows. | R-2 and AC-4 now require the chat-skill test to assert numbered rules 1-6 in order and body <=60 lines, with current line count recorded. |
| AR-016 | Accepted | AC-3 left 'answers', address choice and timeout undefined. | R-3 and AC-3 define the probe: first non-loopback IPv4, GET / returns HTTP 200 with the same body as loopback within 5 seconds. |
| AR-017 | Accepted | A pass/fail rule for the scope check removes ambiguity in AC-5 verification. | Added a scope-check pass rule to the change-impact table (s4) naming the three allowed paths, ignoring .uncle/ files. |
| AR-018 | Accepted | The before/after regression claim needs recorded evidence, and the chat-skill suite is outside the critical tier so must be run explicitly. | Step 1 now requires running the chat-skill suite before and after the SKILL.md edit and recording both runs in implementation notes. |
