# Change Plan

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
|AR-001|Accepted|Completion must publish audited edits; supersedes CHANGE_SPEC.md §15 branch/push exclusion.|§4,7,12,16,21; Frozen change scope; Exact acceptance criteria|
|AR-002|Accepted|Audit hash alone does not bind code.|§7,9,11,16; Exact acceptance criteria|
|AR-003|Accepted|Recovery requires identity; supersedes CHANGE_SPEC.md §13 persistence and §15 reuse exclusions.|§2,3,7,9,12–14,16,21–22; Exact acceptance criteria|
|AR-004|Accepted|Repository and fork head must be explicit.|§8,16,18; Exact acceptance criteria|
|AR-005|Accepted|Fixtures must model current per-finding acceptance.|§4,16–17,20,22; Pre-implementation checks; Post-implementation checks|

Omitted sections: none

## 1. Selected technical approach
All actions are planned. COMPLETE creates PRs when `.git` exists (file/directory); otherwise retain closing.

## 2. Alternative approaches considered

|ID|Alternative|Rejection|
|---|---|---|
|A-1|Wrapper PR|Misses direct runs|
|A-2|Terminal PR failure|AR-003 requires journal/reconciliation|

## 3. Why the selected approach is preferred
Single creator/reconciler in P-5; no wrapper retry.

## 4. Exact components to modify
P-1: scripts/change-workflow.sh; P-2: scripts/from-issue.sh; P-3: scripts/lib/issue-close.sh; P-4: uncle_tui.py.

|Component|Planned change|Reason|Regression risk|Test coverage|
|---|---|---|---|---|
|P-1|Audit snapshot; COMPLETE handoff/recovery|B-1; AR-001–003|Eligibility|T-1,3,5–7|
|P-2|Skip Git fallback; message|I-6|Early close|T-1,2|
|P-3|Extract eligibility gate|I-1|Gate drift|T-2|
|P-4|Parse title default|B-3|Other prompts|T-4|
|P-5: scripts/lib/change-pr.sh (new)|Commit/publish; bind/reconcile/create PR|B-4; AR-001–004|Wrong tree/repo|T-1,3,5–8|
|P-6: scripts/tests/close-flow-test.sh|Repair audit fixtures; PR/recovery cases|AC-1–6; AR-005|Leakage|T-1–3,5–9|
|P-7: scripts/tests/pr-prompt-test.py (new)|Prompt tests|AC-3|Low|T-4|
|P-8: scripts/README.md:210–247|Routing/recovery|Compatibility|Low|M-1|

## 5. Components explicitly not to modify
Preserve scripts/stagegate.sh, audit classification, project roots and approved inputs.

## 6. Data-flow changes
P-5: normalize CHANGE_REQUEST.md Summary whitespace/controls; cap at 72 chars; fallback “Completed change”.
P-5: prompt for nonempty summary/manual-check lines; body includes both and `Closes owner/repo#issue` for gated origins.

## 7. State-transition changes
PR attempts preserve COMPLETE/issue-closed. Originless PRs require owned READY/hash; issue PRs reuse P-3 gate.
P-1/P-5: before FINAL_AUDIT, freeze HEAD, branch, and tracked/nonignored untracked contents/modes via a temporary Git index; exclude only .uncle/workflow/ and FINAL_AUDIT.md.
Bind the resulting tree to the verdict hash, origin and PR owner; include FINAL_AUDIT.md by its recorded hash in the expected commit tree.
Reject source/HEAD changes during audit; after acceptance allow only the recorded handoff commit/branch transition.
Retain effective READY from per-finding acceptance (P-1:WAIT_AUDIT_OVERRIDE); never promote UNKNOWN or retained blockers.

## 8. Interface and API changes
Emit unterminated `PR title [default: <title>]: `; prefill TUI/Python readline; blank accepts default.
P-5: resolve base repository from gh origin, or confirm it for originless runs; query its default branch and validate head remote ownership/branch.
Call `gh pr create --repo <base-owner/repo> --head <head-owner:branch> --base <default-branch> --title <title> --body-file <temp>` quoted; delete temp on exit.
Reject ambiguous remotes, unsupported fork selectors or remote SHA mismatch; never infer head from branch name alone.

## 9. Schema or persistence changes
P-5: atomically journal version, PR owner token, origin, audit hash, reviewed/commit tree IDs, original/intended HEAD, base/head repositories, branches, phase and PR URL/number under .uncle/workflow/pr/.
Generate PR ownership before audit even without STAGEGATE_RUN_ID; resume only matching journal/verdict/origin/tree; preserve existing close ownership/sentinel semantics.
Persist intent before commit/push/create; phases prepared/published/creating/created/unknown support crash reconciliation; missing/corrupt binding requires fresh audit.

