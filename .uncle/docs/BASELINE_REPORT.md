# Baseline Report — Issue 117

Omitted sections: Reproduction (feature, not bug); Baseline test results beyond provenance (driver supplies)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md: offer a sanitized, user-confirmed `gh issue create --repo unclehq/uncle` from the recovery UI on non-recoverable tool/driver failures, with per-stage resolved runner/model/effort.

## 2. Repository architecture
- Bash drivers (`scripts/workflow.sh`, `scripts/change-workflow.sh`, `scripts/stagegate.sh`) with helpers in `scripts/lib/` (bash + Python).
- Python TUI `uncle_tui.py` (7.7k lines) hosts the recovery chat (triage master).
- Tests: `scripts/tests/*-test.sh` and `*-test.py` (hyphenated names).

## 3. Relevant code paths
- `scripts/lib/triage.sh` writes `.uncle/workflow/TRIAGE.md` bundle on stage-failure EXIT trap (header lines 1-40).
- `scripts/lib/triage_chat.py:20` `CLASSES` incl. `tool bug`; `parse_reply` (:48) extracts classification from a triage proposal.
- `uncle_tui.py:4090` `_triage_init` (state incl. `triage_classification`), `:4109` `_maybe_auto_triage`, `:4129` `open_triage` (recovery banner: /do N, /resume), `:4163` `_triage_turn`.
- `uncle_tui.py:3076` slash-command handling area for triage/recovery input.
- `scripts/lib/perf_record.py:57-93` writes one record per model attempt (kind, stage, status, runner, model, effort, ended_at) into `.uncle/workflow/session-totals.json` `records`.
- `scripts/lib/evidence_io.py:21` `_records(state)` reads them; `scripts/lib/envelope.py:253` `producer()` is an existing precedent for per-stage runner/model from records (never from global default).
- `scripts/lib/chat.py:21` `sanitize()` redacts keys/auth headers and control chars.
- `scripts/lib/github_issues.py:26` `gh()` read-only gh wrapper (timeout, no prompt, GH_PROMPT_DISABLED).
- `prompts/triage.md:73` instructs triage to write local `.uncle/workflow/triage-issue-<turn>.md` draft.
- `VERSION` file holds Uncle version.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | Stage failure exit | TUI auto-opens recovery chat with diagnosis turn | uncle_tui.py:4109-4147 | Yes |
| B2 | Triage replies with classification | Parsed into one of 4 classes; proposals listed | triage_chat.py:48-90 | Yes |
| B3 | Triage writes issue draft | Local `triage-issue-N.md` only; guard applies it | triage-chat-test.py:469 | Yes |
| B4 | Human stop / decline / clean exit | Triage not auto-opened | uncle_tui.py:4110-4120 | Yes |
| B5 | /do N, /resume in recovery | Execute proposal / resume driver | uncle_tui.py:3076 | Yes |
| B6 | Any input | No GitHub publication path exists | grep: no `issue create` | n/a |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Triage never writes outside sandbox unless operator selected /do N | triage_guard.py | triage-guard-test.sh | High |
| I2 | Chat text is sanitized of secrets/control chars | chat.py:21 | triage-chat-test.py | Medium |
| I3 | Attempt records carry resolved runner/model/effort | perf_record.py:64 | envelope tests | Medium |
| I4 | Triage never auto-opens on human stop | uncle_tui.py:4112-4120 | triage-resume-test.sh | High |

## 6. Interface contracts
- `session-totals.json` records schema above; `TRIAGE.md` bundle; triage reply grammar. No GitHub write API exists.

## 7. Existing automated-test coverage
`scripts/tests/triage-chat-test.py`, `triage-bundle-test.sh`, `triage-guard-test.sh`, `triage-resume-test.sh`, `tui-*-test.py`. No coverage of redaction of absolute paths or of gh publication. Shell and Python runners use separate temp dirs and no shared ports, hence one parallel group.

## 9. Baseline test results
Commands taken from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (CLAUDE.md/task guidance). Not run here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites are documented to fail on a clean checkout.

## 10. Existing failures
UNRESOLVED until driver baseline; some Python suites known to fail pre-change.

## 12. Likely change surface
New `scripts/lib/bug_report.py`; `uncle_tui.py` (recovery command + preview/confirm UI); new tests; optionally `prompts/triage.md` unchanged.

## 13. Regression-sensitive components
`uncle_tui.py` recovery/chat input handling; triage draft preservation; `chat.sanitize`.

## 14. Outside the change
Driver shell stages, triage_guard, perf_record schema, diagnostic bundle upload (opt-in bundle is optional/deferred).

## 15. Unknowns and assumptions
- Role (agent/reviewer/worker) and attempt number: derive from record `kind` and count of records for the stage; fall back to `unavailable`.
- Source revision and install type derived from `git rev-parse` of ROOT / path heuristics; `unavailable` on failure.

## 16. Initial risk
Medium: leaking paths/secrets into a public repo issue; mitigated by allow-list construction plus redaction.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

