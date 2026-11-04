## AR-001: Resuming a run recorded as attended, with no flag and no TTY, is unspecified.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 precedence (recorded mode) vs TTY rule; CHANGE_SPEC AC-3, AC-8, I-2.
- Failure: Resuming a run recorded as attended, with no flag and no TTY, is unspecified. Settle with: 'A resume whose recorded mode is attended, with no TTY and no UNCLE_ATTENDED_STDIN=1, refuses with exit 1 and never runs unattended.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Env and flag conflict rules collide.

- Severity: HIGH
- References: CHANGE_SPEC s4 Environment row; CHANGE_PLAN s1.1 precedence; AC-4, AC-5, AC-8.
- Failure: Env and flag conflict rules collide. Two CLI flags are refused, but UNCLE_ATTENDED=1 with --unattended resolves to attended, and a legacy env against a recorded attended mode is undefined. Settle with: 'Any explicit attended source wins over any unattended source, except --attended with --unattended on the CLI, which refuses; explicit flag or env overrides the recorded mode.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: An absent, empty or corrupt mode file is not specified.

- Severity: MEDIUM
- References: CHANGE_PLAN s8 Compatibility, s7 Persistence; CHANGE_SPEC I-2, I-5.
- Failure: An absent, empty or corrupt mode file is not specified. The plan resumes mode-file-less runs as unattended, which silently flips a previously attended run, against I-2. Settle with: 'An unparseable mode file refuses with exit 1; a missing one on a run with existing state resumes unattended and prints a notice saying so.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The UNCLE_MODE_RESOLVED guard leaves open a child driver that inherits UNCLE_MODE_RESOLVED=1 and also gets an explicit -

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1, risk row 3, R-2; AC-6.
- Failure: The UNCLE_MODE_RESOLVED guard leaves open a child driver that inherits UNCLE_MODE_RESOLVED=1 and also gets an explicit --attended or --unattended. Settle with: 'When UNCLE_MODE_RESOLVED=1 is inherited, the inherited UNCLE_UNATTENDED is authoritative; a contradicting --attended refuses, and --unattended is ignored silently.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The effect of UNCLE_ATTENDED_STDIN=1 alone, or when the resolved mode is unattended, is not described.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 TTY rule, D-5; CHANGE_SPEC AC-3.
- Failure: The effect of UNCLE_ATTENDED_STDIN=1 alone, or when the resolved mode is unattended, is not described. Settle with: 'UNCLE_ATTENDED_STDIN=1 never changes the selected mode; it only waives the TTY check when the resolved mode is attended.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Only the unattended banner is exact (AC-1).

