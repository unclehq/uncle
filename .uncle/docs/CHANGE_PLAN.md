# Change plan — Issue 236

Seeded from [unclehq/uncle#236](https://github.com/unclehq/uncle/issues/236).

Issue 236

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature flag (none); Observability (none); State transitions (none)

> **BLOCKING PLANNING DECISION.** The release definition and build script are not in this repository (grep for `signed-preview-url`, publisher grants, Daytona entries found none). Nothing in-repo can deliver AC-1..AC-6. Either (a) the operator supplies/points the workflow at the release repository, or (b) the in-repo deliverable is limited to a hand-off record (below) and live verification is performed externally. This plan is executable only as (b); (a) needs new authority. Please state which on approval.

## 1. Selected technical approach

Add one grant entry to the external release definition, normalize script `expiresInSeconds` (absent -> set 3600; above 3600 -> lower to 3600; 3600 or less -> unchanged), publish. In this repo, write `IMPLEMENTATION_NOTES.md` carrying the exact entry and the external-change checklist.

Entry:

```
{"publisher":"daytona","method":"GET","path":"/sandbox/{sandboxId}/ports/{port}/signed-preview-url","require_approval":false}
```

Scope limit: the grant path stays the templated form above (host grants cannot constrain `{sandboxId}`/`{port}` per sandbox). The build script must request signed links only for its own sandbox and the port it serves. Diff review must confirm the entry uses exactly these two placeholders and no wider wildcard (no `*`, no truncated path prefix).

## 2-3. Alternatives and rationale
| Alternative | Verdict |
|---|---|
| Add plain `preview-url` grant | Rejected: token in header, unusable by click |
| Set `operation_id` | Rejected: path matches one operation |
| Edit `host_preview.py`/SKILL.md | Rejected: not the cause |
| Add expire POST always | Rejected: only if script ends links early |

## 4. Components to modify

External: release definition grants; build script `expiresInSeconds` handling in the signed-link call: if absent, set it explicitly to 3600; if above 3600, lower it to 3600; if 3600 or less, leave it unchanged. A script that still omits an explicit value or exceeds 3600 fails AC-6; if the external script edit is not permitted, AC-6 is reported FAIL, never PASS. Failure behavior (SI-2): if the host refuses the signed-link request, returns no link, or returns a link whose expiry exceeds 3600 seconds, the build script prints no `Preview:` line (never an over-limit or partial link) and exits normally; the refusal is reported in build output without failing the build. In-repo: `.uncle/docs/IMPLEMENTATION_NOTES.md` only.

## 5. Not to modify

`scripts/`, `skills/`, `uncle_tui.py`, tests, existing grants. AC-5 baseline: IMPLEMENTATION_NOTES.md records the full pre-change and post-change grant lists from the release repo; the only permitted difference is the added entries. Without both lists AC-5 is NOT RUN, not PASS.

## 6. Data flow
Script -> host Daytona publisher: signed-link GET now allowed -> link returned -> `Preview:` line.

## 8. Interface changes
One added grant entry. No API change.

## 10. Compatibility
Existing hires unaffected (host key; no approval). `require_approval` false.

## 12. Error and recovery
Publish refusal -> stop, report the error; do not guess `operation_id`.

## 14. Rollback
Remove the entry; republish.

## 16-17. Automated and regression tests

None applicable in-repo (change request). Driver regression check: `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` must match baseline (no source changes expected, so unchanged).

Approval gating: the host supports approval only for mail on the script surface, so the new signed-preview-url grant cannot be gated by a host approval prompt. The grant is accepted as ungated (`require_approval` false, per AC-4), and reviewer sign-off on the release-definition diff stands in for the host approval gate.

## 18. Manual verification

Live checks LV-1 publish release; LV-2 hosted build shows `Preview:`; LV-3 existing hire installs without prompt (the main compatibility regression guard). Classification: LIVE_VERIFICATION, require host access and the release repo; non-secret prerequisite evidence: release repo path and publish output saved under `.uncle/docs/`. Repeatability: before running, the executor records in the verification report which web app LV-2 builds (name, source path or commit, and the port it serves on; any minimal single-page app that serves on one port qualifies) and which pre-existing hire LV-3 uses (hire name/id and the date it was created, which must predate the release publish). A run that does not record them is NOT RUN, not PASS. LV-3 procedure: using that pre-existing hire, reinstall or update it on the hosted host after LV-1 and count approval prompts. LV-3 passes only if the hire installs with zero approval prompts. The grant entry sets `require_approval` explicitly to `false` (never omitted). Credential handling: the signed preview URL is a bearer credential. It appears only in the live build output, and is never written to `.uncle/docs/`, `IMPLEMENTATION_NOTES.md`, or any saved publish output. LV-2 evidence records only that a `Preview:` line was present and its host/path shape, with the token (query string or token segment) redacted, e.g. `Preview: https://<host>/<redacted>`. Any saved output is checked for the token before it is kept. Missing access: if host access or the release repo is missing, LV-1, LV-2 and LV-3 are each recorded BLOCKED-SETUP, naming the action required (for example: operator supplies the release repo path, or grants host access to publish and run a hosted build). They are never recorded PASS, and while any of them is BLOCKED-SETUP the change is not declared complete.

Additional live checks. LV-4 (refusal path): with the host refusing or returning no signed link, the hosted build prints no `Preview:` line and exits normally; record the exit status and absence of the line. Token scan: after LV-2 and LV-4, scan .uncle/docs/ (and any saved publish output) for the signed-URL token or query string; any hit fails the check and the file must be redacted before the run is accepted. Both are LIVE_VERIFICATION and are BLOCKED-SETUP, never PASS, without host access.

## Restrictions

Selected option: (b). Approval of this plan selects hand-off only. The in-repo deliverable is .uncle/docs/IMPLEMENTATION_NOTES.md. AC-1..AC-6 are recorded BLOCKED-SETUP, not PASS, until the operator supplies the release repository path; IMPLEMENTATION_NOTES.md is not evidence that any of them is met.

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 1 | AC-1 | Grant is GET signed-preview-url, `require_approval` explicitly false (never omitted), no wildcard wider than the templated sandboxId/port path | Single entry above, templated path only; script requests links only for its own sandbox/port; diff review confirms no wider wildcard | Matches one operation | CAP-RELEASE-EDIT | CODING (external) |
| R-2 | USER | Fix 2 | AC-6 | The script ends links early iff it contains a call to the Daytona signed-preview-url expire endpoint; that grep alone decides whether the expire POST grant is added, and it uses the same path template as the GET grant | Step 2 greps the external build script source for an explicit call to the Daytona signed-preview-url expire endpoint and records the grep command and result in IMPLEMENTATION_NOTES.md. Add the expire POST grant, scoped to the same sandbox/port path template as the GET grant, only if the grep finds such a call; otherwise record 'expire grant not added'. | Least privilege | CAP-RELEASE-EDIT | CODING (external) |
| R-3 | USER | Fix 3 | AC-6 | The signed-link call sets expiresInSeconds explicitly and the value is <= 3600; an omitted field is a violation (absent -> set 3600; above 3600 -> lower to 3600; 3600 or less -> unchanged) | Inspect the script: the signed-preview-url call must pass an explicit expiresInSeconds <= 3600. If absent, edit it to 3600 in the external script; if above 3600, lower to 3600; if 3600 or less, leave unchanged. If the external edit is not permitted, report AC-6 FAIL. | Host limit | CAP-SCRIPT-EDIT | CODING (external) |
| R-4 | USER | Fix 4, Checks | AC-2..4 | Publish and verify; without release repo or host access AC-1..AC-6 are BLOCKED-SETUP (not PASS), naming the access needed | LV-1..3 | Real-host evidence | CAP-HOST-LIVE | LIVE_VERIFICATION |

Regression-gate rule (resolves the sections 16-17 vs Risks conflict): `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` matching baseline is solely a no-source-change guard. It proves only that this change touched no in-repo source. It never counts as evidence toward AC-1..AC-6, and no AC may be recorded PASS on the strength of it. AC-1..AC-6 are satisfied only by the external grant diff, the script check and the LV-1..LV-3 live checks; without those, they are not PASS.

Feasibility: CAP-RELEASE-EDIT unavailable in this checkout (repo grep, no file found); CAP-HOST-LIVE unverified here. Missing live access does not block step 1, and step 1 alone completes the in-repo hand-off deliverable, not AC-1..AC-6. Steps 2 and 3 are BLOCKED-SETUP unless the operator supplies the release repo path. Without that access, AC-1..AC-6 (including AC-1, AC-5 and AC-6) are recorded BLOCKED-SETUP, never PASS, naming the action needed (operator supplies the release repo path); IMPLEMENTATION_NOTES.md is not evidence for them, and the change is not declared complete.

Notes ownership: step 1 is the sole in-repo owner of .uncle/docs/IMPLEMENTATION_NOTES.md and creates it with fixed sections: (1) grant entry, (2) step 2 status, (3) step 3 status. Steps 2 and 3 are external operator steps with no in-repo Owns; their outcomes are recorded in sections 2 and 3 of that file. A skipped step 2 is recorded there as 'not performed: no release repo access', and step 3 is then BLOCKED-SETUP.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `.uncle/docs/IMPLEMENTATION_NOTES.md` | Record entry, external edit checklist, live-check status | Only in-repo artifact | None | Driver suites unchanged |
| Release definition (external) | Add signed-link grant | AC-1 | Low | LV-1 |
| Build script (external) | If expiresInSeconds is absent or > 3600, edit it to 3600; otherwise leave unchanged. If the edit is not permitted, AC-6 is FAIL | AC-6 | Low | LV-2 (app and port recorded by executor) |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 (the grant entry sets `require_approval` explicitly to `false`; omission is not accepted) | SB-1 | SI-1 | Release definition | None | LV-1, Release-definition diff (BLOCKED-SETUP if release repo inaccessible; notes are not evidence) |
| AC-2 | SB-1 | SI-1 | Release definition | None | LV-1 |
| AC-3: a hosted build of a named, recorded minimal web app (name/source and port noted by the executor) prints a `Preview:` line with a signed link in build output. The signed URL is never persisted to .uncle/docs or notes, and LV-2 evidence redacts the token. If the host refuses, returns no link, or reports expiry above 3600, no `Preview:` line is printed and the build exits normally. | SB-2 | SI-2 | Release + script | None | LV-2 |
| AC-4: a named, recorded pre-existing hire (identifier and creation date noted by the executor, created before the publish) installs the new release with zero approval prompts (LV-3 passes only if no approval prompt appears). | SB-3 | SI-3 | Release definition | None | LV-3, Reviewer sign-off on the grant diff stands in for the host approval gate (host cannot gate this surface) |
| AC-5 | SB-4 | SI-3 | Release definition | None | Before/after diff of the full release-definition grant list, with pre-change and post-change lists captured from the release repo and saved at .uncle/docs/GRANT_DIFF.md; only the new signed-preview-url entry (and the conditional expire entry, if added) may differ. If the release repo is inaccessible, AC-5 is BLOCKED-SETUP (name the action: grant access to the release repo). If the diff file is missing, AC-5 is NOT RUN, not PASS. IMPLEMENTATION_NOTES.md is not evidence for this check. |
| AC-6: the script sets expiresInSeconds explicitly in the signed-link call, with a value <= 3600; a script that omits the field fails AC-6 (absent -> 3600; above 3600 -> lowered to 3600; 3600 or less -> unchanged). If the host refuses, returns no link, or the returned link reports expiry above 3600, the script prints no `Preview:` line and exits normally. The expire POST grant is added if and only if the script contains a call to the Daytona signed-preview-url expire endpoint (decided by grep, result recorded); otherwise it is recorded as not added. | SB-5 | SI-2 | Script | None | Script review of external build script (BLOCKED-SETUP if inaccessible; notes are not evidence) |

## Implementation sequence

1. Write `IMPLEMENTATION_NOTES.md` with the exact signed-link GET grant entry, the conditional expire POST entry template, and an external-change checklist (S-1; R-1..R-3). The expire POST grant is not written as an unconditional entry: the notes state the rule 'add the expire POST grant only if the script source has an explicit call to the Daytona expire endpoint (found by step 2's grep, scoped to the same path template); otherwise record it as not added', and the outcome is recorded after the script is inspected.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
2. Apply the grant and script check in the external release repo only if the operator supplies its path and write access (S-2; CAP-RELEASE-EDIT; outside this repo, no in-repo Owns). Grep the script source for an explicit call to the Daytona signed-preview-url expire endpoint and record the command and result in the notes. Add the expire POST grant, scoped to the same path template, only if the call exists; otherwise record 'expire grant not added: no expire call found'. If no release repo path or edit access is supplied, edit nothing: append 'step 2 not performed: no release repo access' to the notes and record AC-1..AC-6 as BLOCKED-SETUP (never PASS), naming the action needed (operator supplies the release repo path and write access). The change is not declared complete in that case.
   Depends on: 1
