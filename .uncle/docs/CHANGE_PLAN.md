# Change plan

Omitted sections: Schema, Migration, Concurrency, Feature flag (none apply)

Issue 263

Seeded from [unclehq/uncle#263](https://github.com/unclehq/uncle/issues/263).

## BLOCKING PLANNING DECISION — plan is not ready for implementation of the fix

The build script that sends `expiresInSeconds=7200` is not in this repository. A repo-wide search (excluding .git/.venv/.uncle) finds no `expiresInSeconds`, `7200`, or `works until`. `docs/preview-link-release.md:40-48` states the build script lives in a separate build-script repo and that this repo only holds the handoff doc, the grant checker, and SKILL.md. The requested one-line fix and its mocked-publisher test therefore cannot be made here.

Options (user must pick):

- A. Point the workflow at the build-script repo/path (preferred); then the plan below applies to that file.
- B. Limit this issue to in-repo documentation: add a line to `docs/preview-link-release.md` that the first request must use <=3600. This does NOT fix the reported defect and does not satisfy AC-1 through AC-4; it requires a separately approved documentation-only spec and sequence.
- C. Close/transfer the issue to the build-script repo.

## 1. Selected technical approach
Once the file is located (option A): change the initial lifetime constant to 3600 (derive end time from the same value); keep the retry on refusal. Decision D-1: use 3600 exactly, the host maximum, matching #235/#251.

## 2-3. Alternatives and rationale
Clamp at request time vs. change the constant: constant change is smallest and keeps the retry intact. Removing the retry rejected by the request.

## 4. Components to modify
Build script (external, UNRESOLVED path); optionally `docs/preview-link-release.md` under option B.

## 5. Not to modify
`scripts/lib/check_release_grants.py`, `skills/uncle-build/SKILL.md`, grant tests, host_preview.py.

## 12. Error and recovery
Retry path unchanged.

## 14. Rollback plan
Revert the constant (or the doc line).

## 16. Automated-test strategy

Mocked publisher enforcing 1..3600: asserts first request <=3600, zero refusals on success, retry still works when the mock refuses once, Preview end time equals expiry. Exhausted-retry case: when the mock refuses every permitted attempt, assert retries terminate (attempt count is bounded and equals the permitted maximum), no Preview line is printed, and a failure reason is printed. Regression test fails before the fix (first request 7200) and passes after. Repo verification commands: baseline list.

## 18. Manual verification
Human runs one hosted build and checks the host logs show no refusal (LIVE_VERIFICATION; requires hosted Daytona, not available here).

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | CAP | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Fix | S-1, V-1 | First request <=3600 | Constant change | CAP-EDIT-BUILD-SCRIPT (not feasible here: file absent, grep shows no match) | CODING |
| R-2 | USER | CHANGE_REQUEST.md Fix | S-3 | Retry kept; the Preview end time is computed from the successful request's own start time (time origin) and its own lifetime, not the initial 3600 constant (a successful retry uses its own, shorter lifetime), formatted HH:MM UTC by truncating seconds | Leave retry code; derive the end time from the accepted (successful) request's own lifetime and start time | CAP-EDIT-BUILD-SCRIPT | CODING |
| R-3 | DESIGN | Scope | V-3 | No edits to grant checker | Not in table | none | CODING |

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| Build script (external; path UNRESOLVED) | Initial expiry 7200 -> 3600 | Host cap | Low | Mocked-publisher test (external repo) |
| `docs/preview-link-release.md` | Only under option B: note first request <=3600 | Handoff accuracy | None | None (doc) |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S-1 | V-1 | Build script | mocked first-request assertion (<=3600), every recorded request has integer expiresInSeconds in 1..3600 (success and forced-refusal tests) | hosted build log |
| AC-2 and S-2 (zero refused requests) apply only when the host accepts the first valid request; the test asserts zero refusals in that scenario. An injected initial refusal followed by a successful retry is governed by AC-3 and is exempt from the zero-refusal requirement. | S-2 | V-1 | Build script | zero-refusal assertion (mock host accepts first request; refusals == 0), every recorded request has integer expiresInSeconds in 1..3600 | hosted build log |
| AC-3: When the mock publisher is forced to refuse the first request, the build makes exactly one refusal followed by a successful retry at a shorter lifetime and still obtains its link; this scenario is exempt from the AC-2/S-2 zero-refusal requirement, which applies only when the host accepts the first request. The Preview end time is computed from the successful request's own start time and its own lifetime, truncated to HH:MM UTC. | S-3 | V-2 | Build script | retry assertion (mock refuses once; expects one refusal then success), retry lifetime is an integer in 1..3600 and shorter than the initial 3600 seconds, after forced refusal then success, Preview HH:MM UTC equals the successful retry request's start time plus its own (shorter) lifetime, truncated to the minute, not the initial 3600 | none |
| The printed Preview end time is HH:MM UTC and equals the accepted request's start instant plus that request's expiresInSeconds, truncated (not rounded) to the minute. The clock is frozen at request acceptance in tests. After a successful retry, the retry's own start instant and shorter lifetime determine the value, not the initial 3600-second constant. | S-4 | V-2, V-3 | Build script | Preview line + baseline suites, Frozen mock clock: assert Preview HH:MM UTC equals (acceptance instant + accepted request lifetime) truncated to the minute, on first-request success, Same assertion after a forced initial refusal and successful retry, using the retry's start instant and lifetime | none |
| AC-5 (PRESERVE): when every permitted attempt is refused, retries terminate at the permitted maximum, no Preview line is printed, and a failure reason is printed. | S-5 | V-2 | Build script | exhausted-retry assertion: mock refuses every attempt; attempt count equals permitted maximum, no Preview line, failure reason printed | none |

Completion note: AC-1 through AC-4 are satisfied only by the code change and regression test in the build-script repo (option A). Option B (documentation-only) requires a separately approved documentation-only spec and implementation sequence; it does not satisfy AC-1 through AC-4 of this bug fix.

Applicability note: zero refusals (AC-2/S-2) applies only when the host accepts the first request; the forced-refusal test expects one refusal followed by a successful retry (AC-3/S-3), which satisfies AC-3 and is not a violation of AC-2.

## Implementation sequence

1. Resolve the blocking decision above (user input; no files).
2. Option A only: locate the build script in the build-script repo and add the mocked-publisher regression test; confirm it fails with 7200. External test file (path TBD). The doc line in docs/preview-link-release.md is not part of this step and does not satisfy any AC.
   Depends on: 1
3. Change the initial expiry to 3600, keep retry, confirm test passes.
   external build script (path TBD)
   Depends on: 2

Steps 2 and 3 apply only under option A. Under option B this sequence does not apply: a separately approved documentation-only spec and sequence is required, and completing it does not satisfy AC-1 through AC-4.

## Scope cuts under time pressure
Cut the doc line first; never cut the regression test.

## Risks and unresolved questions
- Build script location unknown (blocking).
- Live verification needs hosted Daytona; not a coding prerequisite.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Option B (doc-only) cannot satisfy AC-1..AC-4, which require a code fix and regression test; the plan must say so and keep sequence and acceptance consistent. | Add s13 note that Option B needs a separately approved doc-only spec/sequence and does not satisfy AC-1..AC-4; step-2 no longer treats the doc edit as completing the fix. |
| AR-002 | Accepted | Zero-refusal (AC-2/S-2) and refusal-then-retry (AC-3/S-3) conflict unless scoped to different scenarios; scoping is a small clarification. | s12.1 AC-2 and AC-3 requirement text now scope zero-refusal to host-accepts-first-request and exempt the injected-refusal retry scenario. |
| AR-003 | Accepted | The plan did not say which attempt supplies the displayed expiry or how seconds map to HH:MM, so tests could disagree. | R-2 and AC-3/AC-4 now require expiry from the successful request's own start time and lifetime, truncated to HH:MM UTC. |
| AR-004 | Accepted | The plan did not say which request fixes the printed expiry after a retry; the retry lifetime is shorter, so the initial constant would give a wrong end time. | Edit R-2, AC-3 and AC-4 so the Preview end time comes from the successful request's lifetime and time origin, and the retry test asserts it. |
| AR-005 | Accepted | The spec requires no Preview line and a printed reason when all attempts fail, and the regression strategy did not cover that case. | Section 16 (s8.1) adds an exhausted-retry test: retries terminate, no Preview line, a failure reason is printed. |
| AR-006 | Accepted | Zero-refusal (AC-2/S-2) and refusal-then-retry (AC-3/S-3) conflict unless their applicability is separated. | Edit AC-2 and AC-3 traceability rows and add a note in s12 scoping zero-refusal to host-accepted first requests. |
| AR-007 | Accepted | Expiry equality needs a defined clock reference, rounding rule, and source request; the plan only said end time equals expiry. | AC-4 requirement and tests now fix the frozen mock clock, truncation to the minute, and use of the accepted request's lifetime including after retry. |
| AR-008 | Accepted | V-1 applies to every signed-link request, so first-request and mock range checks alone leave integrality and the shorter retry unverified. | Add every-request integer 1..3600 and retry-shorter-than-3600 assertions to the traceability rows AC-1, AC-2, AC-3 tests. |
