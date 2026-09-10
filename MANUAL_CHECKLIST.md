# MANUAL_CHECKLIST.md
Base checks: 8; resolved: 6; added: 4; removed: 0

## Summary

Planned verification against CHANGE_SPEC.md and CHANGE_PLAN.md; no checks executed.
Release completeness remains unverified: IMPLEMENTATION_NOTES.md:25 records STOP-1; `scripts/lib/change-pr.sh:332` lacks description defaults; `uncle_tui.py:1562` lacks length framing.
The supplied diff changes five paths outside C-1–4; reconcile their provenance through MC-009.

## Findings

| Check ID | Priority | Behavior classification | Related behavior | Related invariant | Preconditions | Exclusive resources | Depends on | Exact action | Expected result | Evidence to capture | Actual result | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MC-001 | P0 | MODIFY, ADD | B-2/3; P-6–9; AC-1/3 | I-5/6 | Writable isolated checkout; use AS-3 HandoffTests fixture; write source variants before `h.freeze()` | fixture:handoff | none | Complete issue-origin and Summary-origin fixtures; accept defaults, then repeat with edits. Exercise both supported notes/checklist formats, four entries, controls, whitespace, and summaries of 479/480/481 characters. Repeat with missing, malformed, empty and headings/reference-only sources; try blank then typed answers. Invoke `h.engine("handoff", "\n\n\ny\n")`, then repeat with explicit title/summary/manual answers; inspect returned stdout, `h.calls()` and `h.root / "server.body"`. Use `h.state / "origin"` containing `owner/repo\t42\tgh\n` for issue origin and remove it for Summary origin; set `CHANGE_REQUEST.md` Summary in both. Construct table and section/block variants from CHANGE_PLAN.md:39–41; record absent defaults as unmet requirements, not inapplicability. | Title preserves 72-character shortening/fallback; first three completed-work entries are semicolon-joined; normalized summary ≤480 characters; up to three complete action/outcome pairs; unusable sources require nonempty input; edited values appear in preview and submitted body; consent retained. | Inputs, bound tree ID, prompt/preview transcript, captured PR title/body and calls | | BLOCKED-IMPOSSIBLE |
| MC-002 | P0 | PRESERVE, ADD, SECURITY | B-1/3; P-6/14/19; AC-6 | I-1/6 | Writable audited fixtures with stub publication; AS-3 fixture, `h.freeze()` and `h.engine("handoff", text)` | fixture:handoff | none | Compare 100644/100755 sources with symlinks for each description source; mutate external targets after binding. Separately change audited content while prompt waits, then consent. Include literal shell substitutions and embedded delimiters in source text. Create notes/checklist through `Path.write_text`, `chmod(0o644/0o755)` or `symlink_to` before `h.freeze()`; inspect `h.git("ls-tree", h.journal()["commit_tree"])`. Use the subprocess and prompt pause in `scripts/tests/close-flow-test.sh:1214`; apply external-target mutations after binding and source mutations after the title prompt. Repeat its remote-drift variant at line 1337. | Regular bound blobs supply defaults; external contents never reach preview/body; prompt-time drift prevents publication; text never executes; audit and remote-identity guards remain enforced. | Blob modes/IDs, mutations, preview/body, rejection output, publication-call log, execution sentinel | | BLOCKED-IMPOSSIBLE |
| MC-003 | P0 | PRESERVE, RECOVERY | B-4/7; P-10/12/15; AC-7 | I-2/3 | Writable stubbed fixtures; AS-3 fixture; saved phases produced with `CRASH_GIT`, `LOOKUP_FAIL`, `CREATE_TIMEOUT`, `CREATE_FAIL` in `scripts/tests/close-flow-test.sh:1228–1255` | fixture:handoff | none | Separately decline, send EOF and fail authentication; restart each after correcting the cause. Resume an already-created PR and an uncertain create outcome; change default sources before resuming saved title/body. Invoke `h.engine("handoff", "")`, `h.engine("handoff", "\nSummary\nManual\nn\n")`, and `h.publish(AUTH_RC="1")` separately; retry with `h.publish()`. Use `h.publish(CRASH_GIT="commit-tree")`, `h.publish(CREATE_TIMEOUT="1")`, or `h.publish(CREATE_FAIL="1")` on fresh fixtures, then `h.engine("handoff")`. Save journal title/body before source mutation; record audit rejection and retained saved content before restoring the exact bound bytes and resuming. | Failures stay pending; pending/URL output reflects state; saved title/body retained; created PR is reused; uncertain outcome never triggers blind recreation; issue stays open before merge; journal remains v1. | Prompt/output transcript, before/after journal, PR identifiers and create/close-call counts | | BLOCKED-IMPOSSIBLE |
| MC-004 | P0 | PRESERVE, BOUNDARY | B-5/6; P-13/18; AC-5 | I-4 | Writable no-Git, Git-directory and worktree fixtures; legacy-close cases; `scripts/tests/close-flow-test.sh:new_case`, `setup_audit_stage`, `run_driver_stdin`; AS-3 Git fixture | fixture:handoff | none | Complete each routing fixture; repeat Git completion with WORKFLOW_CLOSE_ISSUE=0 and unattended mode. Exercise legacy close with valid ownership/READY/hash/origin, then invalidate each condition separately. Run `bash -x scripts/tests/close-flow-test.sh` for existing routing/eligibility cases. For Git flag variants, repeat `HandoffTests.test_driver_audit_to_pr_and_rerun` with `WORKFLOW_CLOSE_ISSUE="0"`, then `UNATTENDED="1"` in its driver environment; repeat using the worktree setup in `test_worktree_git_file`. Inspect routing at `scripts/change-workflow.sh:1939` and eligibility at `scripts/lib/issue-close.sh:109`. | No `.git` produces no PR process/dialog; directory and worktree-file Git routes prompt when enabled; disabled/unattended routes do not; legacy close requires every eligibility condition. | Route setup, flags, prompt transcript, PR/close-call logs and eligibility evidence | | BLOCKED-IMPOSSIBLE |
| MC-005 | P1 | MODIFY, REGRESSION | B-2/3; P-11; AC-2 | I-5/6 | Interactive terminal/TUI session; AS-3 fixture; prompt harness `scripts/tests/pr-prompt-test.py:12` | terminal:verification, fixture:prompt | none | In CLI and TUI accept and edit title, summary and manual defaults. Feed Unicode, embedded `]:` and `[y/n]`; split each framed prompt at every boundary, pausing immediately after embedded `]:`. For CLI run `bash -c '. "$1"; change_pr_engine handoff' test "$LIB"` with cwd `h.repo`, environment `h.env` and inherited terminal stdin/stdout. For TUI use `PromptTests.ui`/`detect`, assigning each prefix to `ui.partial` and calling detection three times before the next chunk; exercise both captured prompts and P-11 frames with N=`len(default)`. Exercise keyboard edits in `python3 uncle_tui.py` against the disposable driver fixture. Record missing summary/manual defaults and framing as unmet requirements. | No early dialog; N counts Unicode code points; complete default remains editable; CLI editing and existing prompt handling preserved. | Terminal/platform versions, chunk sequence, dialog timing, full buffers and submitted edits | | BLOCKED-SETUP |
| MC-006 | P0 | PRESERVE, ACCEPTANCE | B-1; AC-4; R-2 | I-3 | Human resolution of R-2; authorized disposable GitHub repository/account and merge permissions | account:github-verification, repo:github-verification | none | After approved contract resolution, create an issue-origin PR, record open issue state, then merge to the default branch and inspect issue events/comments. | Closing reference exists; issue stays open before merge; merge closes issue and produces required post-merge comment. Closure alone does not satisfy retained AR-4. | PR/issue URLs, merge time, closure event, separate comment URL/body/author/time, approved R-2 decision | | BLOCKED-HUMAN |
| MC-007 | P1 | REGRESSION | U-1; P-20; AC-1–3/6/7 | I-1–6 | Writable isolated checkout; Bash/Python execution recorded in BASELINE_REPORT.md §8 | checkout:regression | none | Run `bash scripts/tests/close-flow-test.sh`; `python3 -B scripts/tests/pr-prompt-test.py -q`; `bash -n scripts/change-workflow.sh scripts/from-issue.sh scripts/lib/change-pr.sh scripts/lib/issue-close.sh`; `bash scripts/tests/tui-session-panel-test.sh`. | All exit 0 with no new failures; results cover P-19 and adversarial AR-001/002/004/005, including full-buffer assertions after embedded terminators; baseline fork/identity/drift/worktree/closure guards remain covered. | Full logs, exit codes, test counts and assertion-to-requirement mapping; identify uncovered assertions | | BLOCKED-IMPOSSIBLE |
| MC-008 | P1 | COMPATIBILITY, ROLLBACK | P-10/12/13/16/17; F-2/3 | I-1–4 | Writable isolated prior/current revisions and saved v1 journals; reference HEAD `57312a8a555b2fcfeeef37d3517eeb6e1c5660aa`; candidate is that HEAD plus `.uncle/workflow/change.diff`; provision Bash 3.2/Python 3.9 and record `bash --version`, `python3 --version`, `git rev-parse HEAD`, and diff digest | checkout:rollback | none | Run handoff/recovery on minimum runtimes; resume existing v1 phases. Revert only C-1–4 changes and resume journals again. Compare changed-path inventory against recorded starting changes and F-2/F-3. Use AS-3 and MC-003 with Bash 3.2/Python 3.9 first on candidate, then reference; put those runtimes first on fixture PATH. Establish C-1–4 identity with `git diff HEAD -- scripts/lib/change-pr.sh uncle_tui.py scripts/tests/close-flow-test.sh scripts/tests/pr-prompt-test.py`; if empty, record the requested revert as a no-op, retain compatibility/resume checks, and do not revert unrelated changes. | No migration; saved state remains readable; rollback retains journals/branches/PRs and avoids duplicates; origin TSV/legacy curl and close flag remain compatible; protected paths and unrelated edits unchanged. | Runtime versions, revision IDs, before/after state and remote inventory, transcripts, path inventory | | BLOCKED-IMPOSSIBLE |
| MC-009 | P0 | REGRESSION, BOUNDARY | F-1–3; STOP-1; IMPLEMENTATION_NOTES.md D-1/2, U-4–6 | I-5/6 | Read access to supplied artifacts and candidate; starting diff needed to settle provenance | none | none | Compare `git diff --name-only` and `.uncle/workflow/change.diff:1–76` with CHANGE_PLAN.md:29–32 and IMPLEMENTATION_NOTES.md:35–37; compare the excluded-artifact binary diff digest using CHANGE_TEST_REPORT.md:99's command. Inspect `scripts/lib/change-pr.sh:332–345` and `uncle_tui.py:1562–1579` against P-6–11; account separately for notes/report replacements at IMPLEMENTATION_NOTES.md:5–6. | Every unplanned path has recorded provenance/disposition; preexisting edits remain intact; missing defaults/framing and unresolved STOP-1 block feature acceptance despite baseline test results. | Path/digest comparison, source references, discrepancy disposition and R-2 decision | | BLOCKED-SETUP |
| MC-010 | P1 | MODIFY, REGRESSION | Unplanned error detail; `.uncle/workflow/change.diff:1–14,46–59` | none | Writable disposable adapter fixture from `scripts/tests/agent-codex-test.sh:64–98`; jq | fixture:adapter | none | Run `bash scripts/tests/agent-codex-test.sh`. Using its fake-codex and `run_shim -p` with stdin `p`, vary EMIT_TEXT between error.message, top-level message, multiple error/turn.failed events, missing/null messages, quotes/newlines, and malformed JSON; vary EMIT_COMPLETED=0/1 and FAKE_EXIT=0/7, including a context-length error. Parse the final result with jq and capture process exit. | `scripts/agent-codex.sh:165–199`: failed results retain the last available message or exact fallback `Codex exited without a completed turn`; successful results have null error_detail; one final result, valid JSON, usage, context subtype and exit semantics remain intact. | Input JSONL, final parsed result, exit codes and suite log | | BLOCKED-IMPOSSIBLE |
| MC-011 | P0 | MODIFY, SECURITY, REGRESSION | Unplanned environment isolation; `.uncle/workflow/change.diff:15–45,60–76` | none | Writable scratch directory; source `scripts/lib/green-check.sh`; seven keys from `scripts/lib/parallel_checks.py:85–88` exported with disposable sentinel values; export `VERIFY_KEEP=kept` | fixture:environment | none | Create a command file with two identical Python child commands asserting all seven keys absent from `os.environ` and VERIFY_KEEP retained; create groups file containing `1 2`. Call `green_run "$commands" "$out" "$log"` and then `green_run "$commands" "$out" "$log" "" "$groups"`. Check parent values and sentinel files; repeat with all seven keys initially unset, on minimum runtimes and Git Bash. Run `bash scripts/tests/green-check-test.sh`, `bash scripts/tests/parallel-checks-test.sh` and `bash scripts/tests/verification-integrity-test.sh`. | Both routes remove every listed variable without altering parent/unrelated environment or sentinel files; no env invocation failure; statuses, ordered logs, metrics, protected-input rejection and child cancellation retain their contracts (`green-check.sh:110–162`, `parallel_checks.py:18–157`, `process_tree.py:60–64`). | Child/parent environment assertions, sentinel hashes, platform versions, TSV/logs, metrics and exits | | BLOCKED-IMPOSSIBLE |
| MC-012 | P1 | REGRESSION | CHANGE_TEST_REPORT.md CT-5–7/9–11/15/16/19 | I-1–6 | Writable isolated checkout; platform prerequisites; unresolved lint/type/performance commands and thresholds require recorded disposition under AS-4 | checkout:regression | MC-001, MC-002, MC-003, MC-004, MC-005, MC-006, MC-007, MC-010, MC-011 | Map CT-5 to MC-001/005/007, CT-6 to MC-001/002/005/007, CT-11 to MC-006, CT-16 to MC-002, CT-19 to MC-001–006. For CT-7 execute CHANGE_PLAN.md S-3 using those checks and the platform regression commands in `.github/workflows/installers.yml:67–93`. For CT-9 run `bash -n scripts/agent-codex.sh scripts/lib/green-check.sh scripts/tests/agent-codex-test.sh scripts/tests/green-check-test.sh` and `python3 -B -c 'import ast,pathlib; ast.parse(pathlib.Path("scripts/lib/parallel_checks.py").read_text())'`. For CT-15 run `bash scripts/tests/performance-test.sh`, `bash scripts/tests/background-performance-test.sh`, and `bash scripts/tests/tui-performance-test.sh`; record sequential/parallel elapsed times from MC-011. Resolve AS-4 before claiming CT-9/10/15 coverage complete. | Every NOT RUN item has execution evidence or an explicit remaining blocker; baseline success cannot substitute for missing P-19/framing assertions; syntax checks do not substitute for type checking or linting; performance evidence is evaluated against an approved threshold. | CT-to-check mapping, commands/exits, assertion gaps, timing evidence and unresolved-tool/threshold disposition | | BLOCKED-SETUP |

