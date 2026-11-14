# Baseline report

Omitted sections: Reproduction result (not run; needs hosted Daytona); Existing failures (none documented in repo)

## 1. Change-request summary
CHANGE_REQUEST.md (Issue 263): the build script's first signed-link request uses `expiresInSeconds=7200`; host caps at 3600 and returns 400; retry at 3600 works. Fix: ask for <=3600 first, keep retry. Test: mocked publisher.

## 2. Repository architecture
This repo is the Uncle workflow driver (bash + Python): `scripts/*.sh`, `scripts/lib/*.py`, `scripts/tests/*-test.py` and `*.sh`, `skills/uncle-build/SKILL.md`, `docs/`.

## 3. Relevant code paths
- Repo-wide grep for `expiresInSeconds`, `7200`, `signed-preview`, `works until`, `autoStopInterval` (excluding .git/.venv/.uncle) found NO build-script source.
- `docs/preview-link-release.md:13,40-48`: handoff doc stating the build script lives in an external build-script repo and must use expiry <=3600 s. Not code.
- `scripts/lib/check_release_grants.py:15,46,79`: pre-publish check for the signed-preview-url grant only; does not set expiry.
- `skills/uncle-build/SKILL.md:8-17`: relays `Preview:` lines; says link valid up to an hour.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Release grant check on definition | OK/exit 1/exit 2 per grant | check_release_grants.py:46-80; release-grants-test.py | Yes |
| B-2 | Chat reports build output | Relays `Preview:` lines verbatim, https only | SKILL.md:8-17; chat-skill-test.py | Yes |
| B-3 | Hosted build requests signed link | First request asks 7200, host 400, retry 3600 | CHANGE_REQUEST.md table; code NOT in this repo | Behavior to change |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Only an exact boolean-false-approval grant qualifies | check_release_grants.py | release-grants-test.py | High |
| I-2 | Only valid https `Preview:` lines are relayed | SKILL.md | chat-skill-test.py | Medium |

## 6. Interface contracts
Host: `GET /sandbox/{id}/ports/{port}/signed-preview-url?expiresInSeconds=N`, N whole integer 1..3600 else 400 (from CHANGE_REQUEST.md; not verifiable here).

## 7. Existing automated-test coverage
No test in this repo covers the build script's link request. Shell and Python suites use separate temp dirs and no shared ports, so they are run as a parallel group.

## 9. Baseline test results
Commands taken from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (present). Not run by this stage; driver baseline is authoritative. No documented pre-existing failures found; per task notes some Python suites may already fail on a clean checkout.

## 12. Likely change surface
The build script, in an external repo (UNRESOLVED: its location/path is not in this checkout). In-repo: at most `docs/preview-link-release.md`.

## 13. Regression-sensitive components
check_release_grants.py, SKILL.md and their tests.

## 14. Outside the change
Host cap, release grant, SKILL.md, host_preview.py, autoStop/autoDelete settings.

## 15. Unknowns and assumptions
- U-1: Where the build script lives and whether it can be edited in this task. UNRESOLVED.
- U-2: Whether the script's retry logic (#207) is a loop on 400 that lowers lifetime; assumed from the request.

## 16. Initial risk assessment
High: the requested code change cannot be located in this repository; any in-repo work would not fix the reported defect.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

