# Change Plan: Issue 264

Issue 264

Seeded from [unclehq/uncle#264](https://github.com/unclehq/uncle/issues/264).

Omitted sections: Schema, Migration, Concurrency, Feature flag (none apply)

## BLOCKING PLANNING DECISION — plan is NOT ready for implementation
The change targets `build-with-uncle/scripts/build.py`, which does not exist in this repository (baseline section 2; `docs/preview-link-release.md` says the build script is in a separate repo). I cannot specify line-level edits or run its tests from here, and editing unrelated files here would not fix the defect.

Options:
1. Point this run at the build-script repo (or add it to the working directory), then re-plan against the real symbols `announce_preview`, `signed_preview`, `sb.announced`, `sb.link_expires`, `cleanup_expired`. Recommended.
2. Vendor `build-with-uncle/` into this repo. Needs owner authority.
3. Close #264 here as external and track in the build-script repo.

## 1. Selected technical approach (conditional on option 1, from the request)
At the end of `build`, after the PR, drop the `announced` early return, request a fresh signed link (<= 3600 s), print it as the final `Preview:` line, assign `sb.link_expires` from it. Optional: POST `.../signed-preview-url/{token}/expire` for the earlier link, best effort; failure is ignored and logged.

## 2-3. Alternatives
Renewing periodically during the build: rejected, since the chat agent reads only the final output and it would add requests. Raising the expiry: rejected, host caps at 3600 s.

## 5. Not to modify
Driver scripts and `scripts/lib/check_release_grants.py` in this repo, except an optional grant for the `/expire` POST (decision deferred to option 1).

## 12. Error and recovery
If the final request fails, keep the earlier link as the last line with an expiry warning; do not fail the build. (DESIGN default, revisable.)

## 14. Rollback plan
Revert the build.py commit; no persistence or schema changes.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `build-with-uncle/scripts/build.py` (EXTERNAL, absent here) | Always request final link; set `sb.link_expires` | AC-1..AC-4 | Medium | New mocked publisher/clock test in that repo |
| No file in this repository | None until the blocker is resolved | Target absent | None | Baseline commands unchanged |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: Final preview renewal runs on successful build completion, whether PR creation succeeds, fails, or is skipped (PR creation is not a prerequisite), and the freshly requested link is printed as the final `Preview:` line with sb.link_expires reflecting it for kept sandboxes. After a successful final renewal, the last printed link stays valid for at least 55 minutes after build completion (INV-2 applies only to successful renewal), even for a 70-minute build with a 1-minute early link. If final renewal fails, the build completes with an expiry warning and does not fail, keeps any earlier link and its expiry (sb.link_expires unchanged), reports preview unavailable if no earlier link exists, and is exempt from INV-2. | BH-2 | INV-2 | build.py | external, mocked clock, mocked failure test: early link expired and final renewal request fails; build completes with expiry warning, earlier link and expiry metadata preserved | none |
| AC-2 | BH-3 | INV-3 | build.py | external | none |
| AC-3: Every signed-preview-url request, including retries and fallback requests after a refused link, uses expiresInSeconds no greater than 3600. There is no refusal exemption and no 'no link was refused' qualification. | BH-4 | INV-1 | build.py | external, mocked signing endpoint refuses a request; all later requests (retries and fallbacks) are recorded and every expiresInSeconds is asserted <= 3600 | none |
| AC-4 | BH-1 | none | build.py | external | none |

INV-2 scope: the 55-minute validity guarantee applies only when the final renewal succeeds. On final-request failure the build completes with an expiry warning and the earlier link and expiry metadata are preserved; that outcome is exempt from INV-2 and is covered by the mocked failure test in AC-1. AC-3 test obligation (AR-007): a mocked signing endpoint refuses a request; the test records all requests made afterward (retries and fallbacks) and asserts every expiresInSeconds value is at most 3600, matching INV-1 unconditionally.

Regression test (fail before, pass after): the 1-minute/70-minute mocked test in AC-1.

## Implementation sequence
1. Resolve the blocking decision above (human). Owns: none
2. After the build-script repo is available, re-plan with real file and line references. Owns: none — Depends on: 1

## Scope cuts under time pressure
Cut the optional expire call (BH-5) first.

## Risks and unresolved questions
- Target code not available (blocking).
- Final-link failure behavior is a default, revisable.
- Live verification needs hosted Daytona; not a coding prerequisite.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The keep-earlier-link fallback can print an expired link, so the 55-minute guarantee must apply only to successful renewal. | AC-1 traceability row: requirement and tests now scope INV-2 to successful renewal and add a refresh-failure test with an expired early link. |
| AR-002 | Accepted | Renewal tied to 'after the PR' is undefined when publishing is declined, skipped or PR creation fails; PR creation must not be a prerequisite. | Edit AC-1 in the traceability table to run final renewal at build completion regardless of PR outcome, and add a skipped-PR regression case. |
| AR-003 | Accepted | INV-1 and the host cap apply to every signing request, so the acceptance test must not exempt builds with a refused link. | AC-3 in the traceability table now covers every request, including retries after refusal, with a refused-link test. |
| AR-004 | Accepted | The keep-earlier-link fallback can print an expired link, so INV-2's 55-minute guarantee must apply only to successful renewal and the failure outcome needs its own test. | AC-1 traceability row now requires a mocked refresh-failure test (expired early link, earlier expiry preserved, warning, no build failure) and scopes INV-2 to successful renewal. |
| AR-005 | Accepted | Final renewal must not depend on optional PR creation, or a build that skips publishing keeps the expired early link. | AC-1 row gains the trigger (renewal runs on successful build completion even when PR creation is skipped or fails) and a skipped-PR regression test with kept-sandbox expiry check. |
| AR-006 | Accepted | The nonfatal fallback can print an already-expired early link, which conflicts with an unconditional 55-minute INV-2 oracle; the oracle must be scoped to successful renewal. | AC-1 row now includes a failure-path test with an expired early link, and INV-2 is scoped to successful renewal in the traceability section. |
| AR-007 | Accepted | INV-1 covers every signing request, so AC-3 coverage must include refused-link histories and retries; the qualification hid a possible violation. | Edit AC-3 in the traceability table: unconditional 3600 s cap, refused request plus retries/fallbacks tested; add a s8 note. |
