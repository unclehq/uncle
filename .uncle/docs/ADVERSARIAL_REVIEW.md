## AR-001: Blocking decision (a) external release repo vs (b) hand-off only is unresolved, so AC-1..AC-6 cannot be verified in-repo

- Severity: HIGH
- References: CHANGE_PLAN intro 'BLOCKING PLANNING DECISION'; Restrictions feasibility says CAP-RELEASE-EDIT unavailable.
- Failure: Blocking decision (a) external release repo vs (b) hand-off only is unresolved, so AC-1..AC-6 cannot be verified in-repo. Say: 'Approval selects (b): the deliverable is IMPLEMENTATION_NOTES.md only, and AC-1..AC-6 are recorded BLOCKED-SETUP, not PASS, until the release repo is supplied.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The plan does not say what steps 2 and 3 do when access is absent; its status vocabulary is only PASS/BLOCKED-SETUP, and

- Severity: HIGH
- References: Implementation sequence steps 2-3; 'Missing live access does not block step 1'; CLAUDE.md completion rule.
- Failure: The plan does not say what steps 2 and 3 do when access is absent; its status vocabulary is only PASS/BLOCKED-SETUP, and absent host access may be BLOCKED-IMPOSSIBLE. Say: 'Without release repo or host access, steps 2 and 3 record BLOCKED-SETUP naming the access needed, and the change is not declared complete.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The expire POST grant has no decision rule for 'script ends links early'.

- Severity: MEDIUM
- References: CHANGE_SPEC section 15 'unknown'; plan step 1 and scope cuts; AC-6.
- Failure: The expire POST grant has no decision rule for 'script ends links early'. Step 1 writes it into the notes while it is also conditional. Say: 'Add the expire POST grant only if the script calls the Daytona expire endpoint; otherwise record it as not added.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The expiresInSeconds action is unspecified when the value is missing, exactly 3600, or above 3600.

- Severity: MEDIUM
- References: CHANGE_PLAN section 4 'missing or > 3600'; SI-2; AC-6.
- Failure: The expiresInSeconds action is unspecified when the value is missing, exactly 3600, or above 3600. Say: 'If absent set 3600; if above 3600 lower to 3600; if 3600 or less leave unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: LV-3 has no procedure or pass criterion, and the spec's 'require_approval false or omitted' conflicts with the plan's ex

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 'false or omitted' vs plan entry; Manual verification LV-3; AC-4.
- Failure: LV-3 has no procedure or pass criterion, and the spec's 'require_approval false or omitted' conflicts with the plan's explicit false. Say: 'The entry sets require_approval explicitly to false; LV-3 passes only if a pre-existing hire installs with zero approval prompts.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: AC-5 'no existing grant removed or altered' has no stated baseline, and the diff is in an external repo that the in-repo

- Severity: LOW
- References: Traceability AC-5 'Diff review'; plan section 5.
- Failure: AC-5 'no existing grant removed or altered' has no stated baseline, and the diff is in an external repo that the in-repo notes cannot prove. Say: 'The notes record the pre-change and post-change grant lists from the release repo.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan has no defined regression check for existing Daytona grants (SB-4/AC-5) since the release definition is external an

- Severity: HIGH
- References: CHANGE_PLAN traceability AC-5 -> 'Diff review' with automated test None; no artifact path is named for the diff.
- Failure: Plan has no defined regression check for existing Daytona grants (SB-4/AC-5) since the release definition is external and in-repo suites cannot see it. Decision: AC-5 is verified by a recorded before/after diff of the full grant list saved under .uncle/docs/, and a missing diff means AC-5 is NOT RUN, not PASS.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan says 'in-repo suites must match baseline' as the regression check, yet also says a green in-repo suite is not evide

- Severity: HIGH
- References: CHANGE_PLAN sections 16-17 vs Risks 'A green in-repo suite is not evidence for this change'.
- Failure: Plan says 'in-repo suites must match baseline' as the regression check, yet also says a green in-repo suite is not evidence. The two statements make the regression gate vacuous. Decision: in-repo suite parity is only a no-source-change guard and never counts toward AC-1..AC-6.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Step 3 allows recording LV-1..LV-3 as BLOCKED-SETUP, but the checks have no stated classification when host access is mi

- Severity: MEDIUM
- References: CHANGE_PLAN step 3 'PASS/BLOCKED-SETUP'; section 18 classification LIVE_VERIFICATION; CHANGE_SPEC SB-3.
- Failure: Step 3 allows recording LV-1..LV-3 as BLOCKED-SETUP, but the checks have no stated classification when host access is missing. LV-3 (existing hire installs without approval) is the main compatibility regression guard. Decision: if host access is missing, LV-1..LV-3 are BLOCKED-SETUP, naming the action required, and the change is not complete.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The conditional expire POST has no decision rule.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6 and section 15 'unknown'; CHANGE_PLAN R-2 'Conditional entry'.
- Failure: The conditional expire POST has no decision rule. 'If and only if the script ends links early' is unresolved, so AC-6 passes or fails depending on how it is read, and a missing grant would regress link expiry. Decision: step 2 must grep the script for the expire call and record the finding. The expire entry is added if the call exists and omitted otherwise.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The plan does not state the outcome when a script's expiresInSeconds is absent or above 3600.

- Severity: MEDIUM
- References: CHANGE_PLAN section 4 'build script only if expiresInSeconds is missing or > 3600'; R-3 CAP-SCRIPT-EDIT.
- Failure: The plan does not state the outcome when a script's expiresInSeconds is absent or above 3600. Both the script edit and the 3600 limit are listed as 'Never cut', but the script change is not in scope for any in-repo owner. Decision: a missing or over-limit value is edited to 3600 in the external script, and if that edit is not permitted, AC-6 is reported FAIL.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Steps 2 and 3 both Own IMPLEMENTATION_NOTES.md with Depends on, but step 2 is 'if access is granted' with no defined beh