## Assumptions

| ID | Unverified prerequisite | Settled by |
|---|---|---|
| AS-1 | Current environment is read-only; fixture creation, suite writes and rollback cannot run here. | Move MC-001–004/007/008 to a writable verification environment. |
| AS-2 | Baseline establishes shell/Python test execution, not interactive terminal access or minimum runtime versions. | Provision an interactive verification session for MC-005; record runtime versions for MC-008. |
| AS-3 | Fixture adaptations remain unexecuted; no description-default fixture exists in `scripts/tests/close-flow-test.sh:997–1382`. | In a writable checkout run `python3 -i -c 'from pathlib import Path; import sys; p=Path("scripts/tests/close-flow-test.sh"); s=p.read_text().split("CASE_NAME=pr-handoff\n",1)[1]; s=s[s.index("import hashlib\n"):].split("\nPY\npr_rc=",1)[0]; sys.argv=[str(Path.cwd())]; exec(s.rsplit("unittest.main()",1)[0]); h=HandoffTests(); h.setUp()'`; use a fresh `h` for each case and call `h.doCleanups()` afterward; retain transcripts before cleanup. |
| AS-4 | Broader lint/type commands and a performance acceptance threshold are not supplied in CHANGE_TEST_REPORT.md:38/44/74. | Obtain the repository's applicable commands and approved threshold, execute them under MC-012, or retain those gaps explicitly. |

