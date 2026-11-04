# Change Plan — Issue 117

Omitted sections: Schema/persistence (only new draft file); Concurrency (single-threaded TUI action); Migration (none); Feature flag (none, additive command)

Seeded from [unclehq/uncle#117](https://github.com/unclehq/uncle/issues/117).

Issue 117

## 1. Selected technical approach

New pure-ish module `scripts/lib/bug_report.py` with: `eligible(classification)`, `build_report(state_dir, project_root, uncle_root, stage=None)` -> dict (title, body, fields), `scrub(text, roots)`, `residual_check(text, roots)` -> list of matches, `save_draft(state_dir, report)` -> draft path, `publish(draft_path, runner=subprocess.run)` using `gh` (auth status check then `issue create --repo unclehq/uncle --title --body-file <draft_path>`), and a small CLI. Field validation: every value read from state files (stage, runner, model, effort, role, status) must match `[A-Za-z0-9._:/-]{1,64}` or it renders as `unavailable`; the `stage` argument is validated the same way. Relative references in the body must resolve inside the state dir and contain no `..` segment, otherwise `unavailable`. Residual check: after scrub, `residual_check` re-scans the final title and body for any absolute path (project root, uncle root, home, or any leading-slash absolute path outside the allowed relative `.uncle/workflow` references) and any token pattern; if anything still matches, the report is marked blocked: publish is refused, only the draft is saved, and the preview states why. The preview shows the exact final text that would be published. Draft lifecycle: the draft is `.uncle/workflow/bug-report-N.md`, where N is an integer chosen by the module (never derived from state-file content) and is the lowest unused positive integer among existing `bug-report-*.md` files (1 if none). `save_draft` creates the file exclusively without following symlinks, taking the next free suffix on collision, and never overwrites an existing file. The draft is written before the preview is shown, each `/report` creates a new file, and the draft is kept after a successful publish, a decline, or any failure. `publish` never rebuilds the report: it reads and sends the exact saved bytes that were previewed. `uncle_tui.py` gains a `/report` recovery command: first call builds the report, saves the draft, renders the preview of that draft, and arms a pending confirmation holding the draft path; the next input publishes only if, after trimming whitespace and lowercasing, it equals `yes`; anything else cancels. A repeat `/report` while pending replaces the pending state (and creates a new draft).

## 2. Alternatives
(a) Report via triage master model: rejected, model output not trustworthy for redaction. (b) Shell script: rejected, poor testability. (c) Auto-offer modal: rejected, larger TUI change.

## 3. Why preferred
Deterministic allow-list construction; testable with fake `gh`; minimal TUI surface.

## 4. Decisions

| ID | Decision | Reason |
|---|---|---|
| D1 | Eligibility = triage classification `tool bug` (existing signal at `triage_classification`) | Only existing non-recoverable signal; excludes test failures |
| D2 | Failed stage = the most recent non-speculative record with a non-success status (`status_stage` may name it); attempt = count of non-speculative records for that stage. If no record has a non-success status, stage, attempt, role, exit status, runner, model and effort all render the literal `unavailable`; the last record is never used as a fallback. Any other field without a source (missing/empty session-totals, zero attempts, absent exit status or runner) also renders the literal `unavailable`. | Uses the stage record, never defaults or the last record; absent data is never invented or misattributed, consistent with the `unavailable` rule for missing sources |
| D3 | Role from record kind: review/verification/audit -> reviewer, worker kinds -> worker, else agent | Matches envelope.producer mapping |
| D4 | Diagnostic bundle upload deferred (optional in request) | Out of required AC |
| D5 | Error excerpt = last 20 lines of failing stage log, each line capped 300 chars, after scrub. If the failing-stage log is missing, unreadable or empty, the excerpt renders the literal `unavailable`. Exit status and artifact validation error likewise render `unavailable` when their source is absent. | Concise, bounded; missing sources never crash or fabricate. |
| D6 | Install type: `homebrew` if root path contains `Cellar`/`homebrew`, `git` if `.git` exists, else `unknown` | Cheap heuristic |

## 5. Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Privacy | AC-4, V2 | No secrets/abs paths/prompts/sources; publish refused if scrub leaves any residual path or token pattern | Allow-list fields are the only content included. scrub(text, roots) oracle: absolute project root, uncle root and home dir are replaced by `<project>`, `<uncle>` and `~` (longest root first); each match of the named token-pattern list is replaced by `[REDACTED]`: `ghp_[A-Za-z0-9]+`, `github_pat_[A-Za-z0-9_]+`, `sk-[A-Za-z0-9_-]+`, `Bearer <token>`, `AKIA[0-9A-Z]{16}`, URL userinfo (`scheme://user:pass@` -> `scheme://[REDACTED]@`), and cookie headers (`Cookie:`/`Set-Cookie:` line values). Relative `.uncle/workflow/...` references are exempt. Also chat.sanitize extension applied. State-file values are validated against `[A-Za-z0-9._:/-]{1,64}` else `unavailable`; draft N must be an integer; relative references are confined to the state dir, no `..`. Then a post-scrub residual_check over final title and body: any remaining absolute path or token pattern blocks publish (draft saved only; preview shows the exact final text and the refusal reason). | Cannot leak what is never included | CAP-none | CODING |
| R-2 | USER | CHANGE_REQUEST Privacy | AC-5, V1 | Never auto-publish | publish requires confirm=True; TUI two-step | Explicit gate | CAP-none | CODING |
| R-3 | USER | CHANGE_REQUEST Goal | AC-6 | Target repo unclehq/uncle | argv list with fixed --repo | No shell injection | CAP-gh (tests use fake gh on PATH) | CODING; real gh = LIVE_VERIFICATION optional |
| R-4 | PLATFORM | github_issues.py:26 precedent | AC-6, AC-7 | Non-interactive gh | GH_PROMPT_DISABLED=1, stdin DEVNULL; the auth status check and the issue create call each have their own 30s timeout. Success requires create exit 0 AND a URL: the last stdout line starting with https://. If no such line is found (exit 0 with no URL, extra output without URL), or on nonzero exit or timeout, treat as failure: keep the draft, show the draft fallback, and say the issue may already exist; never report success without a URL. Publish is attempted at most once per confirmation and is never retried automatically. | Observed in inspected symbol gh() | CAP-gh | CODING |
| R-5 | USER | CHANGE_REQUEST Privacy | AC-8, V4 | Preserve triage draft; bug-report drafts are never overwritten, never written through a symlink, and are kept after publish | Never write triage-issue-*. Each /report creates a new draft file named bug-report-N.md (N = lowest unused positive integer), written before the preview. The file is created exclusively (os.open O_CREAT\|O_EXCL\|O_NOFOLLOW), retrying with the next free N on FileExistsError. Existing files and symlinks are never opened for write or overwritten. The draft is kept after a successful publish. | Separate namespace | CAP-none | CODING |

Feasibility evidence: `perf_record.py:64` fields confirmed by inspection; `chat.py:21 sanitize` inspected. Live authenticated publication is not a coding prerequisite.

## 6. Components to modify / not modify

Modify: see change-impact table. Not modify: driver shell stages, `triage_guard.py`, `perf_record.py`, `triage.sh`, `prompts/triage.md`. Existing `triage-issue-*` drafts are never written or overwritten; bug-report drafts use only the separate `bug-report-N.md` namespace.

## 7. Data flow

session-totals.json records + VERSION + git rev + env -> build_report -> scrub -> save draft (exact final text) as lowest-unused `bug-report-N.md` (before the preview) -> preview of the saved draft in TUI -> confirm (`yes`, trimmed, case-insensitive) -> gh publishes the saved draft bytes unchanged (no rebuild between preview and publish). Each `/report` makes a new draft file and replaces any pending state; the draft is kept after publish, cancel or failure.

## 8. State transitions

TUI adds `report_pending` (None | draft path plus report dict). `/report` states: (1) when `eligible(self.triage_classification)` is false (or no classification/recovery), print the fixed refusal line `/report is only available after a tool bug is diagnosed in recovery.` and arm nothing, save no draft, call no gh; (2) when eligible and not pending, build the report, save the draft, render the preview and set `report_pending`; (3) when already pending, build a fresh draft, re-render the preview and replace the pending state. Confirmation rule: while `report_pending` is set, the very next input of any kind (including empty input and slash commands) is consumed by the report flow and is never forwarded to triage chat. After trim + lowercase, only the exact token `yes` publishes the saved previewed draft bytes; every other input (`y`, `no`, empty, any other text, any slash command) cancels the pending report, prints a one-line cancellation message, keeps the saved draft and calls no gh. Exception: `/clear` cancels the pending report and then runs its normal clear behavior; leaving recovery also clears `report_pending`. Pending state is always None after the single consumed input, so at most one input is intercepted. After a publish attempt ends in timeout or no-URL, `report_pending` is cleared, the draft is kept, the message says the issue may already exist, and no automatic retry occurs; a new `/report` is required.

## 9. Interface changes
New recovery command `/report`; banner line in `open_triage` mentions it only when eligible. No other API change.

## 10. Error and recovery

gh missing/unauth/nonzero -> draft kept, message `Saved <relative draft path>. Run: gh auth login, then: gh issue create --repo unclehq/uncle --title <shlex.quote(title)> --body-file <shlex.quote(relative path)>`. gh create timeout after auth passed, or exit 0 with no https:// URL line in stdout -> draft kept, message says the issue may already exist (check github.com/unclehq/uncle/issues before filing again), and publish is not retried. Title rule: the title is scrubbed first, then newlines and quote characters (' and ") are removed, then truncated to at most 80 characters; the copyable command shell-quotes that final title with shlex.quote, so an apostrophe or space cannot break the command. The same final title is used in the preview, draft and gh call. Scrub's absolute-path replacement (project root, uncle root, home) applies only to absolute paths; relative references such as `.uncle/workflow/...` are exempt and are never rewritten. Any report field without a source (missing or empty session-totals, missing failing-stage log, zero attempts, no exit status or validation error) renders the literal `unavailable`; the report is still built and never raises.

## 11. Rollback plan

Revert the commit; no schema or state changes; stray `bug-report-N.md` files (kept after publish or cancel by design) are harmless.

## 12. Automated-test strategy

New `scripts/tests/bug-report-test.py` (unittest, fake `gh` shell script in temp dir prepended to PATH, fixtures with git signing disabled if git used): eligibility (AC-1) including /report refusal with an ineligible class, with no classification and outside recovery (asserts no report_pending, no draft file, no gh invocation) and /report while armed cancels the pending report; runner attribution (AC-2); fields (AC-3) including missing/empty session-totals, missing failing-stage log and zero attempts each rendering the literal `unavailable`; redaction (AC-4); cancel (AC-5); publish (AC-6); unauth/missing gh (AC-7); draft preservation (AC-8). Publish-outcome cases (AC-6/AC-7): fake gh create exits 0 with URL as last stdout line (starting https://) after extra output -> that URL is reported; exits 0 with no https:// line -> failure and draft fallback; auth check or create exceeding 30s (timeout injected via runner) -> failure and draft fallback. For the create timeout after auth passes, and for the no-URL case: draft kept, message says the issue may already exist, create invoked exactly once (no retry). A TUI-level test in the same file exercises `/report` flow through the TUI methods if constructible like `tui-*-test.py`; otherwise module-level CLI test.

Redaction oracle for AC-4 (tests use exactly this list): paths -> `<project>`, `<uncle>`, `~`; tokens -> `[REDACTED]` for ghp_, github_pat_, sk-, Bearer, AKIA, URL userinfo and cookie headers; relative `.uncle/workflow` paths are not altered.

## 13. Regression-test strategy
Existing suites via `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` (parallel group 1 2 per baseline). Defect-injection: tests fail if scrub is disabled, if confirm check is removed, or if global default replaces record value.

## 14. Manual-verification strategy
In a sandbox project force a `tool bug` classification, run `/report`, inspect preview, answer `no`, confirm no issue; with gh unauthenticated answer `yes`, confirm draft + command. Live publish to the real repo is not done automatically.

## 15. Observability

TUI system lines for preview, outcome, draft path (relative). No new logs. Length limits (constants asserted by tests): the title is at most 80 characters and the error excerpt is at most 20 lines of at most 300 characters each; both limits are applied by truncating AFTER scrub, so replacement strings that change text length cannot push the final text over the limit. This supersedes the pre-scrub capping implied by D5. The previewed title and the section 10 fallback command's shell-quoted title both use this same scrubbed title truncated to 80 characters (not 100).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/bug_report.py` | New module | Report build/scrub/draft/publish | Low (new) | `scripts/tests/bug-report-test.py` |
| `uncle_tui.py` | `/report` command, pending-confirm state that intercepts the next input (yes publishes; anything else cancels and is not forwarded to triage chat; `/clear` cancels then runs), banner hint | Recovery UI entry | Medium: chat input path; mitigated by interception tests and existing chat suites | bug-report-test.py (pending-input interception: yes/YES/ yes , no, empty, other text, slash command, /clear, confirms no triage-chat forwarding); existing tui/triage suites |
| `scripts/tests/bug-report-test.py` | New tests | AC-1..AC-8 | Low | self |
| `scripts/tests/bug-report-test.py` acceptance handoff n/a | Non-browser project | n/a | n/a | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: /report is offered only for an eligible `tool bug` triage classification. /report outside an eligible recovery (no classification, ineligible class, or not in recovery) prints a fixed refusal line and arms nothing: no report_pending, no draft, no gh call. /report while a confirmation is armed cancels the pending report. | S1, S2 | V5 | bug_report.eligible, uncle_tui | bug-report-test eligibility, bug-report-test /report refused when ineligible or no classification (no pending, no draft, no gh), bug-report-test /report while armed cancels pending | MC: ineligible class |
| AC-2 | S3, S7 | V3 | bug_report.build_report | attribution test | MC: preview |
| AC-3: report contains the allow-listed fields (stage, attempt, role, runner, model, effort, exit status, bounded error excerpt, artifact validation error, versions/install type); any field without a source renders the literal `unavailable`. | S3 | V2 | bug_report.build_report | fields test, missing-source test: empty/missing session-totals, missing log, zero attempts -> `unavailable` | MC: preview |
| AC-4: scrub maps project root, uncle root and home to `<project>`, `<uncle>` and `~`, and replaces the named token-pattern list (ghp_, github_pat_, sk-, Bearer, AKIA, URL userinfo, cookie headers) with `[REDACTED]`; the report contains no secrets, absolute paths, prompts or sources. | S9 | V2 | scrub | redaction test: one fixture per listed pattern asserts the raw token is absent and `[REDACTED]` present; project root, uncle root and home paths assert `<project>`, `<uncle>`, `~`; relative .uncle/workflow path left intact | MC: preview |
| AC-5 | S5 | V1, V4 | publish, uncle_tui | cancel test | MC: decline |
| AC-6: publish runs gh issue create once against unclehq/uncle and reports the URL (last stdout line starting with https://); on timeout or exit 0 with no URL it keeps the draft, says the issue may already exist, and does not retry. | S4 | V1 | publish | publish test, publish timeout-after-auth test, publish no-URL test | optional live |
| AC-7 | S6 | V4 | publish, save_draft | fallback tests | MC: unauth |
| AC-8 | S8 | V4, V5 | save_draft | hash test, full suites | none |

## Implementation sequence

1. Report module (R-1..R-5, D1-D6) — build_report, scrub, save_draft, publish, eligible, CLI.
   Owns: `scripts/lib/bug_report.py`
2. Tests for module with fake gh, plus a MANDATORY TUI-level test (no CLI-only fallback) driving `/report` through the TUI methods and asserting a pending input is never passed to the triage chat handler. Written against the interfaces in section 1 and the TUI wiring from step 3.
   Owns: `scripts/tests/bug-report-test.py`
   Depends on: 1, 3
3. TUI wiring — `/report` command, pending confirmation, banner hint gated on `eligible(self.triage_classification)`; builds on step 1 interface. The `/report` handler itself also calls `eligible(self.triage_classification)` first and, if false, prints a fixed refusal line (`/report is only available after a tool bug classification.`) without setting report_pending, saving a draft, or calling gh.
   Owns: `uncle_tui.py`
   Depends on: 1
4. Run new test and affected existing suites (triage-chat, tui) locally. This step owns no files: any fix is made as an amendment inside the step that owns the affected file (steps 1-3).
   Depends on: 2, 3

## Scope cuts under time pressure
Cut first: install-type heuristic detail, role mapping nuance (use `agent`), TUI banner hint (keep command). Never cut: confirmation gate, redaction, runner attribution, draft preservation. Diagnostic bundle already deferred.

## Risks and unresolved questions

- Redaction misses novel secret formats: mitigated by allow-list; excerpt is the only free-text and is bounded.
- Failed-stage identification when no non-speculative non-success record exists: stage, attempt, role, exit status, runner, model and effort all render `unavailable`; never falls back to the last record or to defaults.
- No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real gap: plan only hid the banner and never defined /report outside eligible recovery, with no classification, or while armed. | AC-1 traceability requirement and s12.1 test strategy now state the refusal and cancel-while-armed rules; s8/s9 owned elsewhere. |
| AR-002 | Accepted | The confirmation token and handling of slash commands, empty input and /clear while armed were undefined and conflicted with the 'next input consumes it' rule. | Section 8 state-transition text now defines trimmed case-insensitive exact `yes`, cancel-on-anything-else, no forwarding to triage chat, and /clear cancel-then-run. |
| AR-003 | Accepted | Spec and plan conflicted on draft timing and naming; a single lifecycle rule removes the ambiguity. | Section 1 now defines draft as bug-report-N.md, written before preview, kept after publish, N next unused integer, never overwritten. |
| AR-004 | Accepted | Missing records, logs or zero attempts were undefined; one literal rule per field closes the gap. | Edited D2, D5, s10.1, s12.1 and AC-3 so any field without a source renders the literal `unavailable`. |
| AR-005 | Accepted | Absolute-path replacement could corrupt required relative .uncle/workflow references, and single-quoting breaks on apostrophes; title cap was unspecified. | Section 10 text now caps title at 80 chars, builds the copyable command with shlex.quote, and exempts relative paths from scrub. |
| AR-006 | Accepted | Timeout after auth or exit 0 without a URL leaves the issue possibly created; retrying could duplicate it, so the outcome must be defined. | Edit R-4, s10.1, s8.1 and AC-6, and add a test case to s12.1, for timeout/no-URL: keep draft, say the issue may exist, no retry. |
| AR-007 | Accepted | Plan did not define input handling while a report confirmation is pending; the chat input path is the main regression risk. | Section 8 now defines input interception while report_pending is set (yes publishes, else cancels, never reaches triage chat, /clear cancels then runs); change-impact row for uncle_tui updated. |
| AR-008 | Accepted | The plan gated only the banner hint; the /report handler itself needs an eligibility guard to match spec S2 refusal. | Step 3 text now requires the /report handler to call eligible() and print a fixed refusal line, arming nothing, saving no draft, calling no gh when ineligible. |
| AR-009 | Accepted | Draft naming and lifecycle were genuinely ambiguous; the rule is now fixed as next-integer, never overwritten, kept after publish. | Edited s1.1 and R-5 to specify bug-report-N.md numbering, one new file per /report, no overwrite, kept after publish. |
| AR-010 | Accepted | D2's last-record fallback contradicts the 'unavailable' rule for fields without a source. | D2 rewritten to drop the last-record fallback and render all stage fields unavailable; s20.1.i2 aligned. |
| AR-011 | Accepted | Title limits and quoting were unspecified; a scrub-then-truncate-then-quote rule is deterministic and testable. | Section 10 fallback command now shell-quotes the scrubbed title truncated to 100 chars; section 15 states the same bound. |
| AR-012 | Accepted | Pattern-based scrub can miss secrets in the free-text excerpt, so a post-scrub verification that blocks publish is needed. | Edited s1.1 and R-1 to add a post-scrub residual check that refuses publish (draft only) and a preview of the exact final text. |
| AR-013 | Accepted | Publishing must send exactly what the user previewed; rebuilding could differ from the preview, and the `yes` match rule and repeat `/report` behavior were unspecified. | Edited s1.1, s7.1 and s8.1: publish sends saved previewed bytes; `yes` is trimmed case-insensitive; repeat /report replaces pending state. |
| AR-014 | Accepted | Title scrub, cap and shell quoting were unspecified; the fallback command must be safe to paste and the cap testable. | Section 10 (s10.1) now sets title rule: scrubbed, newlines/quotes removed, capped at 80 chars, command uses shlex.quote. |
| AR-015 | Accepted | State-file values flow into body and draft filename, so they need allow-list validation. | Edit s1.1 and R-1 to validate field values against a regex, require integer N, and confine relative references to the state dir. |
| AR-016 | Accepted | Collision and symlink behavior of the draft file was genuinely unspecified; exclusive create with next-free suffix is cheap and safe. | R-5 mechanism/property and s1.1 now require exclusive no-follow create taking the next free bug-report-N.md, never overwriting. |
| AR-017 | Accepted | /report and confirmation behavior was unspecified for pending, ineligible and token-matching states; the proposed rules are deterministic and testable. | Section 8 now defines /report when ineligible, when pending, and the exact confirmation token matching. |
| AR-018 | Accepted | The redaction test had no oracle; naming the path mappings, token pattern list and replacement strings gives independent tests a fixed target. | R-1 mechanism, AC-4 requirement and tests, s10.1 and s12.1 now state the scrub oracle (path tokens, token list, [REDACTED]). |
| AR-019 | Accepted | Draft timing and naming conflicted between plan and spec; a single rule (lowest unused N, written before preview, kept after publish, one file per /report) resolves it. | Edited s1.1, s7.1, s11.1 and R-5 to use bug-report-N.md with lowest-unused N, written before preview, kept after publish, new file per /report. |
| AR-020 | Accepted | D2's last-record fallback contradicted the 'unavailable' rule and the failure/speculative/attempt semantics were ambiguous. | Rewrote D2 in s4.1 and updated s20.1.i2 to remove the last-record fallback. |
| AR-021 | Accepted | Publish outcomes need explicit timeouts and URL parsing so no-URL or timeout cases cannot be misreported as success. | Edit R-4 (30s timeout on auth check and create; URL = last stdout line starting https://; none = failure with draft fallback) and add publish-outcome test to s12.1. |
| AR-022 | Accepted | Limits were unspecified; fixed constants make bounded-length tests assertable and scrub-length changes irrelevant. | Section 15 now states title max 80 chars and excerpt 20 lines of max 300 chars, truncated after scrub. |
