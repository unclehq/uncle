## AR-001: Plan reads ineligible-state /report two ways: spec says refused with a message, plan only hides the banner.

- Severity: HIGH
- References: CHANGE_SPEC S2/AC-1 vs CHANGE_PLAN sections 8-9.
- Failure: Plan reads ineligible-state /report two ways: spec says refused with a message, plan only hides the banner. Plan never says what /report does outside recovery, with no classification, or while report_pending is armed. Settle: '/report outside an eligible recovery prints a refusal and arms nothing; /report while armed cancels the pending report.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Confirmation token is undefined: case, whitespace, 'y', empty input, and slash commands such as /clear while armed.

- Severity: HIGH
- References: CHANGE_PLAN sections 1 and 8; CHANGE_SPEC S4/S5.
- Failure: Confirmation token is undefined: case, whitespace, 'y', empty input, and slash commands such as /clear while armed. Section 8 says /clear clears pending, which collides with 'next input consumes it'. Settle: 'After trim+lowercase only exact yes publishes; every other input, including slash commands and empty, cancels and is not forwarded to triage chat.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Draft rules conflict.

- Severity: HIGH
- References: CHANGE_SPEC V4/S6 vs CHANGE_PLAN section 1 and 7.
- Failure: Draft rules conflict. Spec V4 says draft saved on non-publish outcomes; plan says always saved first. File naming is N in the spec and <turn> in the plan, both undefined. Settle: 'Draft is written before preview, kept after publish, N is next unused integer, never overwritten.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: No behavior is defined for missing or empty session-totals, missing failing-stage log, or zero attempts.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3; CHANGE_PLAN D2, D5, section 10.
- Failure: No behavior is defined for missing or empty session-totals, missing failing-stage log, or zero attempts. AC-3 lists exit status, excerpt, and artifact validation error, but D2/D5 give no source for the first or last. Settle: 'Any field without a source renders the literal unavailable.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Path-replacement scrub may corrupt the required relative .uncle/workflow references.

- Severity: MEDIUM
- References: CHANGE_SPEC section 10 and assumptions; CHANGE_PLAN section 10.
- Failure: Path-replacement scrub may corrupt the required relative .uncle/workflow references. Title cap is unspecified, and the copyable command wraps the title in single quotes, which an apostrophe breaks. Settle: 'Title capped at 80 chars; command uses shlex.quote; relative paths exempt from scrub.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: gh create edge outcomes are unspecified: exit 0 with no URL, and timeout after auth passed, where the issue may exist an

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6 and section 8; CHANGE_PLAN R-4, section 10.
- Failure: gh create edge outcomes are unspecified: exit 0 with no URL, and timeout after auth passed, where the issue may exist and a retry may duplicate. Settle: 'On timeout or no URL, keep draft, say the issue may already exist, and do not retry.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan does not say what happens to input while a report confirmation is pending, including slash commands.

- Severity: HIGH
- References: CHANGE_PLAN s8 'next chat input consumes it (yes -> publish; else cancel)'; the change-impact table rates the chat input path Medium regression risk.
- Failure: The plan does not say what happens to input while a report confirmation is pending, including slash commands. Settle it with: while report_pending is set, the next input is consumed by the report flow and never reaches triage chat; `yes` (trimmed, case-insensitive) publishes and anything else cancels. /clear cancels and then runs normally.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The refusal of /report for ineligible classes has no command-level guard in the plan.

- Severity: MEDIUM
- References: CHANGE_SPEC S2 says '/report refused with message'; CHANGE_PLAN step 3 gates only the banner hint on eligible().
- Failure: The refusal of /report for ineligible classes has no command-level guard in the plan. Step 3 gates only the banner hint. Settle it with: the /report handler calls eligible(self.triage_classification) and, if false, prints a fixed refusal line without setting report_pending, saving a draft, or calling gh.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Draft naming and lifecycle are unspecified: what <turn> means, what a repeated /report does, and whether a draft survive

- Severity: MEDIUM
- References: CHANGE_PLAN s1 'bug-report-<turn>.md' versus CHANGE_SPEC V4/S6 'bug-report-N.md'.
- Failure: Draft naming and lifecycle are unspecified: what <turn> means, what a repeated /report does, and whether a draft survives a successful publish. Settle it with: the draft is bug-report-N.md with N one higher than the highest existing bug-report-*.md, never overwritten, and kept after a successful publish.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The failed-stage fallback in D2 (last record) contradicts the rule that missing records render as `unavailable`.

- Severity: MEDIUM
- References: CHANGE_PLAN D2 'fall back to last record' versus s20 'falls back to unavailable' and CHANGE_SPEC S7.
- Failure: The failed-stage fallback in D2 (last record) contradicts the rule that missing records render as `unavailable`. Settle it with: if no record has a non-success status, the stage, attempt, role, exit status, runner, model and effort all render `unavailable`, and the last record is never used.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The title limits and quoting are unspecified.

- Severity: LOW
- References: CHANGE_SPEC s15 'redacted and capped'; CHANGE_PLAN s10 command uses --title '...' with no quoting or length rule.
- Failure: The title limits and quoting are unspecified. Settle it with: the title is scrubbed first, then truncated to 100 characters, and the copyable command shell-quotes the scrubbed title.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan never says what happens if scrub leaves a likely secret or absolute path in title or body.