## Open questions

| ID | Gate decision |
|---|---|
| OQ-1 | CHANGE_PLAN.md R-2/STOP-1 remains unresolved; obtain approved comment lifecycle or revised criterion before accepting AC-4. |
| OQ-2 | AC-1/3/5/6/7 cannot be established through their fixture checks in this read-only environment; change the verification environment. |
| OQ-3 | Required execution fields and coverage exceed the byte budget; mandatory content retained. |
| OQ-4 | Resolve the completion claim against IMPLEMENTATION_NOTES.md:25 and MC-009; missing implementation does not authorize removal of acceptance checks. |

## acceptance-criteria traceability

| Criterion | Checks |
|---|---|
| AC-1 / AR-1 | MC-001, MC-007 |
| AC-2 / AR-2 | MC-005, MC-007 |
| AC-3 / AR-3 | MC-001, MC-007 |
| AC-4 / AR-4 | MC-006; OQ-1 |
| AC-5 / AR-5 | MC-004 |
| AC-6 / AR-6 | MC-002, MC-007 |
| AC-7 / AR-7 | MC-003, MC-007 |

## preserved-behavior coverage

| Behavior | Checks |
|---|---|
| B-1 | MC-002, MC-006 |
| B-4/7 | MC-003 |
| B-5/6 | MC-004 |
| U-1 compatibility/consent | MC-001, MC-008 |
| Adapter result/exit; verification execution | MC-010, MC-011 |

