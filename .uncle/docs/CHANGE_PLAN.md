# Change Plan

Issue 142

Seeded from [unclehq/uncle#142](https://github.com/unclehq/uncle/issues/142).

Omitted sections: Schema (none); Migration (none); Concurrency (none beyond existing locks); Feature flag (env opt-in is the containment)

## 1. Selected technical approach

Add `confirm_replace_change_request` to `scripts/from-issue.sh`. Call it in the `change)` case right after `check_origin_or_refuse`, only when `UNCLE_NEW_WORKFLOW != 1`, `SEED_ONLY != 1`, `! seed_is_current`, and an entry exists at `generated_input_path CHANGE_REQUEST.md` (tested with `-e` or `-L`: regular file, symlink, dangling symlink or directory) that is not a zero-byte or whitespace-only regular file. A zero-byte or whitespace-only regular CHANGE_REQUEST.md counts as absent: no prompt, replaced without asking. The prompt is shown whenever such an entry exists and seed_is_current is false, regardless of content (even identical to the new request) or the issue number it was seeded for. The guard does not run on stdin-import or seed-only paths; those keep their existing no-clobber behavior (V3). The replacing write must not follow symlinks: remove the entry or write via a temp file and `mv -f`, so a change between guard and write cannot redirect the write through a link.

Logic, in order: (1) if `UNCLE_REPLACE_CHANGE_REQUEST` is exactly the string `1`, proceed without prompting, in both interactive and unattended modes; unset, empty, `0`, `true`, `yes` and every other value do not count. (2) Else, if `UNATTENDED==1` (set to 1 by the `--unattended` flag or `UNCLE_UNATTENDED=1`; the function checks `UNATTENDED` only for this) OR stdin is not a TTY (`! [ -t 0 ]`, which covers the TUI, the driver, closed stdin and piped request content), treat the run as unattended: print a stderr message naming the file and `UNCLE_REPLACE_CHANGE_REQUEST=1` and `exit 1` without ever reading stdin, so piped request content is never consumed as an answer. (3) Else (interactive TTY) print the file path and `Proceed with the new change request and replace it? [y/N] `, then `read -r ans || true` so an unterminated final line (e.g. `y` with no newline) is still used; EOF with no data yields empty. Normalize the answer by stripping all CR characters, trimming leading/trailing whitespace and lowercasing; only the exact strings `y` or `yes` proceed. Everything else (empty, EOF, `n`, `y please`, junk) prints a stop message and `exit 1`.

Streams and display: the prompt and all stop/refusal messages go to stderr; the answer is read from stdin only. The printed path has control characters escaped (for example via `printf '%q'`) so a hostile path cannot inject terminal sequences.

Decision D1: guard before the archive step so a decline modifies nothing. D2: skip for UNCLE_NEW_WORKFLOW (old evidence is archived, so nothing is lost). D3: no archiving of the old request (not required; deferred). D4: prompt on stdin like `offer_worktree_removal`, only when stdin is a TTY.

- Unattended rule (AR-001): unattended means `UNATTENDED` equals exactly `1` (set by the --unattended flag or by `UNCLE_UNATTENDED=1`); any other value is interactive.
- Opt-in rule (AR-002): `UNCLE_REPLACE_CHANGE_REQUEST` permits replacement only when it is exactly the string `1`; unset, empty, `0`, `true` and every other value refuse.
- SEED_ONLY rule: with `SEED_ONLY=1` and an existing request file, no prompt is shown and the existing no-overwrite behavior (V3) is unchanged.
- Existence rule (AR-003): a zero-byte CHANGE_REQUEST.md counts as absent (no prompt, overwritten silently); a file with at least one byte, including whitespace-only content, counts as existing and triggers the guard.
- Output rule: the prompt and all stop/refusal messages go to stderr; stdout is unchanged. The prompt text contains the CHANGE_REQUEST.md file path and the exact phrase `Proceed with the new change request and replace it? [y/N]`.
- Message rule: the unattended refusal message goes to stderr and contains the literal `UNCLE_REPLACE_CHANGE_REQUEST=1`; the decline stop message states that the existing request was left unchanged. Tests assert prompt shown or not shown by matching this stderr text.
- V2 scope (AR-004): the decline guarantee covers CHANGE_REQUEST.md and .uncle/workflow in the current worktree, which stay byte-identical after a decline. A worktree created earlier in the same invocation is out of scope.

## 2-3. Alternatives and rationale
| Alternative | Rejected because |
|---|---|
| Prompt inside write_change_request | Runs after archive/origin steps; decline would not be side-effect free |
| Prompt in change-workflow.sh | File already seeded by then; too late |
| Archive then overwrite | Not requested; larger surface |

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`scripts/lib/change_request_stdin.py`, `change-workflow.sh`, `new)` flow, existing tests.

## 6-8. Data flow / state / interface

No state change on decline. New env var `UNCLE_REPLACE_CHANGE_REQUEST=1` (unattended/non-TTY opt-in); no flag or API changes. The guard never reads piped (non-TTY) stdin, so request content destined for change_request_stdin.py is neither consumed nor taken as an answer. When stdin is a TTY, the prompt and stop messages are written to stderr and the answer is read from stdin and normalized (CR and whitespace stripped, lowercased, exact match on y|yes).

## 10. Compatibility
B2-B6 preserved; only B1 modified (spec S1/S2/S4).

## 12. Error and recovery
Decline/EOF/unattended refusal: exit 1, message, no side effects; rerun after removing file or answering yes.

## 14. Rollback plan
Revert the from-issue.sh hunk, README lines and new test; no persisted data.

## 16. Automated-test strategy

New `scripts/tests/change-request-exists-prompt-test.sh`, mandatory end-to-end invocations of from-issue.sh (function-extraction cases per issue-document-test.sh pattern are supplementary only) in temp dirs with fixtures. Cases: answers y, YES, n, empty, EOF, junk; answer parsing `y\r\n`, ` Yes `, unterminated final `y` accept, `y please`, `yes!`, `yy` decline; no prompt for no file, zero-byte file, UNCLE_NEW_WORKFLOW=1, SEED_ONLY=1 with existing request (assert no prompt and V3 no-overwrite unchanged), seed_is_current; whitespace-only file prompts; symlink, dangling symlink and directory at CHANGE_REQUEST.md trigger confirmation and the symlink target is not clobbered; opt-in values unset, empty, 0, true refuse versus exactly 1 proceeds; non-TTY piped request content with an existing file: guard does not read it, follows the unattended rule, piped content left unconsumed; unattended via --unattended and UNCLE_UNATTENDED=1 with and without opt-in (never-writing fifo under timeout); after decline assert CHANGE_REQUEST.md hash and .uncle/workflow tree byte-identical; assert stderr strings for prompt shown/not shown and README grep.

## 17. Regression strategy
Existing issue-document-test.sh, worktree-auto-seed-test.sh, unattended-test.sh stay unchanged and green; driver full suites (verification commands in baseline).

## 18. Manual verification
Run `scripts/from-issue.sh` change mode in a scratch repo with an existing request: confirm prompt, y proceeds, n stops with file intact.

## 19. Observability
One-line stderr messages stating decision and the opt-in variable.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/from-issue.sh` | Add confirm function and call in `change)` | Requested behavior | Medium: non-interactive callers | New test; issue-document, worktree-auto-seed, unattended tests |
| `scripts/tests/change-request-exists-prompt-test.sh` | New test | AC-1..5 | Low | Self |
| `scripts/README.md` | Document prompt and `UNCLE_REPLACE_CHANGE_REQUEST` | AC-4 | Low | grep in new test |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: when a non-empty CHANGE_REQUEST.md exists and the seed is not current, the user is prompted on stderr; the prompt names the file path and contains `Proceed with the new change request and replace it? [y/N]`; y/yes proceeds. | S1 | V1 | from-issue.sh | new test y/YES | prompt y |
| AC-2 | S2 | V1, V2 | from-issue.sh | new test n/empty/EOF, new test answer parsing: CRLF `y\r`, ` Yes `, unterminated final `y` accept; `y please`, `yy`, `n` decline | prompt n |
| AC-3: With no existing CHANGE_REQUEST.md, or a zero-byte one (treated as absent), no prompt is shown and the file is written/replaced silently as before. A whitespace-only file counts as existing and prompts. | S3 | V1 | from-issue.sh | new test no-file, new test zero-byte file: no prompt, replaced silently, new test whitespace-only file: treated as existing, prompts | scratch repo |
| AC-4: Unattended means UNATTENDED=1 or UNCLE_UNATTENDED=1 exactly (other values are interactive). In that mode an existing request file is never replaced unless UNCLE_REPLACE_CHANGE_REQUEST is exactly 1; otherwise exit 1 with a message naming that variable, without reading stdin. | S4 | V1, V2 | from-issue.sh, README | new test: --unattended flag and UNCLE_UNATTENDED=1, each with and without UNCLE_REPLACE_CHANGE_REQUEST=1, end to end | run once with --unattended and once with UNCLE_UNATTENDED=1 |
| AC-5: In-flight resume (seed_is_current), UNCLE_NEW_WORKFLOW=1 and SEED_ONLY=1 never show the prompt; with SEED_ONLY=1 and an existing request file, existing no-overwrite behavior (V3) is unchanged. | S5, S6 | V3 | from-issue.sh | new test end to end: no prompt for NEW_WORKFLOW, SEED_ONLY, seed_is_current, empty file; hash and .uncle/workflow unchanged after decline; plus existing tests | resume run |
| AC-6 | all | all | all | driver suites | n/a |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Acceptance criteria | AC-4 | Unattended never hangs; unattended means UNATTENDED=1 or UNCLE_UNATTENDED=1 exactly, opt-in only when UNCLE_REPLACE_CHANGE_REQUEST is exactly 1 | Check UNATTENDED (set by --unattended or UNCLE_UNATTENDED=1) and stdin-is-not-a-TTY before any read; never read piped stdin. Opt-in replacement is honored only when UNCLE_REPLACE_CHANGE_REQUEST is exactly 1; unset, empty, 0, true and all else refuse. All prompt and refusal text goes to stderr, the displayed path is control-character-escaped, and the answer is read from stdin only. | DESIGN, revisable | CAP-NONE | `UNATTENDED` var from-issue.sh L462-470 inspected; set by --unattended flag or UNCLE_UNATTENDED=1; tests cover both | CODING |
| R-2 | USER | CHANGE_REQUEST.md Requested behavior 3 | AC-2 | Decline modifies nothing in the current worktree (CHANGE_REQUEST.md and .uncle/workflow stay byte-identical); a worktree created earlier in the same invocation is out of scope | Guard before archive/write_origin; any existing path entry (file, symlink, dangling symlink, directory) triggers confirmation, and the replacing write does not follow symlinks | DESIGN, revisable | CAP-NONE | change) case order L918-948 inspected | CODING |

No live-authentication prerequisites; all verification is local shell tests.

## Implementation sequence

1. Add `confirm_replace_change_request` and its call in the `change)` case; this step owns the pinned prompt and stop-message wording (stderr; file path plus `Proceed with the new change request and replace it? [y/N]`; unattended/non-TTY refusal containing `UNCLE_REPLACE_CHANGE_REQUEST=1`) that steps 2 and 3 consume; `bash -n` check
   Owns: `scripts/from-issue.sh`
2. Write the new shell test. It MUST invoke from-issue.sh end to end (not only the extracted function) and cover: no prompt for UNCLE_NEW_WORKFLOW=1, SEED_ONLY=1, seed_is_current, and an empty/zero-byte request file; prompt shown with y/YES/n/empty/EOF/junk answers; after decline assert CHANGE_REQUEST.md hash and the .uncle/workflow tree are byte-identical; unattended cases using both the --unattended flag and UNCLE_UNATTENDED=1, each with and without UNCLE_REPLACE_CHANGE_REQUEST=1 (stdin from a never-writing fifo under timeout to prove no hang). These end-to-end cases are never cut.
   Owns: `scripts/tests/change-request-exists-prompt-test.sh`
   Depends on: 1, 3
3. Document prompt, answers, unattended default and opt-in
   Owns: `scripts/README.md`
   Depends on: 1
4. Run the new test and existing issue-document, worktree-auto-seed, unattended tests
   none (read-only)
   Depends on: 1, 2, 3

## 21. Scope cuts under time pressure

Cut first: README wording polish. Never cut the end-to-end from-issue.sh test cases, the unattended no-hang behavior, or decline-leaves-state-unchanged.

## 22. Risks and unresolved questions

- Non-interactive callers (TUI) with no stdin now stop instead of overwriting; mitigation: EOF = no, clear message; env opt-in available. Tests cover both the --unattended flag and UNCLE_UNATTENDED=1, each with and without UNCLE_REPLACE_CHANGE_REQUEST=1.
- Worktree may already be created before decline; accepted.
- Archiving the old request: deferred.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan skips the prompt for SEED_ONLY=1 but never states the behavior as a requirement; it should be explicit and tied to V3. | Added SEED_ONLY clarification to s1.1 and AC-5 requirement; s6.1 notes no prompt and V3 unchanged. |
| AR-002 | Accepted | Unattended detection must be one pinned rule shared by plan and spec: UNATTENDED=1 or UNCLE_UNATTENDED=1 exactly, opt-in only when exactly 1. | Added exact unattended definition to s1.1, AC-4 requirement and R-1 property. |
| AR-003 | Accepted | Real ambiguity; a zero-byte request file holds no content to lose, so treating it as absent is safe. | s1.1 adds a rule that a zero-byte CHANGE_REQUEST.md counts as absent (no prompt, silent overwrite); AC-3 states the same. |
| AR-004 | Accepted | Real inconsistency between V2's byte-identical claim and the accepted pre-decline worktree creation. | s1.1 and R-2 scope V2 to CHANGE_REQUEST.md and .uncle/workflow in the current worktree; a worktree created earlier in the same invocation is out of scope. |
| AR-005 | Accepted | Pinning the rule removes ambiguity for identical-content and different-issue files. | s1.1 states the prompt is shown whenever the file exists and seed_is_current is false, regardless of content or issue number. |
| AR-006 | Accepted | Stream and answer normalization must be fixed so tests can assert them. | s1.1 specifies stderr output and trimmed, CR-stripped, lowercased exact match on y\|yes. |
| AR-007 | Accepted | Non-TTY callers with closed or EOF stdin would otherwise silently regress from overwrite to exit 1 after an ambiguous read; treating them as unattended gives a deterministic, no-read refusal with an opt-in message. | s1.1: non-TTY stdin (not -t 0) without UNCLE_REPLACE_CHANGE_REQUEST=1 is treated as unattended: print opt-in message, exit 1, never read. |
| AR-008 | Accepted | The opt-in's interactive effect and the guard's coverage of stdin-import and seed-only paths were unstated. | s1.1: UNCLE_REPLACE_CHANGE_REQUEST=1 also skips the prompt interactively; the guard does not run on stdin-import or SEED_ONLY paths (V3 unchanged). |
| AR-009 | Accepted | Reading the answer from piped request content would consume the request body or misread it as an answer, so the guard must never read non-TTY stdin. | s1.1 now treats non-TTY stdin as unattended (no read); s5.1 states the guard never reads piped stdin; R-1 mechanism updated. |
| AR-010 | Accepted | The plan said non-empty but the spec said only existing; pinning empty/whitespace-only as absent resolves the mismatch. | s1.1 defines zero-byte or whitespace-only CHANGE_REQUEST.md as absent (no prompt, replaced); AC-3 requirement and tests updated. |
| AR-011 | Accepted | Real ambiguity: the plan named two variables; the flag and UNCLE_UNATTENDED=1 already both set UNATTENDED, so one check suffices. | s1.1 and R-1: the confirm function checks only UNATTENDED, which is 1 when --unattended or UNCLE_UNATTENDED=1 is used. |
| AR-012 | Accepted | An unvalidated opt-in could let an ambient value silently allow overwrites; exact-match is the safe rule. | s1.1 and R-1: only the exact string 1 in UNCLE_REPLACE_CHANGE_REQUEST permits replacement; unset, empty, 0, true and all else refuse. |
| AR-013 | Accepted | Existing-path semantics and the guard-to-write race were unspecified and could break V1/V2. | s1.1 now triggers on any existing path entry and requires a no-follow write; R-2 mechanism updated. |
| AR-014 | Accepted | Prompt stream and path sanitization were unspecified, so tests could not assert on them. | s1.1 pins prompt/messages to stderr, escaped path, answer from stdin only; R-1 mechanism updated. |
| AR-015 | Accepted | Function-only tests cannot prove gating or decline-before-archive; end-to-end invocation must be mandatory and uncuttable. | step-2 text and AC-5 tests now require end-to-end from-issue.sh cases with hash and .uncle/workflow checks, never cut. |
| AR-016 | Accepted | Unattended mechanisms differ across spec, plan and manual check; tests must cover both flag and env var with and without opt-in. | AC-4, R-1 evidence, step-2 and risk s18.1.i1 now cover --unattended and UNCLE_UNATTENDED=1, each with/without UNCLE_REPLACE_CHANGE_REQUEST=1. |
| AR-017 | Accepted | Edge cases of the existing-file test and opt-in value were unspecified and need pinning so tests have a single expected result. | s1 new block pins: zero-byte is absent, whitespace-only is existing, opt-in only when exactly 1; AC-3 updated. |
| AR-018 | Accepted | Prompt stream and wording must be fixed so tests can assert prompt shown or not shown. | s1 new block pins stderr output, prompt wording with file path, and unattended message containing UNCLE_REPLACE_CHANGE_REQUEST=1; AC-1 updated. |
| AR-019 | Accepted | Answer parsing was undefined for CRLF, trailing text and an unterminated final line; pinning it makes the tests deterministic. | s1.1 now specifies CR stripping, trim, lowercase, exact y\|yes match, and acceptance of an unterminated final line; AC-2 requirement updated. |
