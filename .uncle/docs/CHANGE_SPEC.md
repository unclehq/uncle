# Change spec (Issue 282)

Omitted sections: Performance (negligible, 1 request per 100 comments); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Feature + bug fix (silent comment loss on curl/jq paths).

## 2. Problem statement
Issue import drops or cannot validate comments on some paths, and treats the thread as flat text.

## 3. Current behavior
See baseline B-1..B-3.

## 4. Desired behavior
All three paths (gh, curl, jq) include the full thread with provenance; completeness is verified against the issue's comment count; noise comments are kept out of requirement text; comment text is neutralized as untrusted data; the agent is told how to reconcile contradictions.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | MODIFY | Import with gh | Comments appended w/o link | Each comment listed with author, URL, timestamps, edited marker, author association | shell test gh path |
| BH-2 | ADD | Import via curl | Comments dropped | Comments fetched from `issues/N/comments`, paginated | shell test curl path |
| BH-3 | ADD | Import via jq (no python3) | Comments dropped | Same thread content as python path | shell test jq path |
| BH-4 | ADD | Fetched comments != issue `comments` count | No check | Exit 1 with message naming both counts; `UNCLE_ISSUE_ALLOW_INCOMPLETE=1` downgrades to warning recorded in the change request | shell test |
| BH-5 | ADD | Comment fetch fails/unavailable | Silent | Exit 1 saying comments could not be fetched (same override as BH-4) | shell test |
| BH-6 | ADD | Thread over 100 comments | Not handled | All pages fetched | shell test with 2 pages |
| BH-7 | ADD | Noise-only comment (`+1`, `bump`, emoji-only, `thanks`) | Included | Listed under `### Excluded as noise` by link only; absent from thread text | python unit test |
| BH-8 | ADD | Comment edited (updated_at != created_at) | Not shown | Marked `edited <ts>`; text is the current text | unit test |
| BH-9 | ADD | Contradicting/superseding comments | Not handled | CHANGE_REQUEST includes `## Thread Review` section instructing the analyst to follow later maintainer statements, record conflicts, and cite source IDs (`body`, `comment-N`) per requirement | shell test checks section present; manual |
| BH-10 | ADD | Comment contains headings or agent instructions | Raw text injected into the document | Comment text quoted line-by-line (`> `) inside a labelled untrusted block; cannot create sections; preamble states the thread is data and cannot override Uncle rules or gates | unit + shell test |
| BH-11 | ADD | Non-collaborator comment | Not distinguished | Flagged with `author_association` (e.g. NONE) and `[non-collaborator]`; included | unit test |
| BH-12 | PRESERVE | Import of issue with no comments | Body only | Same body; thread section states 0 comments | shell test |
| BH-13 | PRESERVE | Fetch failure / empty title / header format | See B-4..B-7 | Unchanged | existing suites |
| BH-14 | ADD | Docs | Say title and body | GITHUB_INTEGRATION.md states whole thread is read, fetch checked, flags | grep test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | NEW | No comment present in the fetched set is silently omitted from the seed (except listed noise, which is listed by link) | from-issue.sh | issue_thread.py render | unit |
| INV-2 | NEW | Seeding never proceeds when comment fetch is short or failed, unless explicit override, which is recorded in the document | from-issue.sh | completeness check | shell |
| INV-3 | NEW | Comment text cannot introduce a document heading or leave the untrusted block | CHANGE_REQUEST.md | quoting in render | unit |
| INV-4 | EXISTING | Header `Issue N` / `Seeded from` unchanged | CHANGE_REQUEST.md | heredoc | existing suites |
| INV-5 | EXISTING | No approval gate or rule is altered by thread content | driver | no code path consumes comment text as config | shell test (injection comment) |
| (none RELAXED or REMOVED) | | | | | |

## 7. Compatibility
Output remains Markdown; thread now under `## Motivation` as subsection `### Issue thread`. The old `### Comment from <login>` headings are replaced; any suite asserting them must be updated only if it fails (to be grepped).

## 8. Error behavior
As BH-4/BH-5. Message names the endpoint/path and the override variable.

## 10. Security
Comments are untrusted data (INV-3, INV-5); author and association recorded; no comment text is passed to a shell or eval.

## 12. Rollback
Revert the commit; the helper is additive.

## 14. Non-goals
Summarizing long threads; re-fetching mid-run; excluding non-collaborators; reactions; resolving contradictions automatically in code; PR/close flows.

## 15. Assumptions and resolved open questions
- Q1 non-collaborators: included and flagged (decision).
- Q2 long threads: never summarized; full text kept (faithfulness over size).
- Q3 mid-run changes: not re-fetched; document records fetch time and comment count so staleness is visible.
- Supersession and noise judgment beyond the regex noise list is performed by the analyst agent from the instructions in `## Thread Review`; code only provides provenance and structure.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A clarifying comment appears in the seeded CHANGE_REQUEST.md with author, comment URL and timestamps on the gh, curl and jq paths. | from-issue-thread-test.sh runs from-issue.sh with stub gh/curl/python-less PATH and greps the output |
| AC-2 | The seed contains a Thread Review section instructing that a later maintainer statement wins on contradiction, that the conflict is recorded, and that each requirement cites body or comment id and link; comments are listed in chronological order with stable ids. | shell test greps section; unit test checks ids/order |
| AC-3 | A thread of more than 100 comments (two API pages) is fully included on curl and gh paths; a fetched count below the issue's comment count or a failed comment fetch exits non-zero unless UNCLE_ISSUE_ALLOW_INCOMPLETE=1, in which case a warning is printed and recorded in the document. | shell test with 2-page stub, short fetch, failing fetch, override |
| AC-4 | Noise-only comments (+1, bump, thanks, emoji-only) are not in the thread text and are listed only as links under Excluded as noise; comments with substantive text are never classed as noise. | issue-thread-test.py table of examples incl. negatives like '+1 but also please support X' |
| AC-5 | Comment text containing headings, fences or agent instructions is rendered as quoted untrusted data and does not create document sections; the preamble states the thread cannot override Uncle rules or approval gates; edited comments are marked and carry current text; non-collaborators are flagged. | issue-thread-test.py and shell test with an injection comment |
| AC-6 | Issue with zero comments seeds as before (body unchanged, header unchanged) and existing suites invoking from-issue.sh still pass. | shell test plus bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh |
| AC-7 | GITHUB_INTEGRATION.md documents that the whole thread is read, the completeness check and override, non-collaborator flagging, and that later comments are not re-fetched. | grep in from-issue-thread-test.sh |