## changed-behavior coverage

| Behavior | Checks |
|---|---|
| MODIFY B-2/3; added defaults/framing P-6–11 | MC-001, MC-002, MC-005 |
| REMOVE | None specified |
| Unplanned error detail/environment filtering | MC-009–011 |

## invariant coverage

| Invariant | Checks |
|---|---|
| I-1 | MC-002 |
| I-2 | MC-003, MC-008 |
| I-3 | MC-003, MC-006 |
| I-4 | MC-004 |
| I-5/6 | MC-001, MC-002, MC-005 |

## regression coverage

| Risk | Checks |
|---|---|
| Adversarial AR-001/002/005 | MC-001, MC-002, MC-007 |
| Adversarial AR-003/004 | MC-005, MC-006, MC-007 |
| Baseline §13; restart and rollback | MC-002–004, MC-007, MC-008 |
| Manual evidence beyond automated coverage | MC-005 terminal interaction; MC-006 live comment/closure; MC-008 rollback/minimum runtimes |
| Scope/provenance; adapter errors; environment isolation | MC-009–011 |
| Every reported NOT RUN; missing assertions/tooling/thresholds | MC-012; AS-4 |

## Removed checks

| Check ID | Reason |
|---|---|
| None | No entire base check is provably inapplicable; MC-008 retains compatibility coverage despite the absent C-1–4 rollback delta. |