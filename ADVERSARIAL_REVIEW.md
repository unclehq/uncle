## AR-001: Description sources are not necessarily audit-bound

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_SPEC.md:I-1,§11; CHANGE_PLAN.md:P-6,P-14; scripts/lib/change-pr.sh:78,99–111,161 |
| Failure | A symlinked notes file can supply external content changed after audit because snapshots bind the link target path, not its contents; existing drift tests cannot reject publication of that content through the proposed default. |
| Fix | Extract defaults from regular-file blobs in the bound tree; reject symlink or absent sources. |
| Verify | Change an external symlink target after binding; assert its contents never enter the preview or PR body. |

## AR-002: Checklist reference does not provide verification steps

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md:Motivation.2; CHANGE_SPEC.md:AR-3,I-6; CHANGE_PLAN.md:P-8,P-19,T-1; scripts/lib/change-pr.sh:335–342 |
| Failure | Any nonempty checklist allows blank input to publish only “Follow MANUAL_CHECKLIST.md,” leaving the description without actions or expected results; the planned blank-acceptance test can pass despite violating AR-3. |
| Fix | Prefill concise actions and expected results from the checklist; require typed steps when usable checks are absent. |
| Verify | Assert the submitted body contains fixture-specific actions and outcomes; a headings-only checklist must require input. |

## AR-003: Required comment has no implementation decision

| Field | Value |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md:Motivation.3; CHANGE_SPEC.md:AR-4; CHANGE_PLAN.md:P-9,R-2,S-1,M-2; scripts/lib/change-pr.sh:342–345,398–414 |
| Failure | Under AR-4’s post-merge-comment requirement, the planned body reference supplies no comment-producing operation; T-1 checks only reference text, and R-2 leaves the required implementation scope undecided. |
| Fix | Resolve whether the requirement accepts a closing body reference before approval; otherwise specify the comment lifecycle, ownership, retries, and rollback. |
| Verify | Make M-2’s required observable explicit and record it; issue closure alone must not satisfy a retained comment requirement. |

## AR-004: Embedded terminators truncate editable defaults

| Field | Value |
|---|---|
| Severity | Medium |
| References | CHANGE_SPEC.md:AR-2; CHANGE_PLAN.md:P-7,P-11,T-2; uncle_tui.py:1562–1580; scripts/tests/pr-prompt-test.py:test_every_chunk_boundary |
| Failure | A default containing `]:` opens the dialog prematurely when a chunk ends there; direct Python invocation of `_detect_prompt()` reproduced a truncated buffer that stayed truncated after completion, while all five existing prompt tests passed. |
| Fix | Make prompt framing distinguish embedded delimiters from completion before extending it to summary defaults. |
| Verify | Split each new prompt immediately after an embedded `]:`; assert no dialog opens until completion and the editable buffer preserves the entire default. |

## AR-005: Summary extraction assumes an unenforced producer format

| Field | Value |
|---|---|
| Severity | Medium |
| References | CHANGE_REQUEST.md:Motivation.2; CHANGE_PLAN.md:P-6,P-7,P-15,T-1; prompts/change/implement-change.md:45–54; scripts/lib/change-pr.sh:193–198 |
| Failure | Widening to the notes producer revealed that it requires sections, not Purpose-column cells; valid notes with purpose prose therefore fall back to the requested-change title, and table-only fixtures miss a description that never summarizes completed work. |
| Fix | Define a supported producer-consumer format or extract the existing purpose section; require an entered summary when neither yields completed-work content. |
| Verify | Supply valid section-based notes without a Purpose table; assert the body describes completed work rather than merely repeating the request title. |

## Blocking findings

AR-001, AR-002, AR-003: resolve before approval.

## Regression risks

AR-004, AR-005.

## Recommended simplifications

AR-003: settle contract first.

## Required test additions

AR-001–AR-005: required.

## Overall assessment

Reject pending corrections.