- Severity: LOW
- References: CHANGE_PLAN s14 Observability; CHANGE_SPEC AC-1, AC-4, AC-8.
- Failure: Only the unattended banner is exact (AC-1). The attended, resume, TUI and deprecation notice strings are given as 'Mode: <mode> ...', so tests, docs and the checklist will each invent different text. Settle by listing the exact string for each.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Resume precedence is unspecified for existing runs without a mode file that were started attended (the old direct-driver

- Severity: HIGH
- References: CHANGE_PLAN s8 Compatibility: 'Existing runs without a mode file resume as default (unattended) unless flagged'; conflicts with I-2 intent and AC-8.
- Failure: Resume precedence is unspecified for existing runs without a mode file that were started attended (the old direct-driver default). The plan says they resume unattended, silently dropping human gates. Plan should say: a run with state but no mode file resumes attended (or refuses without an explicit flag), never silently unattended.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Recorded-mode reuse versus the TTY rule is unspecified.

- Severity: HIGH
- References: CHANGE_PLAN s1 precedence puts the recorded mode before the default; the TTY rule is stated only for 'attended', and AC-3/I-2 do not cover resume.
- Failure: Recorded-mode reuse versus the TTY rule is unspecified. A run recorded attended but resumed with no TTY and no UNCLE_ATTENDED_STDIN is not stated to refuse. Plan should say: a resumed attended run without a TTY refuses with exit 1 and never falls back to unattended.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The UNCLE_MODE_RESOLVED=1 guard can inherit a stale UNCLE_UNATTENDED across entry points.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 and risk row 3; AC-6 parity covers only identical flags/env.
- Failure: The UNCLE_MODE_RESOLVED=1 guard can inherit a stale UNCLE_UNATTENDED across entry points. The plan never says whether --attended or UNCLE_ATTENDED=1 in a child still overrides the inherited value. Plan should say: inherited UNCLE_UNATTENDED is authoritative, and child flags that conflict with it are refused.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The plan does not say what happens for UNCLE_ATTENDED=0 or empty, or for --unattended combined with UNCLE_ATTENDED=1.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4/AC-5 and CHANGE_PLAN s1 precedence list; no empty, 0 or invalid env value is described.
- Failure: The plan does not say what happens for UNCLE_ATTENDED=0 or empty, or for --unattended combined with UNCLE_ATTENDED=1. Plan should say: only the value 1 counts; other values are ignored; --unattended with UNCLE_ATTENDED=1 resolves attended and prints the deprecation notice.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Mode file write timing is ambiguous.

- Severity: MEDIUM
- References: CHANGE_PLAN s9 Persistence vs s12 Error and recovery; housekeeping and from-issue rows do not name a state dir.
- Failure: Mode file write timing is ambiguous. Section 12 says refusals happen before any state is created, but section 9 says drivers write the file at start. A refused resume could overwrite the recorded mode. Plan should say: the mode file is written only after successful resolution, never on refusal, and only by the driver that owns the run directory.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The unattended-enabled ledger text changes to 'enabled by default (or --unattended)', but AC-7/A-8 require byte-identica

- Severity: LOW
- References: CHANGE_PLAN s8 Interface changes vs CHANGE_SPEC AC-7 and A-8 'byte-identical wording and fields'.
- Failure: The unattended-enabled ledger text changes to 'enabled by default (or --unattended)', but AC-7/A-8 require byte-identical ledger entries. These two statements cannot both hold. Plan should say which wording is authoritative, and that the record test compares against the new text only.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The plan never says whether an explicit --attended overrides an inherited UNCLE_MODE_RESOLVED=1 plus UNCLE_UNATTENDED=1.

- Severity: HIGH
- References: CHANGE_PLAN s1: an inherited UNCLE_MODE_RESOLVED=1 stops UNCLE_UNATTENDED being read as legacy input. I-2 says attended never degrades.
- Failure: The plan never says whether an explicit --attended overrides an inherited UNCLE_MODE_RESOLVED=1 plus UNCLE_UNATTENDED=1. Add: an explicit --attended or UNCLE_ATTENDED=1 always re-resolves, including the TTY check, and wins over inherited derived state.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: With UNCLE_ATTENDED_STDIN=1 the TTY check is skipped, but nothing says what a gate does on EOF or an invalid answer.

- Severity: HIGH
- References: CHANGE_SPEC s4 'No TTY' row and CHANGE_PLAN R-5 define UNCLE_ATTENDED_STDIN with no EOF behavior.
- Failure: With UNCLE_ATTENDED_STDIN=1 the TTY check is skipped, but nothing says what a gate does on EOF or an invalid answer. Add: in attended mode, EOF or an unreadable answer at a gate counts as a decline and stops the run. It is never delegated.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Resume behavior is undefined for a mode file with invalid content, and for a recorded attended mode resumed without a TT

- Severity: MEDIUM
- References: CHANGE_PLAN s7/s8 and I-5 define the file as authoritative on resume with no validation.
- Failure: Resume behavior is undefined for a mode file with invalid content, and for a recorded attended mode resumed without a TTY. Add: an invalid mode file is an error and is never read as unattended. A recorded attended mode still requires a TTY (or UNCLE_ATTENDED_STDIN=1) on resume.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The legacy UNCLE_UNATTENDED=0, WORKFLOW_UNATTENDED=0 and UNCLE_HOUSEKEEPING_UNATTENDED=0 values were the old way to forc

- Severity: MEDIUM
- References: CHANGE_PLAN s1 lists only '=1' legacy values; risk row 3 mentions only the inherited UNCLE_UNATTENDED=0 guard.
- Failure: The legacy UNCLE_UNATTENDED=0, WORKFLOW_UNATTENDED=0 and UNCLE_HOUSEKEEPING_UNATTENDED=0 values were the old way to force attended. After the default flip they could silently mean unattended. Add: those legacy envs set to 0 resolve to attended with a notice, and only the exact value 1 selects unattended.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan does not say whether a stale or tampered .uncle/workflow/mode file can escalate a run to unattended on resume.

- Severity: MEDIUM
- References: CHANGE_PLAN s7 and I-5 give the file authority on resume with no integrity requirement.
- Failure: The plan does not say whether a stale or tampered .uncle/workflow/mode file can escalate a run to unattended on resume. Add: the file is read only when valid run state exists in the same directory, and a non-regular file or a symlink is rejected.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Resume precedence is ambiguous: does an explicit flag or env override the recorded mode, and does the TTY rule apply to

- Severity: HIGH
- References: CHANGE_PLAN s1.1 precedence list; CHANGE_SPEC AC-8, I-5.
- Failure: Resume precedence is ambiguous: does an explicit flag or env override the recorded mode, and does the TTY rule apply to a recorded attended run? Settle with: 'On resume an explicit flag/env overrides the recorded mode; recorded attended with no TTY and no UNCLE_ATTENDED_STDIN refuses with exit 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Mode file write timing and bad content are unspecified, and 'written at start' conflicts with 'no state before refusal'.

- Severity: HIGH
- References: CHANGE_PLAN s7.1 vs s9.1 ('before any state is created').
- Failure: Mode file write timing and bad content are unspecified, and 'written at start' conflicts with 'no state before refusal'. Settle with: 'Written atomically only after resolution succeeds; content other than attended/unattended is ignored with a stderr notice and the default applies.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Interaction of an inherited UNCLE_MODE_RESOLVED=1 with an explicit CLI flag or UNCLE_ATTENDED is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1; risk row 3.
- Failure: Interaction of an inherited UNCLE_MODE_RESOLVED=1 with an explicit CLI flag or UNCLE_ATTENDED is unspecified. Settle with: 'When UNCLE_MODE_RESOLVED=1, the inherited UNCLE_UNATTENDED is authoritative; contradicting flags are refused; the launcher clears any user-set UNCLE_MODE_RESOLVED.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Exact stderr text for the deprecation notice, refusal messages, and attended/resume banners is unspecified; only the una

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1, AC-4; CHANGE_PLAN s14.1 'Mode: <mode> ...'.
- Failure: Exact stderr text for the deprecation notice, refusal messages, and attended/resume banners is unspecified; only the unattended banner is fixed. Tests and checklist will assert different strings. Settle by fixing each string verbatim in the plan.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Which stream counts for the TTY check is unspecified, notably when `--application`/`--housekeeping` read text from stdin

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 TTY rule; commit 4948181 (read text from standard input).
- Failure: Which stream counts for the TTY check is unspecified, notably when `--application`/`--housekeeping` read text from stdin, which makes stdin a non-TTY. Settle with: 'Attended requires isatty(0) only; stdin-supplied text therefore requires UNCLE_ATTENDED_STDIN=1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: Legacy env set to a value other than 1 (e.g.

- Severity: LOW
- References: CHANGE_PLAN s1.1 lists only =1; risk row 3 mentions UNCLE_UNATTENDED=0.
- Failure: Legacy env set to a value other than 1 (e.g. UNCLE_UNATTENDED=0) is unspecified. Settle with: 'Legacy env not equal to 1 is ignored silently and does not select attended.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
