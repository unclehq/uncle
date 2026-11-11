# Baseline report

Omitted sections: Reproduction result (the live failure is chat-side and outside this repo; not reproducible here); Existing failures (none documented in-repo beyond the Python-suite note below)

## 1. Change-request summary
Issue 251 (CHANGE_REQUEST.md). Hosted builds give no preview link because three parts live OUTSIDE this repository: (a) the release's script-publisher grant for `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url`, (b) the build script's link request / sandbox keep (#207, #208, #235 step 3), (c) the end-to-end live proof (#235 checks 1-5). Host side already works; `UNCLE_PREVIEW_HOST` default stays `127.0.0.1`.

## 2. Repository architecture
Shell drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`) source `scripts/lib/host_preview_hook.sh`, which calls Python `scripts/lib/host_preview.py`. Skill text for the hosted chat Employee lives in `skills/uncle-build/SKILL.md`.

## 3. Relevant code paths
- `scripts/lib/stage-config.sh:47-51` hosted mode defaults `UNCLE_PREVIEW_MODE=host`.
- `scripts/stagegate.sh:7076`, `scripts/change-workflow.sh:5124` call `uncle_host_preview_hook` at COMPLETE.
- `scripts/lib/host_preview_hook.sh:7-17` stops live preview, runs `host_preview.py serve`, ignores failures.
- `scripts/lib/host_preview.py:217` binds `UNCLE_PREVIEW_HOST` (default 127.0.0.1); `:290-301` `serve` prints `UNCLE_PREVIEW_PORT=<n>`, exits 0.
- `skills/uncle-build/SKILL.md` rules 1-6 (relay `Preview:` line; warning-page rule is rule 6).
- `grep signed-preview-url` over the repo (excluding .git/.uncle) finds no file: no grant, release definition or link code exists here.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | COMPLETE in hosted mode | host_preview serve starts app, prints `UNCLE_PREVIEW_PORT=<n>`, exit 0 | host_preview.py:290-301 | Yes |
| B-2 | Host preview failure | Ignored; run completes | host_preview_hook.sh:15-16 | Yes |
| B-3 | Non-host mode | Hook does nothing | host_preview_hook.sh:9 | Yes |
| B-4 | Default bind | 127.0.0.1 | host_preview.py:217 | Yes |
| B-5 | Build output has `Preview:` line | Skill tells Employee to relay verbatim as plain/Markdown link | SKILL.md rules 1-6 | Yes |
| B-6 | Hosted hire asked for preview link | No link possible; no grant/script change shipped | CHANGE_REQUEST live test | No (fixed outside repo) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Host preview hook never fails the driver run | `|| true`, `return 0` in hook | shell suites for host preview (not enumerated; driver baseline) | Medium |
| I-2 | Host mode only on exact lowercase `UNCLE_PREVIEW_MODE=host` | host_preview.py mode-check | same | Medium |
| I-3 | Preview link is relayed only from the build output, http(s) only | SKILL.md rules 4-5 | two tests from PR #241 | Medium |

## 6. Current API, schema, interface contracts
`host_preview.py serve <dir>` stdout `UNCLE_PREVIEW_PORT=<n>`; `.uncle/preview.json`; env `UNCLE_PREVIEW_HOST/PORT/MODE`. Daytona signed-link API (external, observed in the issue): `expiresInSeconds` integer 1-3600 else 400; expire endpoint exists.

## 7. Existing automated-test coverage
Shell suites via `scripts/run-shell-tests.sh` (default tier `scripts/tests/critical-suites.txt`); Python suites `scripts/tests/*-test.py` via `scripts/run-python-tests.sh`. Groups 1 and 2 use separate temp dirs and bind no shared ports (per runner guidance), so they run in parallel. Command 3 runs the new suite explicitly; it does not exist before the change and is expected to fail at baseline.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (both exist). No results produced here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Known: some Python suites already fail on a clean checkout.

## 12. Likely change surface
In-repo: a new pure release-grant checker plus its test and a short handoff doc. Out-of-repo (not changeable here): release definition, build script.

## 13. Regression-sensitive components
`host_preview.py`, `host_preview_hook.sh`, `skills/uncle-build/SKILL.md`, `critical-suites.txt`.

## 14. Outside the change
Host preview code, hook, SKILL.md, `UNCLE_PREVIEW_HOST` default, Daytona host, chat-side repo-request gap (filed separately).

## 15. Unknowns and assumptions
- U-1 Release definition format is unknown and not in repo; checker must be format-tolerant (walk JSON for matching objects). UNRESOLVED until a real definition is supplied.
- U-2 Build script repository and release publishing need access this workflow lacks.
- U-3 Live checks need a real hosted build.

## 16. Initial risk assessment
High: the issue's real fixes cannot be performed or verified from this repo; completing in-repo work must not be read as closing the issue. Low: regression risk to existing code (additive files only).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- release-grants
```

## Parallel verification groups

```text
1 2
```

