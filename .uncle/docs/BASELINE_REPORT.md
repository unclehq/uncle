# Baseline report

Omitted sections: Current API/schema contracts (no schema change; line formats covered in behaviors); Reproduction (read-only analysis, described in B-1); Migration (none)

## 1. Change-request summary
Issue 253 (CHANGE_REQUEST.md): in hosted builds `--noui` prints loopback `Preview:` lines and starts a second preview server; chat rules relay every `Preview:` line. Fix: suppress in hosted mode, label local address `Local preview:`, tighten chat rule 5 to https only.

## 2. Repository architecture
Shell driver + Python libs under `scripts/lib`. `uncle_headless.py` is the `--noui` runner; `headless_preview.py` serves the finished app after a build; `host_preview.py` decides host mode and serves/records the host app (`.uncle/preview.json`). `skills/uncle-build/SKILL.md` gives chat-agent relay rules, checked by `scripts/tests/chat-skill-test.py`.

## 3. Relevant code paths
- `scripts/lib/uncle_headless.py:144` `_URL_RE` loopback-only; `:204-224` `_scan_announcements` prints `Preview: <url>` (preview-server) and `App: <url>`; `:490-494` calls `preview.finish()`; `:494` appends final scan.
- `scripts/lib/headless_preview.py:39-42` `enabled()`; `:155-173` `poll()`; `:175-190` `finish()` (lines `Preview: could not start...`, `Preview: the server did not report...`, `Preview: the server (pid N) keeps running...`).
- `scripts/lib/host_preview.py:34` `is_host_mode(env)` (exactly `host`); `scripts/lib/hosted.py:9-11` UNCLE_HOSTED==`1`.
- `skills/uncle-build/SKILL.md` rules 1 (relay every Preview:), 5 (http or https).
- Tests: `scripts/tests/headless-preview-test.py` (lines 83,103-104,127,293 assert `Preview: http://127.0.0.1...`), `headless-preview-open-test.py:292-293`, `chat-skill-test.py:12-40,150-200` (REQUIRED patterns incl. `http-https-verbatim`).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `--noui` hosted build, live preview-server state | prints `Preview: http://127.0.0.1:P/` | uncle_headless.py:218 | No (MODIFY) |
| B-2 | `--noui` local build, live preview-server state | prints `Preview: <loopback url>` | :218; headless-preview-test.py:83 | Content yes, label changes |
| B-3 | completed app build, no live driver server | finish() starts server, prints `Preview: the server (pid N)...kill N` | headless_preview.py:175-190 | Content yes locally; label changes; none hosted |
| B-4 | UNCLE_NOUI_PREVIEW=0 or WORKFLOW_PREVIEW_OPEN_BROWSER=0 | no early/final server | enabled() | Yes |
| B-5 | `App: <url>` for app-server/preview-vite, `App: launch ...` | printed | :221,:248 | Yes |
| B-6 | non-loopback or oversize URL in state file | rejected, no line | _URL_RE, :181; test :218 | Yes |
| B-7 | chat sees Preview: lines | rule 1 relays all; rule 5 allows http/https | SKILL.md | Rule 5 changes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Only loopback URLs are announced from state files | _URL_RE | headless-preview-test.py:218 | High |
| I-2 | A driver-owned live server is never duplicated | server_alive() in poll/finish | headless-preview-test.py | High |
| I-3 | Skill body <=60 lines and every REQUIRED rule present, forbidden phrases absent | chat-skill-test check() | chat-skill-test.py | High |
| I-4 | Announcements are read-only on state files | _scan_announcements try/except | headless-preview-test.py | Medium |

## 7. Existing automated-test coverage
Python suites `headless-preview`, `chat-skill` (hyphenated `-test.py`) and shell suite `headless-preview-open` (in critical-suites.txt:126). Runners: `scripts/run-python-tests.sh`, `scripts/run-shell-tests.sh`. Tests share temp dirs per case; no groups declared (serial) to avoid reliance on unmeasured independence.

## 9. Baseline test results
Not run in this stage (driver baseline authoritative: `.uncle/workflow/green-check.baseline.tsv`). Commands derived from CLAUDE.md-mandated runners and scripts/ listing. Some Python suites are known to fail on a clean checkout per runner docs; unlisted here which.

## 10. Existing failures
UNRESOLVED: none known to this stage beyond the generic note in section 9.

## 12. Likely change surface
`headless_preview.py`, `uncle_headless.py`, `SKILL.md`, and tests `headless-preview-test.py`, `headless-preview-open-test.py`, `chat-skill-test.py`.

## 13. Regression-sensitive components
Local `--noui` flow (early page poll, final finish), driver-owned server de-dup, chat skill checker patterns.

## 14. Explicitly outside the change
host_preview.py, host_preview_hook.sh, stage-config.sh, `App:` line behavior, the driver's `preview_server.py`, TUI.

## 15. Unknowns and assumptions
- Assumption: hosted == `UNCLE_PREVIEW_MODE=host` or `UNCLE_HOSTED=1` (per request).
- `App:` loopback lines in hosted mode are also unreachable but chat rules do not relay them; left unchanged.
- Existing tests assert the old `Preview:` loopback label; they must be updated per request item 2.

## 16. Initial risk assessment
Low. Risk: missed `Preview:` literal in a test or doc expecting the old label; chat-skill checker pattern coupling to rule wording.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- headless-preview
bash scripts/run-python-tests.sh -- chat-skill
```