3. Run LV-1..LV-3 only when step 2 was performed and host access exists; record each as PASS or FAIL with evidence in notes (S-3; R-4). If step 2 was not performed (no release repo access), or host access is missing, record LV-1..LV-3 as BLOCKED-SETUP naming the action required (supply the release repo path, a published release, or host access); never PASS, and do not declare the change complete.
   Steps 2 and 3 share the notes file because each appends its own status section. The in-repo deliverable is complete when step 1 exists; that completes only the hand-off record and is not evidence for AC-1..AC-6, which stay BLOCKED-SETUP until steps 2 and 3 are performed.
   Depends on: 2

## Scope cuts under time pressure
Cut first: conditional expire POST entry. Never cut: the signed-link grant and the 3600 limit.

## Risks and unresolved questions
- Blocking decision above (release repo access).
- Host publisher state unverifiable here; if the entry is refused, report rather than adjust.
- A green in-repo suite is not evidence for this change.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Option (b) is the only one executable in this checkout, so the plan states it as selected and records AC-1..AC-6 as BLOCKED-SETUP until the release repo is supplied. | Added a decision block to section 12 and updated R-4, s12.2, and steps 1-3 so AC-1..AC-6 are BLOCKED-SETUP, never PASS, absent the release repo. |
| AR-002 | Accepted | Steps 2 and 3 had no defined behavior without access; absent access is a one-action setup gap, so BLOCKED-SETUP applies and the change must not be declared complete. | Implementation sequence steps 2 and 3 now record BLOCKED-SETUP naming the missing access when absent, never PASS, and the change is not declared complete. |
| AR-003 | Accepted | The expire POST grant needs an objective trigger; step 1 must not write it unconditionally while it is conditional. | R-2, AC-6 and step-1 now say the expire grant is added only if the script calls the Daytona expire endpoint, else recorded as not added. |
| AR-004 | Accepted | The plan left the missing, exactly-3600 and over-3600 cases of expiresInSeconds undefined; a three-way rule removes the ambiguity. | Sections 4 (s3.1) and 1 (s1.1) and rows R-3, AC-6 now state: absent -> set 3600; above 3600 -> lower to 3600; 3600 or less -> unchanged. |
| AR-005 | Accepted | The spec's 'false or omitted' conflicts with the plan's explicit false, and LV-3 lacked a procedure and pass criterion. | Pin require_approval to explicit false in R-1, AC-1 and AC-4; give LV-3 a procedure and a zero-approval-prompt pass criterion in s11.1. |
| AR-006 | Accepted | AC-5 needs a stated baseline; the notes can carry recorded pre- and post-change grant lists even though the diff lives in the external repo. | Section 5 and AC-5 traceability row now require pre-change and post-change grant lists recorded in IMPLEMENTATION_NOTES.md. |
| AR-007 | Accepted | The release definition is external, so AC-5 needs a concrete artifact: a before/after grant-list diff; without it nothing evidences preservation. | Traceability AC-5 now requires a recorded before/after grant diff under .uncle/docs/; a missing diff means NOT RUN, not PASS. |
| AR-008 | Accepted | The regression gate and the 'green suite is not evidence' risk conflict; defining suite parity as a no-source-change guard only removes the contradiction. | Insert a Restrictions block stating suite parity is only a no-source-change guard and never counts toward AC-1..AC-6. |
| AR-009 | Accepted | Live checks LV-1..LV-3 need a stated status when host access is missing; LV-3 is the main compatibility guard and must not be silently skipped or passed. | Section 18 text and step 3 now classify LV-1..LV-3 as BLOCKED-SETUP naming the needed action when host access is missing, and the change is not complete. |
| AR-010 | Accepted | The expire POST trigger lacked an objective test; a grep of the script for the expire call gives a decidable rule. | R-2, AC-6, s13.1.r3 and step-2 now require grepping the script for the expire call, recording the result, and adding the entry only if the call exists. |
| AR-011 | Accepted | The plan left the missing and over-limit expiresInSeconds outcomes undefined; the finding's decision of edit to 3600, else FAIL, is sound. | Sections 4 and R-3, plus the change-impact row, now specify: absent or above 3600 is edited to 3600 in the external script; if the edit is not permitted, AC-6 is FAIL. |
| AR-012 | Accepted | Step 2 was conditional on access with no defined skipped behavior, leaving step 3's status undefined. | Steps 2 and 3 text now record 'step 2 not performed: no release repo access' when skipped and make step 3 BLOCKED-SETUP. |
| AR-013 | Accepted | The templated path covers every sandbox/port the host key reaches; the host grant syntax cannot constrain placeholders, so scoping is enforced by the script and diff review. | Added scope-limit note to s1 and R-1 mechanism: path stays templated, script requests links only for its own sandbox/port, diff review confirms no wider wildcard. |
| AR-014 | Accepted | SI-2 is enforced only by the external script, so an omitted expiresInSeconds would silently use a host default; requiring an explicit value closes that gap. | Edit R-3, AC-6 and s3.1 so the script call must set expiresInSeconds explicitly (<= 3600) and a script that omits it fails AC-6. |
| AR-015 | Accepted | The signed link is a bearer credential printed without human approval, so the plan must forbid persisting it and require redacted evidence. | Section 18 (s11.1) now says the URL appears only in build output, is never written to .uncle/docs or notes, and live-check evidence redacts the token; AC-3 traceability row updated to match. |
| AR-016 | Accepted | The expire POST is an ungated state-changing write, so it needs an objective trigger, same path scoping and a recorded grep result. | R-2 mechanism and step-2 now add the expire grant only if the script source has an explicit expire call, scoped to the same path template, with the grep result recorded in the notes. |
| AR-017 | Accepted | The host supports approval only for mail on the script surface, so the grant cannot be gated; AC-4 requires no prompt, so the plan must state this explicitly. | Added section 10 text and AC-4 requirement/manual fields: grant accepted as ungated; reviewer sign-off on the diff stands in for the host approval gate. |
| AR-018 | Accepted | With the release definition external and inaccessible, no in-repo artifact can evidence AC-1, AC-5 or AC-6, so they must be BLOCKED-SETUP rather than PASS. | Edited s12.2 and the AC-1, AC-5, AC-6 traceability rows to record BLOCKED-SETUP without release-repo access, with IMPLEMENTATION_NOTES.md not counting as evidence. |
| AR-019 | Accepted | Steps 2-3 need external access that the plan itself says is absent, so step 1's sufficiency condition must be explicit. | Edit step-2, step-3, s12.2: BLOCKED-SETUP unless operator supplies release repo path; in-repo deliverable complete when step 1 exists, without claiming AC pass. |
| AR-020 | Accepted | The 'ends links early' condition needs an objective test; a grep for the expire call is checkable and removes ambiguity. | R-2 and AC-6 now state the test: script ends links early iff it contains a call to the Daytona signed-preview-url expire endpoint, decided by grep. |
| AR-021 | Accepted | 'Small web app' and 'existing hire' are unspecified, so live checks are not repeatable; the executor must record exactly what it picked. | Edit s11.1 to require recording the chosen app and hire, and update AC-3, AC-4 and s13.1.r3 to match. |
| AR-022 | Accepted | The refused or no-link path and the over-limit expiry path had no expected output; stating both makes SI-2's failure behavior testable. | Section 4 and AC-3/AC-6 traceability rows state the no-Preview-line, normal-exit outcome when the host refuses, returns no link, or reports expiry above 3600. |
