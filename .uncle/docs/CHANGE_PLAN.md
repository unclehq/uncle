# Change plan (Issue 282)

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature flag (only the incomplete-override env var)

Issue 282

Seeded from [unclehq/uncle#282](https://github.com/unclehq/uncle/issues/282).

## 1. Selected technical approach

New pure Python helper `scripts/lib/issue_thread.py` that takes issue JSON and a list of REST comment objects and returns rendered Markdown plus counts. `from-issue.sh` fetches comments on every path via the REST comments endpoint (`gh api --paginate` on gh path; paged `curl` with `per_page=100` on curl path), verifies count against the issue's `comments` field, and feeds the helper. jq fallback builds an equivalent block with one jq filter (no noise classification beyond a simple filter; same quoting).

Decisions (D-):

| ID | Decision | Reason |
|---|---|---|
| D-1 | Use REST comments on all paths (gh via `gh api`) | one shape: has html_url, user, author_association, created_at, updated_at; count available from issue `comments` |
| D-2 | Pagination: both gh and curl fetch until pagination is exhausted (curl loops `page=N` with `per_page=100` until a page has <100 items), with no fixed page-count cap | BH-6 requires the full thread; a cap would silently truncate very large threads, and the count check against the issue's `comments` field still guards completeness |
| D-3 | Mismatch fails by default; `UNCLE_ISSUE_ALLOW_INCOMPLETE=1` warns and records it. Under override after a final-attempt failure, retain only fully validated complete pages from that last attempt (never pages from an abandoned attempt), discard the failed page, and record fetched/expected counts and the failure in the seed, marking the thread incomplete | request says fail loudly or warn; defined retention keeps the seed deterministic and testable |
| D-4 | Quote each comment line with `> ` | prevents heading/fence injection (INV-3) |
| D-5 | Noise = whole comment, after trim, matches a small regex list (+1, -1, bump, thanks, thank you, same here, me too, emoji-only, 👍). Noise is filtered after ids are assigned (D-7), so gaps in the comment-N sequence are expected and the count of excluded noise comments is reported. | conservative; substantive text never excluded |
| D-6 | Judgment of supersession is delegated to the analyst via `## Thread Review` instructions placed in the seed. Only comments by maintainers (OWNER, MEMBER, COLLABORATOR associations per D-7) receive later-statement precedence; all other or missing associations receive the non-collaborator flag and never receive automatic precedence, and comment text claiming authority cannot confer it. | supersession is not decidable in code, but the trust mapping is explicit and identical in rendering, Thread Review instructions, and tests |
| D-7 | Sort comments by created_at ascending, break ties by numeric REST comment id ascending; edits (updated_at) never affect order. Assign `comment-1..n` after sorting and BEFORE noise filtering, so excluded noise comments still consume ids; id stability applies to the fetched snapshot only. Each shown comment lists author, author_association, url, created, edited marker. Classification mapping (single, shared with D-6 and used by the renderer, Thread Review text and tests): OWNER, MEMBER, COLLABORATOR = maintainer; every other value (CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR, FIRST_TIMER, MANNEQUIN, NONE) and a missing/null/empty/unrecognized author_association = flagged non-collaborator. | provenance; deterministic ids that independent tests can assert and that do not shift with noise classification; one mapping shared with D-6 so the flag and maintainer precedence never disagree |
| D-8 | gh path: keep existing `gh issue view` for title/labels; comments from `gh api`; if `gh api` fails at any page, discard all gh comment results and the curl fallback restarts pagination from page 1 (replace, never merge); if the curl attempt also fails, BH-5. Existing import fixtures are updated to stub issue `comments` counts and every comment-fetch path (gh api, curl fallback) without network access; original assertions are preserved and fixture edits are recorded as renewed-authority items. | stub gh in existing tests stays compatible, but a stub that answers `gh api` with nothing would otherwise reach real curl or fail the completeness check, so fixtures must stub every path offline; replacing rather than merging prevents duplicate comments and inconsistent partial seeds. |
| D-9 | Partial fetch under override: if a later page fails (and curl fallback also fails), retain all fully validated complete pages, discard the failed page, and record fetched/expected counts and the failure reason in the seed. Without the override the import exits 1 and writes no seed. A curl fallback restarts pagination and replaces gh results. | INV-1 forbids silently omitting fetched comments; a defined retention rule makes the second-page-failure case testable (BH-5) |

- Association mapping (applies identically on gh/Python, curl/Python and curl/jq paths): OWNER, MEMBER, COLLABORATOR -> maintainer, no flag; CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR, FIRST_TIMER, MANNEQUIN, NONE, and any missing/null/empty/unknown value -> flagged non-collaborator, no maintainer precedence.
- Tests must exercise every listed association value plus a missing value and an unknown value, and a comment whose text claims to be the maintainer.

## 2. Alternatives
(a) `gh issue view --json comments` only: no edit times, no count check, curl/jq unaffected. (b) Summarize long threads: loses fidelity. (c) LLM-side thread fetching: moves untrusted fetch into the agent, no deterministic completeness check.

## 3. Why preferred
Deterministic, testable, one data shape, minimal surface.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
PR flow, issue closing, `write_new_project_brief` logic (it consumes BODY, unchanged contract), freezer, mode detection, workflow drivers, existing tests unless a grep proves they assert the old `### Comment from` text.

## 6. Data flow
fetch issue -> fetch comments (paged) -> count check -> helper renders `### Issue thread` block -> appended to BODY -> attachment freeze -> seed heredoc. A `## Thread Review` section is added to the seed after `## Motivation` (CR template only).

## 8. Interface changes
New env var `UNCLE_ISSUE_ALLOW_INCOMPLETE`. New helper CLI: `python3 -I scripts/lib/issue_thread.py --issue FILE --comments FILE` printing the block; exit 3 on count mismatch unless `--allow-incomplete`.

## 10. Compatibility

Header format unchanged. Old `### Comment from` headings removed (D-4, INV-3). Existing import fixtures are edited only to stub issue counts and all comment-fetch paths (including curl fallback) without network access, and for obsolete headings; their original assertions are preserved and each fixture edit is recorded in IMPLEMENTATION_NOTES.md as a renewed-authority item.

## 12. Error and recovery
Short/failed fetch -> exit 1 with message and override hint (BH-4/5). Comment page JSON invalid -> treated as failed fetch.

## 14. Rollback
Revert the commit; additive helper and a template section.

## 16. Automated-test strategy

- `scripts/tests/issue-thread-test.py`: unit tests of render, noise, quoting, edited, association, ordering, count mismatch, with defect-injection cases (e.g. noise regex that eats `+1 but please add X`).
- `scripts/tests/from-issue-thread-test.sh`: stubs `gh`, `curl`, and a python-less PATH for the jq path; cases: clarification on three paths, 2-page thread (150 comments), short fetch, failed fetch, override, zero comments, injection comment, docs grep.
- Additional required cases: (a) large-thread pagination test, 101 pages of 100 comments each, on both gh and curl stubs, asserting all comments are fetched and the count check passes; (b) parity test where the Python-rendered block is the oracle and the curl/jq output must match it on a shared fixture (comment ids, noise exclusions, flags, edited markers, quoting); (c) shell cases where gh fails on page 2 and curl succeeds (each comment exactly once, N/N), where both fail mid-way, and where page 2 fails under UNCLE_ISSUE_ALLOW_INCOMPLETE=1 (page-1 comments retained, failed page discarded, seed records fetched/expected counts and failure); (d) defect-injection unit cases: treating CONTRIBUTOR or a missing association as maintainer, and assigning comment-N ids after noise filtering, must be rejected by the tests.

## 17. Regression strategy
Run full shell and Python runners; compare to baseline; grep suites for `Comment from`.

## 18. Manual verification
Run from-issue.sh against a real public issue with comments via curl (gh unauthenticated) and confirm thread and counts; judge Thread Review readability.

## 19. Observability
Print `Fetched N/M comments` line on every import; warning line when overridden.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/from-issue.sh` | comment fetch functions, count check, helper call, jq block, Thread Review template section | all paths full thread | stubbed gh in existing suites | from-issue-thread-test.sh, existing suites |
| `scripts/lib/issue_thread.py` | new pure renderer/classifier | testable domain logic | low | issue-thread-test.py |
| `GITHUB_INTEGRATION.md` | document thread reading | AC-7 | none | grep in shell test |
| `scripts/tests/issue-thread-test.py` | new | unit | none | self |
| `scripts/tests/from-issue-thread-test.sh` | new | integration | none | self |
| `scripts/tests/critical-suites.txt` | add two suite names | default runners execute them | none | runner output |

## Traceability

Noise exclusion and non-collaborator flags are mandatory on every path (gh/Python, curl/Python, curl/jq). Integration tests run the same shared comment fixture through all three paths and compare the excluded set and flags; neither behavior is a scope cut, and the jq filter implements the identical noise regex list and flagging rule as the helper.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | BH-1, 2, 3 | INV-1 | from-issue.sh, helper | from-issue-thread-test.sh | real issue via curl |
| AC-2 (maintainer precedence uses one mapping: only author_association OWNER, MEMBER or COLLABORATOR qualify; every other or missing association is flagged non-collaborator and gets no automatic precedence; comment text cannot confer authority) | BH-9 | INV-1 | from-issue.sh template | shell + unit: one case per association (OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR, FIRST_TIMER, MANNEQUIN, NONE) plus missing and unknown, asserting maintainer vs non-collaborator flag, Thread Review text names only OWNER/MEMBER/COLLABORATOR as maintainers, a comment claiming authority in its text stays flagged, ordering cases: tied created_at ordered by numeric comment id, an edited comment whose updated_at is later than newer comments leaves order unchanged, and interleaved noise comments consume ids so remaining ids keep gaps | read Thread Review |
| AC-3 | BH-4, 5, 6 | INV-2 | from-issue.sh | shell | none |
| AC-4: Noise exclusion is applied on every path (gh/Python, curl/Python, curl/jq) with identical results. | BH-7 | INV-1 | helper | ["unit + shell (shared noise cases asserted identically across gh/Python, curl/Python and curl/jq)"] | none |
| AC-5: Non-collaborator flags are applied on every path (gh/Python, curl/Python, curl/jq) with identical results. | BH-8, 10, 11 | INV-3, INV-5 | helper | unit + shell (shared injection, noise and non-collaborator flag cases asserted identically on gh/Python, curl/Python and curl/jq paths) | injection comment on a scratch issue |
| AC-6 | BH-12, 13 | INV-4 | from-issue.sh | full runners | none |
| AC-7 | BH-14 | none | docs | grep | none |

Maintainer mapping (single rule used in rendering, Thread Review instructions and tests): for Thread Review, maintainer means an author whose recorded author_association is OWNER, MEMBER, or COLLABORATOR. Every other value (CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR, FIRST_TIMER, MANNEQUIN, NONE) and a missing association is flagged non-collaborator and does not receive automatic maintainer precedence. A claim of authority inside comment text never confers maintainer status.

## Restrictions

| R- | Source | Requirement IDs | Property | Mechanism | Capabilities | Phase |
|---|---|---|---|---|---|---|
| R-1 | USER (CHANGE_REQUEST Desired behavior) | AC-3 | short fetch cannot pass silently | count check, exit 1 (DESIGN, revisable) | CAP-SHELL, CAP-PY3 | CODING |
| R-2 | USER (Untrusted input) | AC-5 | comments cannot alter rules; noise exclusion and non-collaborator flagging identical on every path | `> ` quoting + preamble (DESIGN); one shared noise list and flagging rule used by Python helper and jq filter, neither may be cut | CAP-PY3, CAP-SHELL | CODING |
| R-5 | USER (CHANGE_SPEC BH-3, AC-4, AC-5) | AC-4, AC-5 | noise exclusion and non-collaborator flags identical on every rendering path; not a scope cut | one shared noise regex list and flagging rule used by helper and jq filter; three-path parity integration test (DESIGN, revisable) | CAP-SHELL, CAP-PY3 | CODING |
| R-3 | REPOSITORY (CLAUDE.md) | AC-6 | no test weakening, no signing in fixtures | disposable fixtures, no commits | CAP-SHELL | CODING |
| R-4 | PLATFORM | AC-1, AC-6 | no network in tests, including existing import fixtures: stub issue counts and every comment-fetch path (gh api, curl fallback); preserve original assertions; record fixture edits as renewed-authority items | stub gh/curl on PATH (feasibility: worktree-run-test.sh:108 stub pattern) | CAP-SHELL | CODING |

All paths (gh/Python, curl/Python, curl/jq) use identical noise classification and non-collaborator flagging; neither behavior may be cut or reduced on the jq path. Integration tests run the same shared comment fixtures through all three paths and assert identical thread content.

Live verification (manual only, not a coding prerequisite): public issue via curl; no credentials needed.

## Verification commands
```
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```
The new suites run by default after being added to `critical-suites.txt` (step 4). Protected verification paths: `scripts/tests/issue-thread-test.py`, `scripts/tests/from-issue-thread-test.sh`, `scripts/tests/critical-suites.txt`.

## Implementation sequence

1. Helper `issue_thread.py` (pure render, noise, quoting, count check, CLI) and its unit test.
   Decisions: D-4..D-7
   Owns: `scripts/lib/issue_thread.py`, `scripts/tests/issue-thread-test.py`
2. Fetch and seed changes in from-issue.sh: REST comment fetch for gh and curl, paginating until exhausted with no page-count cap (D-1, D-2, D-8); curl fallback restarts pagination and replaces any gh results; count check and override retaining only validated pages from the final attempt (D-3); helper call on python path, jq block, `## Thread Review` template section, `Fetched N/M comments` output. Also update existing import fixtures that stub gh/curl so they supply issue counts and every comment-fetch path (including fallback) without network access, preserving original assertions and recording each edit as a renewed-authority item in IMPLEMENTATION_NOTES.md.
   Owns: `scripts/from-issue.sh`
   Depends on: 1
3. **Update existing import fixtures** — Find by grep the existing from-issue test fixtures that stub gh/curl and edit them only to stub the issue comment count and every comment-fetch path (gh api, curl fallback) without network access, preserving their original assertions. Record each edit in IMPLEMENTATION_NOTES.md as a renewed-authority item. Run the existing from-issue suites with curl on PATH replaced by a failing stub to prove they use no network.
   Depends on: 2
4. Integration test with stubs for all paths and docs update.
   Owns: `scripts/tests/from-issue-thread-test.sh`, `GITHUB_INTEGRATION.md`
   Depends on: 2
5. Register suites.
   
   The unit test in step 1 and docs in step 3 can be written in parallel with step 2 since they depend only on the helper contract.
   Owns: `scripts/tests/critical-suites.txt`, `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 4

## Scope cuts under time pressure

Noise exclusion and non-collaborator flagging are mandatory on every rendering path (gh/Python, curl/Python, curl/jq) and cannot be cut. Cut first: docs detail beyond the required thread-reading section. Never cut: count check, curl comments, quoting, noise exclusion, non-collaborator flagging.

## Risks and unresolved questions

- Existing stub gh may answer `gh api` with nothing, which would fall through to real curl or fail the count check: existing fixtures are updated, without network, to stub counts and all fetch paths (R-4), preserving their existing assertions, and renewed authority is recorded where an override applies. The D-8 fallback (restart and replace, no merge) must be exercised by existing suites; run them early. Add a test where gh page 2 fails after page 1 succeeds, to confirm no duplicates, and an override test where the final attempt fails on page 2.
- `gh api --paginate` emits concatenated JSON arrays; helper parses with raw_decode.
- GitHub rate-limit for unauthenticated curl (60/h) may fail large fetches; surfaced via BH-5.
- Existing 'untrusted piped text' handling not located (baseline unknown); plan adds its own neutralization and does not rely on it.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Scope cuts contradicted required noise exclusion and non-collaborator flagging (AC-4, AC-5, BH-3). | Rewrote s20.1 so noise exclusion and non-collaborator flagging are mandatory on every path; updated AC-4/AC-5 tests to cover all paths. |
| AR-002 | Accepted | A fixed 100-page cap contradicts unconditional full-thread import (BH-6); pagination must run until exhausted on both paths. | D-2 now fetches until pagination is exhausted with no page cap; step-2 text and s1 intro updated to match. |
| AR-003 | Accepted | The plan gave later maintainer statements precedence without defining who qualifies; an explicit association mapping removes the trust ambiguity. | AC-2 traceability row and a new rule block in Traceability define OWNER/MEMBER/COLLABORATOR as maintainers; all others flagged non-collaborator. |
| AR-004 | Accepted | Retention across gh failure, curl fallback and override was undefined and could yield duplicate or inconsistent partial seeds. | D-8 and D-3 define restart/replace semantics and validated-page retention under override; step-2 and risk s21.1.i1 updated to match. |
| AR-005 | Accepted | Existing gh stubs may return nothing for gh api, falling through to real curl or failing the count check; fixtures need network-free stubs. | Edit D-8, s8.1 compatibility, R-4 and step-2 to require network-free fixture updates, preserved assertions, and renewed-authority recording. |
| AR-006 | Accepted | Parity of noise exclusion and non-collaborator flags across gh/Python, curl/Python and curl/jq is required by BH-3, AC-4 and AC-5; scope cuts contradicting it are removed. | AC-4/AC-5 rows, s16 note and R-5 restriction make noise exclusion and flags mandatory on every path with a three-path parity test. |
| AR-007 | Accepted | Maintainer precedence needs one explicit association mapping used by rendering, Thread Review instructions, and tests. | Edit D-6 and D-7 to define the OWNER/MEMBER/COLLABORATOR mapping and add it to AC-2's requirement, behaviors and tests. |
| AR-008 | Accepted | The jq path must share noise classification and non-collaborator flagging with Python; allowing cuts makes the BH-3 oracle ambiguous. | Edit AC-4, AC-5 and R-2 to require identical noise and flagging on all paths, and add a Restrictions block banning those cuts and requiring cross-path tests. |
| AR-009 | Accepted | Override after a partial fetch needs a testable output contract so INV-1 holds for fetched comments. | Add decision D-9 defining retention, discard and recording on page failure under override, and add a second-page-failure test to the traceability row for AC-3's behaviors. |
| AR-010 | Accepted | The plan named no association mapping, so flags and maintainer precedence were untestable; one explicit mapping resolves this. | Edited D-6, D-7, and AC-2 and added a mapping block after the decisions in section 1. |
| AR-011 | Accepted | Ordering, tie-breaking, edit handling and ID assignment relative to noise filtering were unspecified, so independent tests could assert different sequences. | Revised D-7 and D-5 with an ordering/ID contract; AC-2 now requires tests for tied timestamps, edits and interleaved noise. |
