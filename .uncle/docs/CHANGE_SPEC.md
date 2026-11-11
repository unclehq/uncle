# Change spec

Omitted sections: Performance (none); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Bug fix spanning three repositories/systems; only the verification tooling and handoff are changeable in this repo.

## 2. Problem statement
Hosted builds cannot give a preview link: release grant, build-script link request/sandbox keep, and live proof never shipped (see CHANGE_REQUEST.md, baseline sec. 1).

## 3. Current behavior
Baseline B-1..B-6. No in-repo artifact detects a missing signed-link grant.

## 4. Desired behavior
Release grants include publisher `daytona`, `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url`, `require_approval` false; build script prints `Preview: <url> (works until HH:MM UTC)` with expiry <= 3600 s and sandbox kept; a pre-publish check proves the grant is present; live checks 1-5 recorded on the issue.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Run grant checker on a release definition containing the signed-link grant | No checker | Exit 0, prints OK | python test AC-1 |
| SB-2 | ADD | Checker on definition missing the grant, or with it but `require_approval` true, wrong publisher/method/path, or unparseable/missing file | n/a | Nonzero exit, names the missing/invalid element | python test AC-2 |
| SB-3 | PRESERVE | Host preview hook / serve / default bind | See B-1..B-4 | Unchanged | existing suites AC-4 |
| SB-4 | PRESERVE | SKILL.md relay rules | B-5 | Unchanged | existing tests AC-4 |
| SB-5 | ADD | Release published with grant (external) | No grant | Revision recorded on issue | manual AC-5 |
| SB-6 | ADD | Build script run (external) | No link | `Preview:` line, expiry <=3600 s, autoStop >= lifetime, autoDelete 0, kept sandbox; 400/403 gives reason and no `Preview:` | external-repo tests AC-6 |
| SB-7 | ADD | Live hosted build | none | Checks 1-5 pass | manual AC-7 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Host preview hook never fails the run | hook | host_preview_hook.sh | existing suites |
| I-2 | EXISTING | Host mode only on exact `host` | host_preview.py | mode-check | existing suites |
| I-3 | EXISTING | Only build-output http(s) Preview links are relayed | SKILL.md | rules 4-5 | existing tests |
| I-4 | NEW | Printed end time never later than link expiry; expiry <=3600 s | build script (external) | build script | AC-6 |
| I-5 | NEW | Checker never reports OK unless every grant field matches exactly | checker | checker | AC-1/AC-2 |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Additive only; no existing file's behavior changes.

## 8. Error behavior
Checker: missing/unreadable/invalid-JSON input or no matching grant exits nonzero with a reason; never silently passes.

## 10. Security
Link is a bearer credential; checker and docs must not print or store tokens. Grant is read-only GET without approval, as requested.

## 12. Rollback
Delete the added files; external release can be republished without the grant.

## 14. Non-goals
Editing host preview code, hook, SKILL.md, UNCLE_PREVIEW_HOST default, chat-side repo-request gap, and any out-of-repo change performed by this workflow.

## 15. Assumptions and unresolved questions
- Release definition format unknown (UNRESOLVED): checker accepts any JSON where an object has `publisher`=daytona, `method`=GET, `path` equal to the signed-link path, `require_approval`=false (key names may also be nested under a grants list).
- AC-5..AC-7 cannot be performed in this repo; they are LIVE_VERIFICATION and remain open, not PASS.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A checker (`scripts/lib/check_release_grants.py <file>`) exits 0 for a release definition JSON containing a grant object with publisher daytona, method GET, path `/sandbox/{sandboxId}/ports/{port}/signed-preview-url`, require_approval false. | bash scripts/run-python-tests.sh -- release-grants |
| AC-2 | The checker exits nonzero with a reason for: missing grant, require_approval true or absent, wrong publisher/method/path, invalid JSON, missing file. | bash scripts/run-python-tests.sh -- release-grants (each case asserts nonzero and reason text) |
| AC-3 | A handoff doc `docs/preview-link-release.md` states the grant, build-script requirements (expiresInSeconds<=3600, autoStopInterval>=lifetime minutes, autoDeleteInterval 0, Preview line format, keep/delete rules) and live checks 1-5, and says they are not done by this repo. | manual read; test asserts file exists and names the grant path |
| AC-4 | Existing host preview behavior, hook, default bind and SKILL.md are unmodified and existing suites show no regression versus baseline. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh vs baseline; git diff shows no change to those files |
| AC-5 | Release grant published and revision number recorded on issue 251 (external, LIVE_VERIFICATION). | manual: run checker on the release definition before publish; record revision |
| AC-6 | Build script (external repo) meets SB-6/I-4 with mocked-publisher tests. | external repository tests; reported, not run here |
| AC-7 | Checks 1-5 of the issue pass on a real hosted build and are posted on the issue. | manual live run; unperformed unless a human supplies it |