## 10. Compatibility strategy
Retain Bash 3.2/prompts/B-6/B-8; exclude curl/legacy PRs.

## 11. Concurrency implications
Hold P-1 acquire_lock through PR; worktrees independent.
P-5: after prompts, recheck origin/verdict/tree, local HEAD/branch and remote SHA immediately before creation; reject drift.
Recheck returned PR head SHA; diagnose later drift and require re-audit, without closing/deleting the PR.

## 12. Error and recovery behavior
Auth/EOF/gh failure: diagnose, preserve issue/COMPLETE, return success with pending PR outcome; resume P-5 on rerun.
P-5: show exact audited file list/diff and target; obtain commit/publish consent; from default branch create a unique feature branch, commit exactly the expected tree, push without force.
Never include unrelated preexisting edits without that review; reject tree drift and rerun audit; never reset/stash user changes.
On resume reconcile local commit and remote SHA before repeating mutations.
Before every create/retry query PRs across open/closed/merged states by exact base/head identity and SHA: one match records URL; multiple matches stop.
After create timeout record unknown; reconcile only, never recreate on an empty/failed lookup until the prior outcome is independently resolved.
Reuse P-3 gh timeout/fallback.

## 13. Migration plan
New PR journal only; legacy COMPLETE without binding requires fresh audit before PR recovery.

## 14. Rollback plan
Revert P-1–P-8; inspect PRs before old COMPLETE closes immediately; retain PRs/state and ignore the PR journal.

## 15. Feature-flag or containment strategy
Disable PRs/prompts for WORKFLOW_CLOSE_ISSUE=0 or unattended.

## 16. Automated-test strategy
CHANGE_SPEC.md IDs; T-1–3,5–9: P-6; T-4: P-7.

|Requirement|Behavior|Invariant|Component|Automated test|Manual check|
|---|---|---|---|---|---|
|AC-1,4|B-1,4,5|I-6,7|P-1,2,5|T-1: one PR/body; zero closes/markers|M-1|
|AC-2,5,6|B-2,6,8|I-1–3,5|P-1–3|T-2: corrected close suite|M-2|
|AC-3|B-3|I-5|P-4,5|T-4: prefill/edit/Unicode/chunks; generic prompts|M-1|
|§7,8|B-7|I-4,5|P-1,5|T-3: originless/worktree/disabled/unattended/EOF/auth/error/lock|M-2|
|AR-001|B-1|I-6|P-1,5|T-5: default-branch edit/audit→consented commit/push/PR; declined handoff resumes|M-1|
|AR-002|B-1|I-1,6|P-1,5|T-6: change branch/code/remote after audit and during prompt; unchanged audit hash still rejects|M-1|
|AR-003|B-1|I-3,6|P-1,5|T-7: no-run-ID failure/recovery; crash at each phase; server success/timeout; successful rerun gives one PR|M-1|
|AR-004|B-1,5|I-6|P-5|T-8: upstream/fork same branch name, different SHA; assert --repo/head/base and PR SHA|M-1|
|AR-005|B-2|I-1–3|P-1,3,6|T-9: EOF/retained blockers deny; accepted findings yield READY and gated close/PR; UNKNOWN denies|M-2|

## 17. Regression-test strategy
T-1: fail before, pass after.
Run `env -u UNCLE_PROJECT_ROOT bash scripts/tests/close-flow-test.sh`; `python3 scripts/tests/pr-prompt-test.py`.
Run `python3 scripts/tests/audit-findings-test.py`; `bash scripts/tests/audit-verdict-test.sh`; `bash scripts/tests/issue-project-root-test.sh`; `bash scripts/tests/unattended-test.sh`; `python3 scripts/tests/tui-support-test.py`.
Keep gate/retry assertions; supply timeout/gtimeout.

## 18. Manual-verification strategy

|ID|Planned check|
|---|---|
|M-1|Disposable upstream/fork: T-5–8; CLI/TUI title/body; default-branch merge closes issue|
|M-2|No-git/worktree: routing, failures, project roots|

## 19. Observability changes
Print PR URL or skip/failure reason.

## 20. Implementation sequence

|ID|Planned step|
|---|---|
|S-1|Repair P-6: copy scripts/lib/audit-findings.py, emit blocking finding tables, replace obsolete override assertions with T-9; pass baseline before extraction; add PR tests failing T-1|
|S-2|Extract P-3 gate; add P-5, audit binding, handoff/recovery and routing|
|S-3|Update P-4/P-8|
|S-4|Run §17/M-1/M-2|

## 21. Scope cuts under time pressure
Defer cancellation/PR editing; keep handoff, recovery and AC tests.

