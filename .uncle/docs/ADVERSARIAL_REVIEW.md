## AR-001: The plan skips the prompt when SEED_ONLY=1, but the spec never mentions SEED_ONLY in S3/S5/S6/AC-5.

- Severity: HIGH
- References: CHANGE_PLAN s1 guard (SEED_ONLY != 1) vs CHANGE_SPEC S5/S6 and V3.
- Failure: The plan skips the prompt when SEED_ONLY=1, but the spec never mentions SEED_ONLY in S3/S5/S6/AC-5. Add: 'With SEED_ONLY=1 and an existing request file, no prompt is shown and existing no-overwrite behavior (V3) is unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Unattended detection differs between spec and plan.

- Severity: HIGH
- References: CHANGE_SPEC AC-4/S4 vs CHANGE_PLAN s1 and R-1.
- Failure: Unattended detection differs between spec and plan. The spec says UNCLE_UNATTENDED=1; the plan also accepts UNATTENDED==1. Add: 'Unattended means UNATTENDED=1 or UNCLE_UNATTENDED=1 exactly; other values are interactive; UNCLE_REPLACE_CHANGE_REQUEST counts only when equal to 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The plan does not say whether a zero-byte request file counts as existing.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 'non-empty existing file' vs CHANGE_SPEC AC-3/V1.
- Failure: The plan does not say whether a zero-byte request file counts as existing. The plan guard requires non-empty, but AC-3/V1 say 'existing'. Add: 'A zero-byte request file is treated as absent: no prompt, overwritten silently.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: V2 claims .uncle/workflow is byte-identical after a decline, but the plan accepts that the worktree may already be creat

- Severity: MEDIUM
- References: CHANGE_SPEC V2 vs CHANGE_PLAN s22 risk 2.
- Failure: V2 claims .uncle/workflow is byte-identical after a decline, but the plan accepts that the worktree may already be created before the decline. Add: 'V2 covers CHANGE_REQUEST.md and .uncle/workflow in the current worktree; a worktree created earlier in the same invocation is out of scope.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The plan leaves two cases open: the existing file is identical to the new request, or the issue number differs from the

- Severity: MEDIUM
- References: CHANGE_PLAN s1 guard; CHANGE_SPEC S5 defines only same-issue in-flight resume.
- Failure: The plan leaves two cases open: the existing file is identical to the new request, or the issue number differs from the seeded one. Add: 'The prompt is shown whenever the file exists and seed_is_current is false, even if content is identical.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The plan does not say which stream the prompt goes to or how answers are normalized (CRLF, trailing space).

- Severity: LOW
- References: CHANGE_PLAN s1 'print the file path and prompt', 'trim, lowercase'; CHANGE_SPEC S1.
- Failure: The plan does not say which stream the prompt goes to or how answers are normalized (CRLF, trailing space). Add: 'The prompt goes to stderr; input is trimmed of whitespace and CR, lowercased, and matched exactly against y|yes.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Non-TTY callers without the unattended flag (TUI, driver, closed stdin) hit EOF, which counts as no, so runs that used t

- Severity: HIGH
- References: CHANGE_PLAN s22 risk 1 accepts that callers with no stdin 'now stop'; spec S2 makes EOF a decline.
- Failure: Non-TTY callers without the unattended flag (TUI, driver, closed stdin) hit EOF, which counts as no, so runs that used to overwrite now exit 1. Settle with: 'When stdin is not a TTY and neither UNATTENDED nor UNCLE_REPLACE_CHANGE_REQUEST=1 is set, treat the run as unattended: print the opt-in message and exit 1 without reading.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The plan never says whether UNCLE_REPLACE_CHANGE_REQUEST=1 skips the prompt in interactive mode, or which seeding paths

- Severity: MEDIUM
- References: CHANGE_PLAN s1 mentions the opt-in only inside the unattended branch; spec V3 keeps stdin imports as existing no-clobber.
- Failure: The plan never says whether UNCLE_REPLACE_CHANGE_REQUEST=1 skips the prompt in interactive mode, or which seeding paths the guard covers. Settle with: 'UNCLE_REPLACE_CHANGE_REQUEST=1 also skips the prompt interactively; the guard does not run on stdin-import or seed-only paths.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The guard reads the answer from stdin, which may carry piped request content for change_request_stdin.py, so the prompt

- Severity: MEDIUM
- References: CHANGE_PLAN s5 keeps change_request_stdin.py unmodified; s1 uses `read -r` from stdin in the change) case.
- Failure: The guard reads the answer from stdin, which may carry piped request content for change_request_stdin.py, so the prompt could consume the request body or take it as an answer. Settle with: 'When stdin is piped request content (non-TTY), the guard never reads it and follows the unattended rule.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The meaning of an empty or whitespace-only existing file is left open: s1 says non-empty, while the spec's AC-3 says onl

