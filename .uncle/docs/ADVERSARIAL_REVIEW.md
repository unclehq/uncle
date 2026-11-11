## AR-001: A readable READY verdict with unreadable or malformed acceptance evidence has no defined outcome.

- Severity: HIGH
- References: CHANGE_PLAN.json §1 limits its explicit fallback to failures preventing verdict determination; §12 broadly promises Refs on parsing failure. CHANGE_SPEC.json §8 repeats the verdict-dependent condition. Implementations could silently treat unavailable acceptance rows as no blockers and close unfinished work.
- Failure: A readable READY verdict with unreadable or malformed acceptance evidence has no defined outcome. Add: "Missing, unreadable, or malformed acceptance evidence yields Refs even when the verdict is READY, with an evidence-unavailable reason in Still open."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: An explicit still-open audit finding has no clear precedence when acceptance rows pass.

- Severity: HIGH
- References: CHANGE_PLAN.json §1 includes audit findings saying "not closed" or "stays open", but its scope cuts permit removing that extraction. CHANGE_SPEC.json AC-2 requires those findings in the list, while SI-1 omits them from closure conditions. The same audit could therefore yield either Closes or Refs.
- Failure: An explicit still-open audit finding has no clear precedence when acceptance rows pass. Add: "Any FINAL_AUDIT finding stating that the origin issue remains open forces Refs and appears in Still open, regardless of an otherwise eligible verdict; this behavior cannot be cut."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Optional BLOCKED delivery rows can either prevent closure or be ignored under the current wording.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 collects every BLOCKED row from Acceptance delivery but filters Acceptance gate rows to Required=YES. CHANGE_SPEC.json SI-1 and SB-2 specify required BLOCKED rows. This difference changes whether optional unfinished work prevents automatic closure.
- Failure: Optional BLOCKED delivery rows can either prevent closure or be ignored under the current wording. Add: "Only required BLOCKED acceptance rows prevent closure; determine requiredness from the Required cell, treating an absent or unrecognized value as required in either table."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Refs caused solely by an override, release skip, or ineligible verdict has no defined Still open content.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §4 and SB-1 require a Still open list for unfinished work; CHANGE_PLAN.json §8 makes that section optional. Neither defines entries when there are no BLOCKED rows or extracted finding IDs. Code and tests could disagree on whether a bare Refs trailer satisfies the requirement.
- Failure: Refs caused solely by an override, release skip, or ineligible verdict has no defined Still open content. Add: "Every Refs trailer includes Still open with available blocker IDs and a single-line reason for each applicable override, release skip, ineligible verdict, or unavailable verdict, even when no IDs exist."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: A readable READY verdict with missing or malformed acceptance evidence has no defined outcome, allowing parsers to mista

- Severity: HIGH
- References: CHANGE_PLAN.json §1 limits its explicit failure fallback to failures preventing verdict determination, while §12 broadly says parsing failures return Refs; CHANGE_SPEC.json SI-1 requires no required BLOCKED row. Resolve this difference and test READY with missing files and malformed tables so parsing changes cannot silently enable issue closure.
- Failure: A readable READY verdict with missing or malformed acceptance evidence has no defined outcome, allowing parsers to mistake unknown status for no blockers. Add: “Missing, unreadable, or malformed acceptance evidence yields Refs even when the verdict is READY.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Backward trailer scanning does not define what happens when trailing bullets or a Still open heading lack a valid refere

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8, decision D-2, walks backward over blank lines, bullets and the Still open header before finding a reference line; CHANGE_SPEC.json AC-4 requires preservation. Specify atomic recognition and add regression cases for ordinary trailing lists, an unmatched Still open heading, and prose beginning “Refs ”.
- Failure: Backward trailer scanning does not define what happens when trailing bullets or a Still open heading lack a valid reference trailer, risking changes to ordinary body content. Add: “Move trailing content only after recognizing a complete Closes/Refs origin trailer; otherwise preserve it verbatim before the attestation.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Newline stripping allows repository-derived Still open text to introduce closing keywords, defeating the Refs decision.

- Severity: HIGH
- References: CHANGE_SPEC.json §10 requires only single-line sanitization; CHANGE_PLAN.json §1 takes acceptance rows and FINAL_AUDIT findings into the Still open list. A source entry containing `Fixes owner/repo#123` remains single-line and can introduce an unintended issue-closing instruction into the PR body; constrain emitted entries and add an adversarial fixture.
- Failure: Newline stripping allows repository-derived Still open text to introduce closing keywords, defeating the Refs decision. Add: "Render Still open entries using validated acceptance/finding IDs and fixed reason labels only; never copy repository-derived prose or arbitrary ID text into the trailer."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The READY verdict plus unreadable acceptance evidence case has no unambiguous test oracle.

- Severity: HIGH
- References: CHANGE_PLAN.json §1 limits fallback to failures preventing verdict determination, while §12 says parsing exceptions return Refs; CHANGE_SPEC.json §8 repeats the verdict qualification. A parser that silently ignores malformed tables could therefore pass the listed tests and emit Closes without establishing that required acceptance is complete.
- Failure: The READY verdict plus unreadable acceptance evidence case has no unambiguous test oracle. Add: "If either acceptance document is missing, unreadable, or malformed, emit Refs even when the verdict is READY; test each failure independently."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Audit-only open findings lack a defined closure oracle, and their extraction is both required and removable.

- Severity: HIGH
- References: CHANGE_PLAN.json §1 includes audit open-finding inputs, but 'Scope cuts under time pressure' permits removing their extraction; CHANGE_SPEC.json AC-2 requires those findings in the list while SI-1 omits them from closure conditions. The planned combined BLOCKED-row test cannot establish whether an audit-only open finding prevents Closes.
- Failure: Audit-only open findings lack a defined closure oracle, and their extraction is both required and removable. Add: "A FINAL_AUDIT finding explicitly marked not closed or stays open forces Refs and inclusion of its ID, even without BLOCKED rows; this behavior cannot be cut and requires a standalone test."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Conflicting journal and audit verdicts have no defined expected result for tests.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §15 allows the verdict from FINAL_AUDIT.md or journal state, whereas CHANGE_PLAN.json §1 specifies parsing FINAL_AUDIT.md and leaves helper selection to implementation. Independent implementers and test authors could choose different authorities and disagree about whether identical inputs should produce Closes.
- Failure: Conflicting journal and audit verdicts have no defined expected result for tests. Add: "FINAL_AUDIT.md is the sole verdict authority; a missing, unreadable, or ambiguous audit verdict yields Refs regardless of journal state, with tests covering journal/audit disagreement."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
