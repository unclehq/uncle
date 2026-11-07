# Baseline report — Issue 182

Omitted sections: Reproduction (feature, not a bug); Baseline test results detail (driver supplies, see section 9)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 182): Bedrock runner configured by region + bearer token only; always Converse; remove `base_url`/`api_compatibility`; list foundation models + paginated inference profiles; never send temperature (Bedrock only); migrate legacy configs.

## 2. Repository architecture
- `aws-bedrock` is a *profile* of the Self Hosted HTTP runner (`scripts/lib/self_hosted.py` `BEDROCK`, line 28), separate key file `.uncle/aws-bedrock-keys.json` (self_hosted.py:34).
- Transport/agent loop: `scripts/lib/self_hosted_http.py`. Protocol adapters: `scripts/lib/bedrock_protocols.py` (openai/anthropic/converse, 135 lines).
- UI: `uncle_tui.py` (Configure section `bedrock`); shell fallback `uncle` (lines ~755-940) delegates to `python3 scripts/lib/self_hosted.py models|choose-model|set-key|apply-all aws-bedrock`.
- Stage wiring: `scripts/lib/stage-config.sh`, `supervisor*.py`, `self_hosted_performance.py` (reuse key excludes Bedrock temperature, lines 232-264).

## 3. Relevant code paths
| Area | Location |
|---|---|
| Connection validation/save (URL check) | self_hosted.py:72-130 (`_bedrock_url_ok`, `save_keys`) |
| Anthropic discovery + region regex | self_hosted.py:167-207 (`bedrock_control_url`, `discover_anthropic_models`) |
| `refresh_models(keys, base_url, api_key, protocol)` | self_hosted.py:214-221 |
| Request settings, URL/https checks, `_protocol` from `WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY` | self_hosted.py:286-350 |
| Shell menus: `profile_menu`, `main` | self_hosted.py:1996-2083 |
| Dispatch: `compatible_post`, `_require_choices`, `_bedrock_native_post` | self_hosted_http.py:158-224 |
| Temperature: `sampling`, `_strip_temperature` | self_hosted_http.py:1023-1045 |
| `capabilities()` network probe via `detect_flavor(base_url)` | self_hosted_http.py:1001-1006, used 1081 |
| Protocol adapters | bedrock_protocols.py:1-135 |
| TUI fields/pickers/labels | uncle_tui.py:372-377, 535, 1193-1397, 1447-1506, 1536-1615, 7982 |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | Configure → AWS Bedrock | asks Bedrock URL, token, API Compatibility (OpenAI default/Anthropic/Converse) | uncle_tui.py:1277, 1536 | No (MODIFY) |
| B2 | Refresh models | OpenAI: `{url}/models`; Anthropic: `/foundation-models?byProvider=Anthropic`; Converse uses `/models` | self_hosted.py:214-221 | No (MODIFY) |
| B3 | Stage request, protocol openai (default) | POST `{url}/chat/completions`; anthropic `/v1/messages`; converse `/model/<enc>/converse` | bedrock_protocols.py:30-37 | converse path only |
| B4 | Any Bedrock request | temperature stripped; sampling() returns {} | self_hosted_http.py:1033-1045, 161-162, 214 | Yes |
| B5 | Self Hosted request | temperature behaviour unchanged | self_hosted_http.py:1042 | Yes |
| B6 | Token saved | 0600 file, gitignored, refused if gitignore fails | self_hosted.py:99-129 | Yes |
| B7 | Discovery failure | prior catalog kept, error shown | self_hosted.py:216-220; uncle_tui.py:1398-1402 | Yes |
| B8 | Bedrock isolated from Self Hosted creds/models | separate key file/env prefix `UNCLE_AWS_BEDROCK_` | self_hosted.py:293-300 | Yes |
| B9 | Token redaction | `redact_token` | self_hosted.py:63 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | No Bedrock body has temperature | `_strip_temperature`, `sampling` fail-closed | aws-bedrock-protocols-test.py TemperatureTests; aws-bedrock-test.py | High |
| I2 | Bedrock temperature config/env never splits reuse key | self_hosted_performance.py:256-264 | aws-bedrock-test.py | Medium |
| I3 | Token never over cleartext (http only loopback) | self_hosted.py:322 | aws-bedrock-test.py | High |
| I4 | Token single-line | self_hosted.py:326 | aws-bedrock-test.py | High |
| I5 | Self Hosted state never rewritten by Bedrock | separate key file | aws-bedrock-test.py | Medium |
| I6 | Failed discovery retains catalog | refresh_models commit-after-success | aws-bedrock-test.py | Medium |

## 6. Interface contracts
Key file JSON: `__opencode_connection__` {base_url, api_key, api_compatibility}; `__opencode_models__` {name: {base_url, api_key, model}}; per-stage token at top-level stage key. Config keys `aws-bedrock.base_url`, `aws-bedrock.model`; env `UNCLE_AWS_BEDROCK_{BASE_URL,MODEL,API_KEY}`, `WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY`. `settings()` returns dict with `base_url`, `api_key`, `model`, `_profile`, `_protocol`.

## 7. Existing automated-test coverage
Bedrock suites: `scripts/tests/aws-bedrock-test.py` (~60 tests; uses loopback http servers, 9 refs), `aws-bedrock-protocols-test.py`, `aws-bedrock-configure-test.py`, `aws-bedrock-configure-test.sh`, `aws-bedrock-dispatch-test.sh`; `supervisor-test.py` touches Bedrock. Shell and Python suites use separate tmp dirs/no shared ports, so run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (repo-mandated runners, CLAUDE.md/runner prompts). No result produced here; driver baseline (.uncle/workflow/green-check.baseline.tsv) is authoritative. Known: some Python suites already fail on a clean checkout (per driver guidance).

## 10. Existing failures
Not established here; see driver baseline.

## 12. Likely change surface
self_hosted.py, self_hosted_http.py, bedrock_protocols.py, uncle_tui.py, docs/aws-bedrock.md, README.md, the five Bedrock test files.

## 13. Regression-sensitive components
Self Hosted discovery (`discover_models`) and `settings()` self-hosted branch; temperature paths for Self Hosted; key file save/gitignore; supervisor runner config; reuse-key construction.

## 14. Explicitly outside the change
Self Hosted runner behavior, other runners, stage-config.sh, shell `uncle` menus (delegating only), SigV4/AWS credential auth.

## 15. Unknowns and assumptions
- Tests use loopback http servers for Bedrock; region-derived https endpoints need a test seam (patching, not a production override).
- `capabilities()` probe in `constrained_completion` may hit the runtime URL; must be bypassed for Bedrock.
- Live Bedrock not reachable here.

## 16. Initial risk
Medium: wide touch of Bedrock tests; migration of stored configs; tool-call/schema translation must keep working on Converse only.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

