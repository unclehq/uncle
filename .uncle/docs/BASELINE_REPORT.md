# Baseline Report

Omitted sections: Current API contracts (target code absent); Reproduction (not runnable here)

## 1. Change-request summary
Issue 264 (CHANGE_REQUEST.md): hosted build script `build-with-uncle/scripts/build.py` prints a signed preview link once (`announce_preview`), skips the final link request (`sb.announced`), and keeps `sb.link_expires` from the first link. Builds over an hour hand over an expired link.

## 2. Repository architecture
This repository (Uncle driver: `scripts/`, `scripts/lib/`, `scripts/tests/`, `skills/`, `prompts/`, `docs/`) does NOT contain `build-with-uncle/` or `build.py`. Evidence: `git ls-files` has no such path; grep for `announce_preview`, `sb.announced`, `link_expires`, `autoStopInterval`, `cleanup_expired` returns no match in the working tree; `git log --all -- '*build.py'` is empty. `docs/preview-link-release.md` (lines 1-6, 24-30) states the build script lives in a separate build-script repo and that work on it is external to this repo. The prior fix for #263 (commit dee824c) touched only `.uncle/` artifacts here.

## 3. Relevant code paths
| Path | Relevance |
|---|---|
| `docs/preview-link-release.md` | Documents build-script requirements: `Preview:` line, expiry <= 3600 s, keep sandbox. |
| `scripts/lib/check_release_grants.py` | Checks release grant for GET `/sandbox/{sandboxId}/ports/{port}/signed-preview-url` (line 15, 46). Does not cover the `/expire` POST named as optional in the request. |
| `scripts/tests/release-grants-test.py` | Tests that checker. |
| `skills/uncle-build/SKILL.md` | Chat skill; no build.py reference. |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Run check_release_grants.py on a definition with GET signed-preview-url grant | exit 0 `OK` | docs/preview-link-release.md:20-26 | Yes |
| B-2 | build.py announce/final-link behavior | UNRESOLVED: source not in this repo | grep above | n/a |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Release grant checker accepts only boolean `require_approval:false` GET grant | check_release_grants.py | scripts/tests/release-grants-test.py | Medium (not read in full) |

## 7. Existing automated-test coverage
No test in this repo covers build.py. Shell and Python runners are independent (separate temp dirs), so they are grouped.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (both exist). Not run here, per stage rules; the driver baseline is authoritative. No repository-documented failures were read.

## 12. Likely change surface
UNRESOLVED. The surface named by the request (`build-with-uncle/scripts/build.py`, its tests) is outside this repository.

## 14. Areas explicitly outside the change
Driver scripts (`scripts/*.sh`, `scripts/lib/host_preview.py`), the release checker.

## 15. Unknowns and assumptions
- U-1: Location of the build-script repo and its test harness (mocked publisher and clock) is unknown to this checkout.
- U-2: Whether the release grant must also allow POST `.../expire` (optional step 3).

## 16. Initial risk assessment
High: the requested change cannot be made or tested in this repository. Any edit here would be unrelated to the reported defect.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

