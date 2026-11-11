# Change spec — Issue 253

Omitted sections: Performance, Security (beyond S below), Migration, Prototype isolation (not applicable)

## 1. Change type
Bug fix.

## 2. Problem statement
Hosted `--noui` builds print a loopback `Preview:` line and start a redundant preview server; chat rules would relay the unusable link.

## 3-4. Current / desired behavior
See B-1..B-7 in baseline. Desired: hosted prints no `Preview:` from this runner and starts no server; local prints `Local preview:`; chat relays only https links.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | `--noui`, host mode (UNCLE_PREVIEW_MODE=host or UNCLE_HOSTED=1), live preview-server state | `Preview: <loopback>` | no `Preview:` or `Local preview:` line | headless-preview-test |
| SB-2 | MODIFY | same, build completes | finish() starts server, prints kill line | finish() returns [] and starts nothing; poll() starts nothing | headless-preview-test |
| SB-3 | MODIFY | local, live preview-server | `Preview: http://127.0.0.1:P/` | `Local preview: http://127.0.0.1:P/` | headless-preview-test |
| SB-4 | MODIFY | local, finish() starts server | `Preview: the server (pid N) ... kill N` and its two failure lines | same text prefixed `Local preview:` | headless-preview-open-test, headless-preview-test |
| SB-5 | PRESERVE | UNCLE_NOUI_PREVIEW=0 / WORKFLOW_PREVIEW_OPEN_BROWSER=0; B-5; B-6 | as baseline | unchanged | existing tests |
| SB-6 | MODIFY | chat rule 5 | relay http or https | relay only https; never localhost/127.0.0.1/[::1]; if only local Preview: lines, say no link was provided | chat-skill-test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | Hosted runs: `--noui` runner emits no preview line and starts no preview server | uncle_headless/headless_preview | `enabled()` and scan guard | headless-preview-test |
| SI-2 | NEW | `Preview:` prefix never precedes a loopback address from this runner | headless output | label change | headless tests |
| SI-3 | NEW | Skill rule forbids relaying local addresses | SKILL.md | chat-skill checker | chat-skill-test + bad variant |
| SI-4 | EXISTING | I-1..I-4 | baseline | unchanged | existing tests |

No RELAXED or REMOVED invariants. Note rule 5 narrows from http/https to https (stricter).

## 7. Compatibility
Any consumer parsing `Preview: http://127.0.0.1` from local `--noui` output must read `Local preview:`; required by request.

## 8. Failure behavior
Host-mode detection failure defaults to non-hosted behavior (env absent). No new exceptions.

## 12. Rollback
Revert the commit; no persisted state.

## 14. Non-goals
Changing `App:` lines, host_preview.py, hook scripts, TUI, or host signed-link production.

## 15. Assumptions
Hosted check = `UNCLE_PREVIEW_MODE=='host'` or `UNCLE_HOSTED=='1'`. Existing tests asserting the old label are intentionally updated (requirement-based: request item 2).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With UNCLE_PREVIEW_MODE=host (and separately UNCLE_HOSTED=1) and a live preview-server state file, uncle_headless prints no line starting `Preview:` or `Local preview:` for it. | headless-preview-test new cases |
| AC-2 | In host mode HeadlessPreview.enabled() is False, poll() and finish() start nothing and finish() returns []. | headless-preview-test new case with a start spy |
| AC-3 | Without host mode, the loopback address prints as `Local preview: http://127.0.0.1:P/`; final server lines (started, could-not-start, no-address) start with `Local preview:`. | headless-preview-test, headless-preview-open-test |
| AC-4 | UNCLE_NOUI_PREVIEW=0, WORKFLOW_PREVIEW_OPEN_BROWSER=0, App: lines and URL rejection behavior are unchanged. | existing headless-preview tests |
| AC-5 | SKILL.md rule 5 relays only https links, never localhost/127.0.0.1/[::1], and says no link was provided when only local Preview: lines exist; chat-skill-test requires this via a new pattern and a bad variant lacking it is rejected. | chat-skill-test |
| AC-6 | Full shell and Python suites show no new failures versus baseline. | driver verification commands |