- Severity: HIGH
- References: CHANGE_PLAN s1/R-1/Risks: redaction relies on patterns; the excerpt is free text; no post-scrub check is specified.
- Failure: Plan never says what happens if scrub leaves a likely secret or absolute path in title or body. Decision: if any path or token pattern still matches after scrub, publish is refused and only the draft is saved; preview shows the exact final text.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan does not say whether publish sends the previewed draft or rebuilds the report.

- Severity: MEDIUM
- References: CHANGE_PLAN s1/s7/s8: draft written before prompt; publish(report, runner); no match rule for `yes`.
- Failure: Plan does not say whether publish sends the previewed draft or rebuilds the report. Decision: publish sends the exact saved, previewed bytes; `yes` matches trimmed and case-insensitive; a repeat `/report` replaces the pending state.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Fallback command embeds a title in shell quoting, and the title cap and scrub are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s10: `--title '...'`; CHANGE_SPEC Assumptions: title redacted and capped, with no value given.
- Failure: Fallback command embeds a title in shell quoting, and the title cap and scrub are unspecified. Decision: title is scrubbed, newlines and quotes removed, capped at 80 chars; the copyable command uses shlex.quote.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Values from state files (stage, runner, model) go into the body and the draft filename without validation.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 build_report(stage=None) and bug-report-<turn>.md; R-1 allow-lists field names only.
- Failure: Values from state files (stage, runner, model) go into the body and the draft filename without validation. Decision: values must match [A-Za-z0-9._:/-]{1,64} or become `unavailable`; <turn> must be an integer; relative references must stay inside the state dir with no `..`.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Draft filename collision and symlink behavior are unspecified.

- Severity: LOW
- References: CHANGE_PLAN R-5/s1: bug-report-N.md with no collision handling.
- Failure: Draft filename collision and symlink behavior are unspecified. Decision: exclusive create without following symlinks, taking the next free suffix rather than overwriting.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: /report and the pending confirmation are unspecified in several states: already pending, ineligible, no records, and 'ye

- Severity: HIGH
- References: CHANGE_PLAN s1/s8: 'next input yes publishes, anything else cancels'. CHANGE_SPEC S2: refusal message has no text.
- Failure: /report and the pending confirmation are unspecified in several states: already pending, ineligible, no records, and 'yes' with different case or whitespace. Say: 'Confirmation accepts only trimmed case-insensitive `yes`; /report while pending re-renders and replaces it; /report when ineligible prints a refusal and arms nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The AC-4 redaction test has no oracle: no token pattern list, no replacement string, no path rule.

- Severity: HIGH
- References: CHANGE_SPEC AC-4 and s10; CHANGE_PLAN R-1 says 'chat.sanitize extension' with no list. Tests are written independently (s12).
- Failure: The AC-4 redaction test has no oracle: no token pattern list, no replacement string, no path rule. Say: 'scrub maps project root, uncle root and home to <project>, <uncle> and ~, and replaces a named token-pattern list (ghp_, github_pat_, sk-, Bearer, AKIA, URL userinfo, cookie headers) with [REDACTED]; tests use that list.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Draft timing and naming conflict.

- Severity: MEDIUM
- References: CHANGE_PLAN s1/s7 ('bug-report-<turn>.md') against CHANGE_SPEC V4/S6 ('bug-report-N.md').
- Failure: Draft timing and naming conflict. The plan saves the draft before confirmation, but the spec says it is saved on every non-publish outcome. Numbering key (<turn> or N), draft survival after publish, and a second /report are unspecified. Say: 'Draft is written before the preview as the lowest unused bug-report-N.md, kept after publish; each /report makes a new file.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The D2 failed-stage rule is ambiguous: several failures, all-success stages, and speculative records in the attempt coun

- Severity: MEDIUM
- References: CHANGE_PLAN D2 against s20 and s10.
- Failure: The D2 failed-stage rule is ambiguous: several failures, all-success stages, and speculative records in the attempt count. Its last-record fallback conflicts with the 'unavailable' fallback. Say: 'Failing stage is the most recent non-speculative non-success record; if none, all stage fields are unavailable with no last-record fallback; attempt counts non-speculative records for that stage.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Publish outcomes are underspecified: whether the auth check and the create call each get a timeout, and what happens whe

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6 and s8; CHANGE_PLAN R-4 and s10.
- Failure: Publish outcomes are underspecified: whether the auth check and the create call each get a timeout, and what happens when create exits 0 with no URL or extra output. Say: 'Auth check and create each time out at 30s; the URL is the last stdout line starting with https://; if none is found, treat it as failure and show the draft fallback.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The title and excerpt limits are unspecified, and a scrub replacement can change lengths.

- Severity: LOW
- References: CHANGE_SPEC s15 ('redacted and capped') against CHANGE_PLAN D5.
- Failure: The title and excerpt limits are unspecified, and a scrub replacement can change lengths. The bounded-length test has no constant to assert. Say: 'Title is at most 80 chars, truncated after scrub; excerpt is 20 lines of at most 300 chars each, truncated after scrub.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