- Severity: LOW
- References: CHANGE_PLAN s1 'non-empty existing file' versus CHANGE_SPEC AC-3.
- Failure: The meaning of an empty or whitespace-only existing file is left open: s1 says non-empty, while the spec's AC-3 says only 'no existing file'. Settle with: 'A zero-byte or whitespace-only CHANGE_REQUEST.md counts as no file and is replaced without a prompt.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Unattended is read from either UNATTENDED or UNCLE_UNATTENDED, but the spec names only UNCLE_UNATTENDED.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 says `UNATTENDED==1` (or `UNCLE_UNATTENDED==1`). CHANGE_SPEC AC-4 mentions only UNCLE_UNATTENDED=1.
- Failure: Unattended is read from either UNATTENDED or UNCLE_UNATTENDED, but the spec names only UNCLE_UNATTENDED. Fix: 'Unattended is true if the flag or UNCLE_UNATTENDED=1 sets UNATTENDED=1; the confirm function checks only UNATTENDED.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The plan does not say how the opt-in value is validated.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 'proceed only if UNCLE_REPLACE_CHANGE_REQUEST==1'. AC-4 and V1 give no other-value behavior.
- Failure: The plan does not say how the opt-in value is validated. Unset, 0, empty and 'true' are unspecified, and an ambient exported value could silently allow overwrites. Fix: 'Only the exact string 1 in UNCLE_REPLACE_CHANGE_REQUEST permits replacement; every other value refuses.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: 'Non-empty existing file' leaves a zero-byte file, a symlink, a dangling symlink or a directory unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1: 'non-empty existing file'. CHANGE_SPEC V1 says an existing file is never replaced without consent.
- Failure: 'Non-empty existing file' leaves a zero-byte file, a symlink, a dangling symlink or a directory unspecified. The plan also does not cover a change between the guard and the write, so V1 and V2 can be broken. Fix: 'Any existing path entry at CHANGE_REQUEST.md triggers confirmation, and the write does not follow symlinks.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The plan does not say where the prompt text goes, or whether the printed path is sanitized.

- Severity: LOW
- References: CHANGE_PLAN s1.1 'print the file path and ... read -r'. s19 mentions stderr only for decision messages.
- Failure: The plan does not say where the prompt text goes, or whether the printed path is sanitized. Fix: 'Prompt and messages go to stderr, the path is printed with control characters escaped, and the answer is read from stdin only.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Isolated function tests can't verify gating or decline-before-archive (V2); end-to-end case is optional and cut first.

- Severity: HIGH
- References: CHANGE_PLAN s16 'if from-issue.sh's test hook allows'; s21 cuts end-to-end case first; AC-5/V2 need state checks.
- Failure: Isolated function tests can't verify gating or decline-before-archive (V2); end-to-end case is optional and cut first. Say: 'The new test MUST invoke from-issue.sh end to end, covering no prompt for NEW_WORKFLOW, SEED_ONLY, seed_is_current, and empty file, and asserting unchanged file hash and .uncle/workflow after decline; never cut.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Unattended mechanism ambiguous: plan accepts UNATTENDED or UNCLE_UNATTENDED, AC-4 names only the env var, manual check u

- Severity: MEDIUM
- References: CHANGE_PLAN s1; AC-4; s18 manual '--unattended run'.
- Failure: Unattended mechanism ambiguous: plan accepts UNATTENDED or UNCLE_UNATTENDED, AC-4 names only the env var, manual check uses --unattended. Say: 'Tests cover both the --unattended flag and UNCLE_UNATTENDED=1, each with and without UNCLE_REPLACE_CHANGE_REQUEST=1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: 'Non-empty existing file' leaves zero-byte, whitespace-only, directory files and non-1 opt-in values (true, 0, empty) un

- Severity: MEDIUM
- References: CHANGE_PLAN s1; AC-3 says only 'No existing file'.
- Failure: 'Non-empty existing file' leaves zero-byte, whitespace-only, directory files and non-1 opt-in values (true, 0, empty) unspecified. Say: 'Zero-byte counts as absent; whitespace-only counts as existing; opt-in proceeds only when exactly 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Prompt stream and wording not pinned, so tests can't assert 'prompt shown' or 'no prompt'.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 vs s19; AC-1 'message names the file'.
- Failure: Prompt stream and wording not pinned, so tests can't assert 'prompt shown' or 'no prompt'. Say: 'Prompt and stop messages go to stderr; prompt contains the file path and "Proceed with the new change request and replace it? [y/N]"; the unattended message contains UNCLE_REPLACE_CHANGE_REQUEST=1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Answer parsing undefined for CRLF, 'y please', and a final 'y' with no newline (read -r returns nonzero but fills variab

- Severity: LOW
- References: CHANGE_PLAN s1 'read -r (EOF => empty); trim, lowercase'; AC-2 EOF.
- Failure: Answer parsing undefined for CRLF, 'y please', and a final 'y' with no newline (read -r returns nonzero but fills variable). Say: 'Only trimmed, lowercased y or yes proceed, with CR stripped and an unterminated final line accepted; all else declines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
