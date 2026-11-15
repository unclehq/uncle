# Baseline report (Issue 282)

Omitted sections: Reproduction result (not a bug repro; behavior gap observed by reading code); Existing failures/flaky (driver baseline is authority, none documented in repo for this area)

## 1. Change-request summary
CHANGE_REQUEST.md (Issue 282): `scripts/from-issue.sh` must read the whole issue thread on every fetch path, verify completeness, preserve provenance, treat comments as untrusted, and document it.

## 2. Repository architecture
Shell driver scripts in `scripts/`, Python helpers in `scripts/lib/`, suites in `scripts/tests/` (`*-test.sh`, `*-test.py`), critical tier listed in `scripts/tests/critical-suites.txt`. Runners: `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh`.

## 3. Relevant code paths
- `scripts/from-issue.sh:613-615` `fetch_with_gh`: `gh issue view --json title,body,url,state,labels,comments`.
- `scripts/from-issue.sh:617-620` `fetch_with_curl`: only `GET /repos/o/r/issues/N`; no comments endpoint, no pagination.
- `scripts/from-issue.sh:622-639` fetch selection (`USED_GH`), failure exit.
- `scripts/from-issue.sh:641-668` parsing: python path appends `### Comment from <author>` per comment (lines 644-658); jq path extracts only `.body` (660-663).
- `scripts/from-issue.sh:802-813` attachment freeze applied to `$BODY` (comments are inside BODY on python path).
- `scripts/from-issue.sh:824-882` `write_change_request` heredoc places `$BODY` under `## Motivation`.
- `scripts/from-issue.sh:734` `fetch_kind` passed to `change_pr_engine`.
- Docs: `GITHUB_INTEGRATION.md` "Import an issue" (lines 11-15) says only title and body.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Import issue via authenticated gh, python3 present | Body + each non-empty comment appended as `### Comment from <login>` under Motivation | from-issue.sh:644-658 | Yes (content), format may change |
| B-2 | Import via curl fallback | Comments silently absent | from-issue.sh:617-620 | No (defect) |
| B-3 | Import with jq only | Body only, comments absent | from-issue.sh:660-663 | No (defect) |
| B-4 | Fetch failure on all paths | Prints failure, exit 1 | from-issue.sh:636-640 | Yes |
| B-5 | Empty title | Exit 1 with rate-limit hint | from-issue.sh:670-673 | Yes |
| B-6 | Change request written | Header has `Issue N` and `Seeded from [o/r#N](url)`; fixed section skeleton | from-issue.sh:824-882 | Yes |
| B-7 | Neither python3 nor jq | Exit 1 | from-issue.sh:665-668 | Yes |
| B-8 | gh succeeded | `USED_GH=1` (gates later issue close/PR flow) | from-issue.sh:626-631 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Issue metadata header (`Issue N`, seed URL) is first and parseable | heredoc 835-839 | worktree-run-test.sh, others (grep from-issue.sh) | Medium |
| I-2 | Attachment freeze runs on body text before seeding | 802-813 | not confirmed | Low |
| I-3 | gh-fetched issue sets USED_GH only on non-empty output | 626-631 | worktree-run-test.sh stub gh | Medium |

## 6. Current contracts
CLI: `from-issue.sh` args unchanged by baseline. Output file `.uncle/docs/CHANGE_REQUEST.md` (or root override via `generated_input_path`). gh stub in tests answers `issue view` and label lookup only (worktree-run-test.sh:108).

## 7. Existing automated-test coverage
No suite targets comment handling. Suites invoking from-issue.sh: install-safety-test.sh, pr-auto-publish-test.sh, worktree-run-test.sh, plus several `*-test.py` (headless-run, home-actions, repl-session, implementation-completion, gitignore-post-push). Shell and Python runners use separate temp dirs and no shared ports, so they run as one parallel group (`1 2`).

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CLAUDE.md/driver guidance). No results produced here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout. Parallel group: `1 2`.

## 12. Likely change surface
`scripts/from-issue.sh` (fetch + parse + seed template), new `scripts/lib/issue_thread.py`, `GITHUB_INTEGRATION.md`, new tests, `critical-suites.txt`.

## 13. Regression-sensitive components
Tests that stub `gh` for from-issue.sh (worktree-run-test.sh stub only handles `issue view` and label lookups: any new `gh api` call must tolerate a stub that returns nothing/fails without breaking those suites); attachment freezer; branch-name derivation using TITLE.

## 14. Outside the change
PR publishing, issue closing, mode detection, workflow drivers, new-application brief (`write_new_project_brief`) beyond sharing BODY.

## 15. Unknowns and assumptions
- The 'existing handling for untrusted piped text' referenced in the request was not located in from-issue.sh; assumed to be elsewhere; the plan adds its own neutralization for comments.
- Unknown whether other suites assert exact `### Comment from` text (to be grepped at implementation).

## 16. Initial risk
Medium: stubbed gh in existing suites may break if new gh calls fail hard; mitigated by treating comment-fetch failure on a stub as explicit, tested behavior.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

