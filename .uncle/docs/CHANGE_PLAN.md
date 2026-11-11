# Change plan: Issue 254

Seeded from [unclehq/uncle#254](https://github.com/unclehq/uncle/issues/254).

Issue 254

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature flag (none)

## 1. Selected technical approach

Add a pure Python helper `closing_trailer(j, origin)` in the embedded Python of `scripts/lib/change-pr.sh`, replacing the unconditional append at :1823-1825. It returns `Closes repo#N` when finished, else `Refs repo#N` followed by a `Still open` list. Inputs: `j.get('release_skipped')`; `override_record()` matching the verdict run (same condition as :1805); verdict parsed from FINAL_AUDIT.md (Verdict line, must be READY or READY_WITH_NON_BLOCKING_ISSUES); BLOCKED rows from `## Acceptance delivery` in IMPLEMENTATION_NOTES.md and `## Acceptance gate` in VERIFICATION_REPORT.md (Status cell BLOCKED*, and for the gate table Required cell YES); FINAL_AUDIT lines containing "not closed"/"stays open" with their finding IDs. Verdict authority (decision D-1): FINAL_AUDIT.md is the sole verdict authority. Journal state (including any verdict recorded in the journal `j`) is never consulted to decide closure; a missing, unreadable, or ambiguous audit verdict (no Verdict line, more than one conflicting Verdict line, or an unrecognized value) yields Refs regardless of journal state. Verdict parsing reuses whatever helper the file already uses for verdicts if one exists (inspect `verdict_run` use near :1805) provided it reads FINAL_AUDIT.md; otherwise a regex over FINAL_AUDIT.md. Any read/parse failure that prevents determining the verdict yields Refs (SI-3). Acceptance-evidence rule: Closes requires positive evidence that no required acceptance row is BLOCKED. If either acceptance document (IMPLEMENTATION_NOTES.md `## Acceptance delivery` or VERIFICATION_REPORT.md `## Acceptance gate`) is missing, unreadable, or malformed (section absent, table header or Status column not recognised, or a row that cannot be parsed), the helper emits Refs even when the verdict is READY or READY_WITH_NON_BLOCKING_ISSUES, and Still open carries a fixed-label evidence-unavailable entry naming the unavailable document. Unparseable or absent evidence is never treated as 'no blockers'; Closes is emitted only when both documents were positively parsed with no blocking row. Tests (in pr-closes-refs-test.sh) cover journal/audit disagreement in both directions (journal says READY while FINAL_AUDIT.md says NOT_READY -> Refs; journal says NOT_READY while FINAL_AUDIT.md says READY with no blockers -> Closes), missing, unreadable, and ambiguous FINAL_AUDIT.md verdict -> Refs, and each acceptance-evidence failure independently (missing notes, missing report, malformed notes table, malformed report table) -> Refs.

Still open rendering rule (AR-007, binding): every Still open entry is built only from (a) an ID that fully matches a strict allowlist pattern (acceptance/finding IDs such as `AC-[0-9]+`, `AR-[0-9]+`, `[A-Z]{1,6}-[0-9]{1,4}`; anything else is dropped, not sanitized) and (b) a fixed reason label chosen from a closed set in the helper (e.g. `required acceptance row BLOCKED`, `audit finding: issue stays open`, `release skipped`, `override recorded`). Repository-derived prose, table cell text, finding titles and arbitrary ID text are never copied into the trailer, so source text such as `Fixes owner/repo#123`, `Closes #1` or `Resolves ...` cannot reach the PR body. Adversarial fixture (in pr-closes-refs-test.sh): BLOCKED rows and FINAL_AUDIT 'stays open' lines whose text and ID cells contain `Fixes unclehq/uncle#123`, `closes #5` and embedded newlines; assert the body contains exactly one closing-keyword line (the origin trailer), that no emitted Still open line contains a closing keyword or a `#N` reference other than the origin, and that non-matching IDs are omitted.

## 2. Alternatives
A: change nothing in the driver, rely on GitHub keywords by hand (rejected: this is the bug). B: strip Closes at merge time (rejected: no hook). C: always Refs (rejected: breaks READY auto-close).

## 3. Why preferred
Smallest surface, fail-safe, local to body assembly.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
Audit/verdict computation, release_blocked_reason, draft logic at :1882, envelopes.

## 6. Data flow
Final audit/notes files -> helper -> trailer appended after `attach_body`. Banners unchanged.

## 8. Interface

Body trailer is `Closes o/r#N` or `Refs o/r#N` then optionally `\nStill open:\n- ...`. attach_body treats trailing lines beginning `Closes ` or `Refs ` (and Still open content following them) as trailer. Since attach_body runs before the trailer is appended in change-pr.sh, the attestation.py change matters for re-reading/legacy paths (tests at attestation-test.py:310,413). Decision D-2 (atomic recognition): attach_body moves trailing content only after recognizing a complete origin trailer, i.e. a line that fully matches `Closes <owner>/<repo>#<digits>` or `Refs <owner>/<repo>#<digits>`, optionally followed by a `Still open:` header and only `- ` bullet lines (blank lines allowed between). Anything else is preserved verbatim before the attestation: ordinary trailing bullet lists, a `Still open:` heading with no valid Closes/Refs line, and prose that merely begins with `Refs ` or `Closes ` (not matching the full origin-reference pattern) are never moved or altered.

## 10. Compatibility
No-origin runs unchanged; stored prepared bodies unchanged.

## 12. Error and recovery
Parsing is wrapped in try/except returning Refs; never blocks publish.

## 14. Rollback
Revert the commit; no data migration. Published PRs unaffected.

## 16. Automated-test strategy

New `scripts/tests/pr-closes-refs-test.sh` modeled on `pr-auto-publish-test.sh` fixture (origin file `unclehq/uncle\t107\tgh`): cases NOT_READY+override -> Refs (AC-1), READY_WITH_NON_BLOCKING + BLOCKED row -> Refs + Still open (AC-2), READY with all acceptance rows passing but a FINAL_AUDIT finding stating "not closed" or "stays open" and NO BLOCKED rows -> Refs with that finding ID in Still open (AC-2, standalone audit-only test; precedence rule: any such finding forces Refs regardless of an otherwise eligible verdict, and this behavior cannot be cut), READY -> Closes, no-origin -> neither (AC-3). Evidence-unavailable cases, each run independently with a READY verdict and otherwise-clean fixtures, all expecting Refs: (a) IMPLEMENTATION_NOTES.md missing; (b) IMPLEMENTATION_NOTES.md unreadable; (c) IMPLEMENTATION_NOTES.md `## Acceptance delivery` section absent or table malformed; (d) VERIFICATION_REPORT.md missing; (e) VERIFICATION_REPORT.md unreadable; (f) VERIFICATION_REPORT.md `## Acceptance gate` section absent or table malformed. Add suite name to `scripts/tests/critical-suites.txt`. Add cases to `scripts/tests/attestation-test.py` for Refs and Still open trailers (AC-4). Explicit run of new suite: `bash scripts/run-shell-tests.sh -- pr-closes-refs`. Regression tests that fail before fix: the NOT_READY case and the evidence-unavailable cases.

AC-4 atomic-recognition regressions in `scripts/tests/attestation-test.py` (each fails if attach_body scans backward without requiring a complete Closes/Refs origin trailer): (a) body ending in an ordinary bullet list; (b) body ending in a `Still open:` heading and bullets with no Closes/Refs line; (c) body ending in a prose line beginning `Refs ` that is not `Refs owner/repo#N`. In each, the trailing content must appear verbatim before the attestation block.

## 18. Manual verification
Post-fix: publish an unattended all-BLOCKED run and confirm `Refs #N` plus list; reopen/link #235 and #236 (human action, outside code).

## 19. Observability
None beyond PR body.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 1-2 | AC-1..3 | Closes only for finished work | closing_trailer helper | smallest local change | CAP-BODY | CODING |
| R-2 | REPOSITORY | change-pr.sh:1805 | AC-1 | override matches verdict_run | reuse override_record condition | consistency | CAP-BODY | CODING |
| R-3 | DESIGN | SI-3 | AC-1 | fail-safe to Refs: any unreadable verdict or missing/unreadable/malformed acceptance evidence yields Refs even when the verdict is READY | try/except plus explicit evidence-available check before Closes; evidence-unavailable entry in Still open | avoid false close when evidence cannot be established | CAP-BODY | CODING |

Feasibility: inspected change-pr.sh:1781-1825, attestation.py:318-335; no live credentials needed. Live check (human, post-merge): publish an all-BLOCKED run; no secrets prerequisite.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/change-pr.sh` | closing_trailer helper; replace :1823-1825 | core fix | Medium: body assembly | pr-closes-refs-test.sh, pr-auto-publish-test.sh |
| `scripts/lib/attestation.py` | attach_body strips a complete Closes/Refs origin trailer (with optional Still-open bullets) atomically; unrecognized trailing content is left verbatim | AC-4 | Low | attestation-test.py |
| `scripts/README.md` | document Closes vs Refs | AC-5 | None | inspection |
| `scripts/tests/pr-closes-refs-test.sh` | new suite | AC-1..3 | None | self |
| `scripts/tests/attestation-test.py` | add Refs and Still-open trailer cases plus atomic-recognition regressions: ordinary trailing bullet list preserved, unmatched `Still open:` heading preserved, prose beginning `Refs ` preserved | AC-4 | None | self |
| `scripts/tests/critical-suites.txt` | list new suite | ensure default run executes it | None | runner |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: A PR is published over a NOT_READY/overridden verdict, release skip, or ineligible or unavailable verdict -> body trailer is Refs, never Closes. Also: if either acceptance document (IMPLEMENTATION_NOTES.md `## Acceptance delivery`, VERIFICATION_REPORT.md `## Acceptance gate`) is missing, unreadable, or malformed, emit Refs even when the FINAL_AUDIT verdict is READY; unknown acceptance status is never treated as no blockers. Every Refs trailer includes a Still open list: available blocker IDs plus one single-line fixed-label reason for each applicable cause (override, release skip, ineligible verdict, unavailable verdict, missing/unreadable/malformed acceptance document), even when no IDs exist. Tests assert Still open is present and non-empty for each Refs cause, including override-only and release-skip-only cases. | SB-1 | SI-1, SI-3 | change-pr.sh | pr-closes-refs-test.sh: NOT_READY+override -> Refs, Still open non-empty, pr-closes-refs-test.sh: release skip only -> Refs, Still open non-empty, pr-closes-refs-test.sh: override only -> Refs, Still open non-empty, pr-closes-refs-test.sh: READY with IMPLEMENTATION_NOTES.md missing -> Refs, pr-closes-refs-test.sh: READY with VERIFICATION_REPORT.md missing -> Refs, pr-closes-refs-test.sh: READY with unreadable acceptance file -> Refs, pr-closes-refs-test.sh: READY with malformed Acceptance delivery table -> Refs, pr-closes-refs-test.sh: READY with malformed Acceptance gate table -> Refs | all-BLOCKED publish |
| AC-2: a PR whose acceptance is unfinished gets `Refs repo#N` and a Still open list naming the blocking row/finding IDs, never Closes. Unfinished means either (a) a required BLOCKED acceptance row, or (b) a FINAL_AUDIT finding stating the origin issue is "not closed" or "stays open". READY_WITH_NON_BLOCKING_ISSUES with a required BLOCKED row yields Refs plus Still open. Only required BLOCKED rows prevent closure on the table side: requiredness is read from the Required cell in both the Acceptance delivery and Acceptance gate tables, and an absent or unrecognized value is treated as required; an optional (Required=NO) BLOCKED row does not prevent Closes. An audit-only not-closed/stays-open finding forces Refs by itself, even when the verdict is READY or READY_WITH_NON_BLOCKING_ISSUES and no row is BLOCKED. This rule is not cuttable and takes precedence over verdict eligibility. | SB-2 | SI-1 | change-pr.sh | pr-closes-refs-test.sh (required BLOCKED-row case), pr-closes-refs-test.sh (optional Required=NO BLOCKED row does not prevent Closes), pr-closes-refs-test.sh (standalone audit-only still-open finding with READY verdict and no BLOCKED rows -> Refs + finding ID in Still open) | same |
| AC-3: READY verdict with no required BLOCKED acceptance row yields Closes (an optional Required=NO BLOCKED row in either table does not prevent it); a run with no origin emits neither Closes nor Refs. | SB-3, SB-4 | SI-1 | change-pr.sh | pr-closes-refs-test.sh, pr-auto-publish-test.sh | none |
| AC-4 | SB-5 | SI-2 | attestation.py | attestation-test.py: Refs trailer and Refs + Still open trailer handled, attestation-test.py: ordinary trailing bullet list preserved verbatim before attestation, attestation-test.py: unmatched `Still open:` heading with no valid Closes/Refs line preserved verbatim, attestation-test.py: prose beginning `Refs ` (not a full origin reference) preserved verbatim | none |
| AC-5 | SB-6 | none | README.md | none | read README |
| AC-6 | all | all | all | driver commands | none |

## Implementation sequence

1. Trailer detection in attach_body plus its tests. This step owns the shared trailer grammar: a complete trailer is a line fully matching `Closes <owner>/<repo>#<digits>` or `Refs <owner>/<repo>#<digits>`, optionally followed by a `Still open:` header and `- ` bullet lines. Step 2 must emit exactly this format. Step 1 also owns the atomic-recognition regression cases in attestation-test.py (ordinary trailing bullet list, unmatched `Still open:` heading, prose beginning `Refs `), each asserting verbatim preservation before the attestation.
   Owns: `scripts/lib/attestation.py`, `scripts/tests/attestation-test.py`
2. closing_trailer helper and call site, new shell suite, suite listing. The helper emits the exact trailer grammar defined in step 1, rendering Still open entries only from allowlisted IDs and fixed reason labels. pr-closes-refs-test.sh (owned here) must contain: the adversarial closing-keyword injection fixture (Fixes/Closes/Resolves owner/repo#123 in row and finding text and IDs); the standalone audit-only 'stays open' case (READY, no BLOCKED rows -> Refs plus finding ID); per-document missing/unreadable/malformed evidence cases under READY; Required=YES/NO/absent/unrecognized fixtures in both acceptance tables; Still open presence for each Refs cause including no-ID cases; and journal/audit verdict disagreement cases.
   Owns: `scripts/lib/change-pr.sh`, `scripts/tests/pr-closes-refs-test.sh`, `scripts/tests/critical-suites.txt`
   Depends on: 1
3. README update
   Owns: `scripts/README.md`
   Depends on: 2

## Scope cuts under time pressure

Cut first: Still open list formatting polish; then BLOCKED-row ID extraction detail, only after the items below are preserved. Never cut the Refs-vs-Closes decision, the fail-safe, the extraction of FINAL_AUDIT findings marked 'not closed'/'stays open' (they force Refs and appear by ID in Still open, with their standalone test), or the Still open allowlist-ID/fixed-label rendering rule and its adversarial fixture (AR-007).

## Risks and unresolved questions

- Verdict parsing format of FINAL_AUDIT.md must be confirmed at implementation; FINAL_AUDIT.md is the sole verdict authority and the fallback for any missing, unreadable, or ambiguous verdict is Refs (safe), regardless of journal state. None blocks starting.
- Reopening #235/#236 is a human action outside this change.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan only guaranteed Refs when the verdict was undeterminable; a READY verdict with unavailable acceptance evidence was undefined and could close unfinished work. | Section 1 and R-3 now state that missing, unreadable or malformed acceptance evidence yields Refs even on READY, with an evidence-unavailable reason in Still open. |
| AR-002 | Accepted | Real gap: audit open-finding extraction was both required and cuttable, with no closure precedence; an explicit still-open audit finding must force Refs. | Add standalone audit-only test case to s11.1 and AC-2 tests/requirement, and state the non-cuttable precedence rule. |
| AR-003 | Accepted | Optional BLOCKED rows must not prevent closure; requiredness must be determined uniformly, failing safe to required when absent or unrecognized. | AC-1, AC-2 and AC-3 traceability requirements state that only required BLOCKED rows (Required cell, absent/unrecognized treated as required, in both tables) prevent closure. |
| AR-004 | Accepted | A Refs trailer with no Still open content leaves code and tests free to disagree on whether a bare Refs satisfies the spec. | Traceability AC-1 requirement now states every Refs trailer carries a Still open list with fixed single-line reason labels, even with no IDs. |
| AR-005 | Accepted | A readable READY verdict with missing or malformed acceptance evidence was undefined; unknown status must never read as no blockers. | Traceability AC-1 requirement/tests now state Refs for READY with missing/unreadable/malformed acceptance docs, tested independently per file. |
| AR-006 | Accepted | Backward scanning without atomic recognition could move ordinary trailing bullets or prose into the trailer area and alter body content. | s7.1 makes trailer recognition atomic (only a complete Closes/Refs origin trailer is moved); s11.1 and AC-4 add regression cases. |
| AR-007 | Accepted | Single-line sanitization still lets repository prose like `Fixes owner/repo#123` into the body; emitting only validated IDs and fixed labels removes that path. | s1.1 gains a Still open rendering rule (validated IDs, fixed labels, adversarial fixture); s18.1 forbids cutting it. |
| AR-008 | Accepted | A readable READY verdict with missing, unreadable or malformed acceptance evidence must not close the issue; the plan only covered verdict-determination failures. | Section 1 now emits Refs when either acceptance document is missing, unreadable or malformed even if READY; section 16 tests each failure independently. |
| AR-009 | Accepted | Audit-only open findings need a defined closure oracle, and the plan both required and allowed cutting their extraction. | Edit AC-2, s11.1 and s18.1: not-closed/stays-open findings force Refs with their IDs, are uncuttable, and get a standalone test. |
| AR-010 | Accepted | Two verdict authorities would let identical inputs produce Closes or Refs; a single authority makes the test oracle unambiguous. | s1.1 names FINAL_AUDIT.md as sole verdict authority (Refs if missing/unreadable/ambiguous, journal ignored); s19.1.i1 updated; journal/audit disagreement test added. |