## 22. Risks and unresolved questions

|ID|Disposition|
|---|---|
|R-1|ASSUMPTION: merge closes linked issue; settle via M-1|
|R-2|Unknown remote outcome blocks recreation pending reconciliation (§12)|
|R-3|AR-005: scripts/tests/close-flow-test.sh:new_case omits audit-findings.py; setup_audit_stage omits blockers; repair via S-1/T-9|
|R-4|Budget exception: preserved sections plus mandatory dispositions, acceptance rows and execution contract exceed 4092 bytes/123 lines; retained per output-budget rule.|

## Frozen change scope

|ID|Planned boundary|
|---|---|
|FS-1|Implement P-1–8 and T-1–9; AR-001/003 narrowly supersede CHANGE_SPEC.md §13/15 for audited publication and recovery.|
|FS-2|No automatic merge, force-push, cancellation, unrelated PR editing or close-gate relaxation.|

## Files expected to change

|ID|Allowed implementation files|
|---|---|
|FC-1|scripts/change-workflow.sh|
|FC-2|scripts/from-issue.sh|
|FC-3|scripts/lib/issue-close.sh|
|FC-4|scripts/lib/change-pr.sh (new)|
|FC-5|uncle_tui.py|
|FC-6|scripts/tests/close-flow-test.sh|
|FC-7|scripts/tests/pr-prompt-test.py (new)|
|FC-8|scripts/README.md|

## Files that must not change

|ID|Protected paths|
|---|---|
|NC-1|Source paths outside FC-1–8, including scripts/stagegate.sh, scripts/lib/audit-findings.py, scripts/lib/self_hosted.py and scripts/tests/self-hosted-test.py.|
|NC-2|Approved inputs, including CHANGE_SPEC.md and ADVERSARIAL_REVIEW.md; preserve existing user edits in uncle_tui.py.|

## Expected behavioral differences

|ID|Planned difference|
|---|---|
|BD-1|Git COMPLETE enters reviewed commit/publish/PR handoff with resumable outcomes (§7–12).|
|BD-2|PR creation requires exact audited tree and repository/head binding (T-6,8).|

## Expected unchanged behavior

|ID|Required preservation|
|---|---|
|UB-1|CHANGE_SPEC.md B-2,6–8 and I-1–6; close ownership remains unchanged.|
|UB-2|P-1:WAIT_AUDIT_OVERRIDE retains per-finding effective READY semantics; T-9 verifies them.|

## Exact acceptance criteria

|ID|Required result|
|---|---|
|AC-1|T-1,5: one PR containing audited source/audit edits and summary/manual steps.|
|AC-2|T-2: no Git means no PR/prompt and existing immediate-close behavior.|
|AC-3|T-4: shortened editable default; blank accepts; Unicode/chunked input and generic prompts pass.|
|AC-4|T-1/M-1: qualified closing keyword; creation never closes/marks; default-branch merge closes source issue.|
|AC-5|T-2,9: existing run/origin/hash/READY, fetch and duplicate-close gates pass.|
|AC-6|T-2: driver close failure remains successful/retryable; wrapper failure exits 1.|
|AC-7|T-6: all drift cases deny creation despite unchanged audit hash.|
|AC-8|T-7: recovery without injected run ID and timeout/rerun sequences yield one discoverable PR; unresolved outcome never recreates.|
|AC-9|T-8: base repository and fork head SHA match selected identities.|
|AC-10|T-3: originless/worktree/kill-switch/unattended/EOF/auth/error/lock cases preserve state and issue.|

## Pre-implementation checks

|ID|Planned check|
|---|---|
|PRE-1|Record `git status --short`; preserve preexisting edits; read P-1–4 and scripts/lib/audit-findings.py.|
|PRE-2|Run existing §17 tests before edits; repair only explained audit fixtures via S-1; require corrected close baseline green before gate extraction.|

## Post-implementation checks

|ID|Planned check|
|---|---|
|POST-1|Run §17/T-1–9 and M-1–2; report command statuses and PR identities; unrun manual checks remain unverified.|
|POST-2|Run `git diff --check`; inspect `git diff --name-only` against FC/NC and preexisting edits.|

## First features to cut if time expires

|ID|Cut|
|---|---|
|CUT-1|Optional prompt polish beyond AC-3; never cut AC-1–10 or identity/recovery checks.|

## Conditions that require stopping implementation

|ID|Stop condition|
|---|---|
|STOP-1|Unexplained baseline failure, required protected-file edit, or inability to bind reviewed files to published SHA.|
|STOP-2|Recovery needs close-gate relaxation, destructive Git actions or duplicate-risk retries.|
