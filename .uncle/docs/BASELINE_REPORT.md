# Baseline report — Issue 236

Omitted sections: Reproduction (needs live host, not available here); Existing failures (none documented in repo; driver baseline is authority)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`. The hosted-build release must list Daytona's signed preview-link call (`GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url`, `require_approval` false) in its script publisher grants. The release definition and build script are NOT in this repository.

## 2. Repository architecture
Uncle workflow driver: shell scripts (`scripts/*.sh`, `scripts/lib/`), Python helpers (`scripts/lib/*.py`, `uncle_tui.py`), skills (`skills/`), tests (`scripts/tests/`). A repo-wide grep (excluding `.uncle`, `docs`) for `signed-preview-url`, `publisher_grants` and a Daytona publisher entry found nothing; no release-definition file exists here.

## 3. Relevant code paths
- `scripts/lib/host_preview.py:281-292` prints `UNCLE_PREVIEW_PORT=<n>` (the port the external script asks a link for).
- `skills/uncle-build/SKILL.md:8-16` chat rules for the `Preview:` line.
Neither needs to change.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Hosted build serves an app | `UNCLE_PREVIEW_PORT=<n>` printed | host_preview.py:288-291 | Yes |
| B-2 | Script requests signed link | Refused (not granted); no `Preview:` line | CHANGE_REQUEST.md (external, not reproducible here) | No (target of change) |
| B-3 | Script creates/deletes sandboxes via Daytona | Allowed by existing grants | CHANGE_REQUEST.md | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Release lists only calls matching exactly one publisher operation | Host publisher (external) | None in repo | Medium |
| I-2 | Existing Daytona grants unchanged | Release definition (external) | None in repo | Medium |

## 6. Contracts
Release grant entry: publisher, method, path, optional `operation_id`, `require_approval`. External.

## 7. Test coverage
No tests in this repo cover the release definition (CHANGE_REQUEST.md "Tests": none). Shell and Python suites use separate temp dirs and no shared ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (Uncle's documented runners). No results run here; the driver's baseline is authoritative. No documented pre-existing failures beyond those the driver records.

## 12. Likely change surface
Outside this repository (release definition, build script). In-repo: none required.

## 13. Regression-sensitive components
None in-repo. External: the release's other Daytona grants.

## 14. Outside the change
`host_preview.py`, `SKILL.md`, all Uncle driver code and tests.

## 15. Unknowns and assumptions
- UNRESOLVED: where the release definition lives and whether this workflow can modify it.
- Assumed the host's Daytona publisher offers the call as the issue states (read 2026-11-10); not verifiable here.

## 16. Initial risk assessment
Low code risk; high delivery risk: no in-repo artifact can carry the fix, so completion depends on an external repository and live-host checks.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

