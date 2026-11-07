# Baseline Report — Issue 178

Omitted sections: Reproduction (feature, not a bug); Schema contracts (no persisted schema beyond key/config files)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (Issue 178): add an AWS Bedrock runner profile that reuses Self Hosted code, never sends temperature, and offers a stored API Compatibility choice (OpenAI / Anthropic / Converse).

## 2. Repository architecture
- `uncle_tui.py` (8466 lines): menus; runner id `"self-hosted"` hard-coded in many places.
- `scripts/lib/self_hosted.py` (2134): config, key file, model discovery, runner entry; `resolve_profile` exists only in the uncommitted tree.
- `scripts/lib/self_hosted_http.py` (1157): OpenAI-compatible transport (`compatible_post` :158, `_request` :925, `_final_call`, `constrained_completion`, `chat` :1138, `temperature()` :547).
- `scripts/lib/self_hosted_performance.py` (373): performance heuristics assuming numeric temperature (~:232, :257).
- `scripts/lib/stage-config.sh` (472), `scripts/stagegate.sh`, shell shims: runner dispatch and per-stage config.
- Tests: `scripts/tests/*-test.py` via `scripts/run-python-tests.sh`; shell suites via `scripts/run-shell-tests.sh`.

## 3. Relevant code paths
`temperature()` self_hosted_http.py:547; request bodies in `_final_call` (~:1000-1030) and `chat` (:1138); `compatible_post` :158; `self_hosted_performance.py` :232/:257; runner id dispatch in `uncle_tui.py`, `stage-config.sh`, `stagegate.sh`.

## 4. Current observable behavior and existing invariants
**Working-tree note:** the checkout carries uncommitted partial work for this issue (HEAD..worktree: 5 source files +227/-72, untracked `docs/aws-bedrock.md`, `scripts/tests/aws-bedrock-test.py`), including `sampling()`, `_strip_temperature`, `_profile` handling and an api-key redaction in `_request`. It is NOT baseline evidence; the driver baseline measures it as-is. The plan treats it as a starting point to be audited, not trusted.

| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Self Hosted request (chat/final/ollama) | body includes `temperature` (default 0, configurable via `WORKFLOW_SELF_HOSTED_TEMPERATURE`, `<stage>.temperature`) | self_hosted_http.py:547 and body builders at HEAD | Yes |
| B-2 | Main menu | Self Hosted entry only; no Bedrock | uncle_tui.py | Yes (add entry) |
| B-3 | Self Hosted key/settings save | stored in Self Hosted key/config files | self_hosted.py | Yes |
| B-4 | Model discovery/refresh, request options, performance | work for Self Hosted | self_hosted*.py | Yes |
| B-5 | Stage dispatch with runner `self-hosted` | shims call self_hosted runner | stage-config.sh, stagegate.sh | Yes |

| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Self Hosted always sends numeric temperature | `temperature()` + body builders | Self Hosted shell/py suites (unverified which) | Medium |
| I-2 | Self Hosted credentials/settings isolated to own files | key-file path in self_hosted.py | self-hosted tests | Medium |
| I-3 | API keys not leaked in errors | none at HEAD for HTTP errors | none | Low |

## 5. Interfaces
Env: `WORKFLOW_SELF_HOSTED_*`, per-stage `<stage>.temperature`; config/key files under Uncle config dir; runner id strings. Bedrock must add parallel `WORKFLOW_AWS_BEDROCK_*` names without altering these.

## 6. Existing automated-test coverage
Shell suites (`scripts/tests/*.sh`) and Python suites (`*-test.py`) run by the two runners. They use separate temp dirs and bind no shared ports, so run in parallel (group `1 2`; measured shell 297s, Python 196s, together ~297s). `aws-bedrock-test.py` is untracked and already present.

## 7. Baseline test results (section 9 source)
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` per CLAUDE.md/driver guidance. No results produced here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites are known to fail on a clean checkout.

## 8. Likely change surface / regression-sensitive / outside
- Surface: files in section 3 plus `docs/aws-bedrock.md`, `scripts/tests/aws-bedrock-test.py`.
- Regression-sensitive: Self Hosted temperature path, menu ordering in uncle_tui.py, stage-config.sh env parsing, performance heuristics.
- Outside: other runners, workflow driver stages, Self Hosted defaults.

## 9. Unknowns and risk
- SigV4 for Converse: unknown; bearer token supported by Bedrock API keys (assumed).
- Risk: hard-coded `self-hosted` strings missed -> Bedrock silently runs as Self Hosted (HIGH). Risk: temperature leaking via defaults/request options (HIGH).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