- Severity: LOW
- References: CHANGE_PLAN Implementation sequence steps 2-3.
- Failure: Steps 2 and 3 both Own IMPLEMENTATION_NOTES.md with Depends on, but step 2 is 'if access is granted' with no defined behavior when it is skipped. Decision: when step 2 is skipped, the notes record 'step 2 not performed: no release repo access', and step 3 is BLOCKED-SETUP.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The grant path uses unconstrained {sandboxId}/{port} placeholders, so it covers every sandbox and port the host key reac

- Severity: HIGH
- References: CHANGE_PLAN s1.2 path '/sandbox/{sandboxId}/ports/{port}/signed-preview-url'; CHANGE_SPEC AC-1 has no sandbox or port restriction.
- Failure: The grant path uses unconstrained {sandboxId}/{port} placeholders, so it covers every sandbox and port the host key reaches. Plan should say: the grant stays a templated path, the script requests links only for its own sandbox, and diff review confirms no wider wildcard.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: SI-2 (expiresInSeconds <= 3600) is enforced only by the external, unverified build script.

- Severity: HIGH
- References: CHANGE_PLAN R-3 'Inspect script' (CAP-SCRIPT-EDIT); CHANGE_SPEC SI-2 enforcement point is Script.
- Failure: SI-2 (expiresInSeconds <= 3600) is enforced only by the external, unverified build script. The plan does not say what happens if the field is omitted. Plan should say: expiresInSeconds must be set explicitly in the call; a script that omits it fails AC-6.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The signed link is a bearer credential, and with require_approval false no human sees it before it is printed.

- Severity: MEDIUM
- References: CHANGE_PLAN s11 saves 'publish output saved under .uncle/docs/'; AC-3 requires a Preview: line; no redaction rule.
- Failure: The signed link is a bearer credential, and with require_approval false no human sees it before it is printed. The plan sets no rules for where it may be recorded. Plan should say: the URL appears only in build output, is never written to .uncle/docs or notes, and live-check evidence redacts the token.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The conditional expire-POST grant is a state-changing write with require_approval false, and its trigger 'script ends li

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6 and s15 'Whether the script ends links early is unknown'; CHANGE_PLAN R-2.
- Failure: The conditional expire-POST grant is a state-changing write with require_approval false, and its trigger 'script ends links early' is undefined. Plan should say: add it only if the script source contains an explicit expire call, scoped to the same path template, with the grep result recorded in the notes.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: AC-4 (no approval prompt) sits beside the spec's note that the host supports approval only for mail on the script surfac

- Severity: MEDIUM
- References: CHANGE_SPEC s10 'host supports approval only for mail on script surface' versus AC-4 and SB-3.
- Failure: AC-4 (no approval prompt) sits beside the spec's note that the host supports approval only for mail on the script surface, so the new grant cannot be gated. Plan should say: the grant is accepted as ungated, and reviewer sign-off on the diff stands in for the host approval gate.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan has no pass/fail evidence for AC-1 and AC-5 when the release repo is inaccessible, because the only diff to ins

- Severity: HIGH
- References: CHANGE_PLAN Traceability lists 'Diff review'/'Script review' for AC-1/5/6; Restrictions says CAP-RELEASE-EDIT is unavailable in this checkout.
- Failure: The plan has no pass/fail evidence for AC-1 and AC-5 when the release repo is inaccessible, because the only diff to inspect is external. Plan should say: 'If the release definition is not accessible, AC-1, AC-5 and AC-6 are recorded BLOCKED-SETUP (not PASS), and IMPLEMENTATION_NOTES.md is not evidence for them.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The plan says it is 'executable only as (b)' but also keeps steps 2 and 3 that require external access.

- Severity: HIGH
- References: CHANGE_PLAN intro BLOCKING PLANNING DECISION versus Implementation sequence steps 2-3 and Restrictions feasibility note.
- Failure: The plan says it is 'executable only as (b)' but also keeps steps 2 and 3 that require external access. Plan should say: 'Steps 2 and 3 are BLOCKED-SETUP unless the operator supplies the release repo path; the in-repo deliverable is complete when step 1 exists.' The condition for step 1 alone being sufficient is undefined.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The expire-POST condition 'if and only if the script ends links early' has no objective test.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6, SB-5 and Assumptions ('whether the script ends links early is unknown'); CHANGE_PLAN R-2.
- Failure: The expire-POST condition 'if and only if the script ends links early' has no objective test. Plan should say: 'The script ends links early iff it contains a call to the Daytona signed-preview-url expire endpoint; grep for that call decides it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: AC-3's 'small web app' and AC-4's 'existing hire' are unspecified, so the live checks cannot be repeated or compared.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 and AC-4; CHANGE_PLAN section 18 LV-2 and LV-3.
- Failure: AC-3's 'small web app' and AC-4's 'existing hire' are unspecified, so the live checks cannot be repeated or compared. Plan should say which app and hire to use, or that the executor records which it picked.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The scripts' behavior is unspecified when the signed link is returned with expiresInSeconds above 3600 or is refused, so

- Severity: MEDIUM
- References: CHANGE_SPEC SI-2 and Failure behavior cover only the publish refusal; CHANGE_PLAN Error and recovery.
- Failure: The scripts' behavior is unspecified when the signed link is returned with expiresInSeconds above 3600 or is refused, so SI-2's failure path has no expected output. Plan should say: 'If the host refuses or returns no link, the build prints no Preview: line and exits normally.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
