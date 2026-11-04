# Change Spec — Issue 117

Omitted sections: Migration (none); Prototype isolation (n/a); Performance (negligible)

## 1. Change type
Feature + Security (privacy-sensitive).

## 2. Problem
Triage drafts are local only; users must hand-redact and file them.

## 3. Current behavior
See baseline B3, B6.

## 4. Desired behavior
When triage classifies a failure `tool bug` (non-recoverable tool/driver failure), the recovery UI offers `/report`. It builds a redacted preview with required metadata, asks explicit confirmation, then runs `gh issue create --repo unclehq/uncle`. Cancel, missing/unauthenticated `gh`, or failure preserves a sanitized local draft and shows a copyable command.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S1 | ADD | Recovery with classification `tool bug` | No report offer | Recovery shows `Report Uncle bug (/report)` hint | bug-report test: offer predicate |
| S2 | PRESERVE | Classification code defect / requirement gap / needs owner decision, or routine test failure, or no classification | Normal recovery | No report offer; /report refused with message | test: predicate false for each |
| S3 | ADD | /report | n/a | Preview shows metadata, resolved runner/model/effort of failed stage, excerpt; nothing published | test: preview content |
| S4 | ADD | User confirms (explicit `yes`) with authenticated gh | n/a | One `gh issue create --repo unclehq/uncle --title T --body-file F` call; URL shown | test with fake gh on PATH |
| S5 | ADD | User cancels / any non-yes | n/a | No gh issue create invoked; draft retained | test: fake gh records no create |
| S6 | ADD | gh missing or `gh auth status` fails | n/a | Sanitized draft saved at `.uncle/workflow/bug-report-N.md`; actionable message and copyable `gh issue create ...` command | test: unauth fallback |
| S7 | ADD | Report generated | n/a | Per-stage runner/model/effort from the failed stage's attempt record, never global default; `unavailable` if no record | test: two stages with different runners |
| S8 | PRESERVE | Any outcome | Local triage-issue draft exists | `triage-issue-N.md` untouched | test: hash before/after |
| S9 | ADD | Report built from tree containing secrets/abs paths/prompts | n/a | Output has none of: keys, tokens, cookies, absolute project/home paths, raw prompts, source files, `.uncle/config` content | redaction test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V1 | NEW | No issue is published without explicit confirmation in the same flow | bug_report.publish | confirm param required True | test S4/S5 |
| V2 | NEW | Report body is built from an allow-list of fields then redacted; never includes absolute paths or secrets | bug_report.build | build + scrub | test S9 |
| V3 | NEW | Runner/model/effort come from stage attempt record, not defaults | bug_report.build | record lookup | test S7 |
| V4 | NEW | Local sanitized draft is saved on every non-publish outcome and existing triage drafts are never modified | bug_report | save_draft | tests S5,S6,S8 |
| V5 | EXISTING | Triage guard/sandbox and human-stop non-triage rules unchanged | TUI | unchanged | existing suites |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No change to driver stages, state files, or record schema. Additive only.

## 8. Failure behavior
gh absent, unauthenticated, timeout, or nonzero create: draft saved, message with exact next step and copyable command; no crash; no retry loop.

## 10. Security
Allow-list + redaction (chat.sanitize plus home/project path replacement, token patterns, URL credentials). gh invoked with argv list (no shell), GH_PROMPT_DISABLED=1, stdin devnull. Local diagnostics referenced by relative id only (`.uncle/workflow/...` relative), no absolute paths.

## 12. Rollback
Revert additive commit; no persisted schema changes. Leftover `bug-report-N.md` drafts are inert.

## 14. Non-goals
Auto-publishing; diagnostic bundle upload (opt-in bundle deferred); changing triage classification logic; reporting routine test failures.

## 15. Assumptions
- Eligibility is defined as triage classification `tool bug` (existing signal). Decision recorded in plan.
- Issue title: `[bug] <stage>: <short failure>` redacted and capped.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Report offer appears only when the recovery classification is `tool bug`; not for code defect, requirement gap, owner decision, routine test failure, or unclassified recovery. | Unit test of eligibility predicate over all classes and none; TUI test that the hint/command is refused otherwise. |
| AC-2 | Preview shows resolved runner, model, and effort of the failed stage taken from its attempt record, not the global default. | Test with session-totals records for two stages using different runners/models/effort and a differing global config; assert preview matches the failed stage. |
| AC-3 | Generated issue contains Uncle version, source revision, install type, OS/runtime, workflow type, state, failing stage, attempt, role, exit status, runner/model/effort, concise error excerpt, artifact validation error if present, and a relative reference to retained diagnostics. | Test asserts each field label present in built body from a fixture state dir. |
| AC-4 | Body and preview contain no API keys, tokens, cookies, credentials, `.uncle/config` content, absolute project/home paths, raw prompts, source files, or full logs. | Redaction test with planted secrets, absolute paths, and prompt text in logs; assert absence and bounded excerpt length. |
| AC-5 | Cancelling at confirmation invokes no `gh issue create` and leaves a sanitized local draft. | Fake gh on PATH logs invocations; assert no create call and draft file present. |
| AC-6 | Explicit confirmation with authenticated gh runs `gh issue create --repo unclehq/uncle` once and reports the issue URL. | Fake gh returning a URL; assert argv and displayed URL. |
| AC-7 | Missing gh or failed auth saves a sanitized local draft and shows an actionable next step with a copyable submission command. | Tests with gh absent from PATH and with fake gh failing `auth status`. |
| AC-8 | Existing `triage-issue-N.md` drafts are never modified or removed regardless of outcome, and existing triage and TUI suites still pass. | Hash comparison in test; bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh show no new failures vs baseline. |

