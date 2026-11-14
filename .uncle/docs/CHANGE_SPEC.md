# Change spec

Omitted sections: Performance (none); Migration (none); Prototype isolation (n/a)

## 1. Change type
Bug fix.

## 2. Problem statement
The build script's first signed-link request asks for 7200 s; the host caps at 3600 and logs a refusal error for every hosted build.

## 3. Current behavior
B-3 in baseline: 400 on first request, success on retry.

## 4. Desired behavior
First request uses `expiresInSeconds` <=3600 and succeeds; retry retained for refused requests.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | MODIFY | Build requests signed link | expiresInSeconds=7200 first | First request expiresInSeconds <=3600 (whole number) | Mocked publisher test in build-script repo |
| S-2 | MODIFY | Build gets its link | One refused request, then success | Zero refused link requests | Mocked publisher records no 400 |
| S-3 | PRESERVE | Host refuses a request | Retry at shorter lifetime | Retry kept | Mocked publisher returns 400 once, then 200 |
| S-4 | PRESERVE | Link obtained | Prints `Preview: <url> (works until HH:MM UTC)` matching expiry | Unchanged; end time matches requested lifetime | Mocked publisher test asserts line |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V-1 | NEW | Requested expiry is a single whole number 1..3600 | Every signed-link request | Build script | Mocked publisher test |
| V-2 | EXISTING | Printed end time equals link expiry | Preview line | Build script | Mocked test |
| V-3 | EXISTING | Release grant check unchanged (I-1) | check_release_grants.py | Existing | release-grants-test.py |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Preview line format unchanged.

## 8. Failure behavior
If the host still refuses, existing retry applies; if all fail, build prints no Preview line and a reason.

## 10. Security
Shorter-or-equal lifetime only; never longer than 3600.

## 12. Rollback
Revert the constant in the build script.

## 14. Non-goals
Host cap, grants, autoStop/autoDelete, SKILL.md, retry redesign.

## 15. Assumptions and unresolved questions
UNRESOLVED: the build script source is not in this repository (baseline U-1); the criteria are verifiable only where it lives.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | The build script's first signed-link request has expiresInSeconds <= 3600 (a whole number >= 1). | Mocked-publisher test in the repo containing the build script asserts the first recorded request. |
| AC-2 | A build whose link request is accepted makes no refused (400) link request. | Mocked publisher that enforces the 1..3600 cap records zero refusals. |
| AC-3 | The retry after a refused request is retained and still yields a link. | Mocked publisher refuses the first request; test asserts a retry and a Preview line. |
| AC-4 | The printed end time matches the requested expiry; existing suites in this repo still pass. | Mocked test asserts the Preview line; bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh unchanged versus baseline. |

