#!/usr/bin/env bash
# The layout a stage document must be written in, stated to the agent that
# writes it.
#
# Every artifact here is read back by a parser. Until now those parsers were the
# only statement of the shape they accept, so an agent had to infer it from a
# list of required fields -- and a reasonable inference is often wrong. A
# reviewer asked for "Check ID, Priority, Exact action, Expected result" emitted
# a markdown table, which is a fair reading and which checklist_groups.py does
# not recognise; the run failed after 49 minutes with "No checklist rows", a
# message describing a different failure entirely.
#
# So: one worked example per artifact, appended to the prompt the same way the
# budget block is. The example is the contract. When a parser changes what it
# accepts, the example here changes with it, and the two stay in one place.
#
# Keep each example minimal and real. It is quoted into the prompt verbatim, so
# a long one costs tokens on every run of that stage.

# A check the checklist parser recognises. It looks for a heading that leads
# with the ID, or a `Check ID:` field -- never a bare ID in a table cell,
# because the traceability matrix at the end of the document is full of those.
_layout_manual_checklist() {
    cat <<'LAYOUT'
Write each check as a heading that begins with its ID, then one field per line.
A markdown table is NOT a supported layout: the driver reads checks by heading
or by a `Check ID:` field, and a table cell holding an ID is not recognised.

### MC-1 Serve the built page

- Priority: P0
- Behavior classification: PRESERVE
- Related behavior: B-2
- Related invariant: I-1
- Preconditions: the build completed; port 4173 is free
- Exclusive resources: port:4173
- Depends on: none
- Exact action: `npm run serve`, then open http://127.0.0.1:4173/
- Expected result: the page renders with the heading visible
- Evidence to capture: screenshot, server log lines
- Actual result:
- Status: NOT RUN

IDs are a prefix, hyphens, and a number: `MC-1`, `MC-12`, `MC-S-1`. Keep every
field, in this order, one per line. Every check MUST declare both `Exclusive
resources` and `Depends on`, using `none` when applicable; these are the
driver's only inputs for safe parallel scheduling. A check missing either,
`Exact action`, or `Expected result` is rejected before execution starts.
LAYOUT
}

# Anything ending in an acceptance gate the driver parses row by row.
_layout_acceptance_gate() {
    cat <<'LAYOUT'
End with exactly one `## Acceptance gate` section holding only this table:

| ID | Required | Status | Evidence |
|---|---|---|---|
| G-1 | YES | PASS | Node 26.8.1 present; `node --version` recorded |
| G-2 | YES | BLOCKED-SETUP | Playwright browsers absent. Action: `npx playwright install chromium`. |

IDs must be plain identifiers -- letters, digits, `-`, `_`, `.`, `/`, and no
spaces. Put the subject of a check in Evidence, never in the ID cell: a row
whose ID contains a space is not parsed, and the stage records no result.
Required is YES or NO. Status is one of PASS, FAIL, BLOCKED-SETUP,
BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE, NOT RUN, N/A. No literal pipes in cells.
LAYOUT
}

# Documents whose enumerable content the driver reads as tables with stable ids.
_layout_id_tables() {
    cat <<'LAYOUT'
Give every enumerated item a stable identifier in the first column, so later
stages and the audit can cite it: `R-1`, `B-2`, `I-3`, `AR-4`, `D-5`. An
identifier is letters, digits and hyphens with no spaces. Never renumber an
existing id; add new ones at the end. One row per item, one item per row.
LAYOUT
}

# The adversarial review. adversarial-context.py enforces all of this: a level-2
# Overall assessment heading with body text, `## AR-001: Title` finding
# headings, five named fields per finding, and the words "No findings" when
# there are none.
_layout_adversarial_review() {
    cat <<'LAYOUT'
Write each finding as a level-2 heading `## AR-001: Title`, then its fields one
per line. End with a level-2 `## Overall assessment` heading followed by body
text. Both are headings, not bold labels inside another section: a line reading
`**Overall assessment:** ...` is NOT recognised and the stage is rejected.

## AR-001: Plan omits the rollback path

- Severity: high
- References: CHANGE_PLAN.md:41
- Failure: a failed migration leaves the schema half-applied
- Fix: state the rollback step and its verification
- Verify: run the migration against a copy and roll back

## Overall assessment

The plan is sound apart from AR-001; the behavior tables are complete.

Every finding needs all five of Severity, References, Failure, Fix and Verify
with nonempty values. With no findings at all, still write the
`## Overall assessment` section and state the words "No findings" explicitly.
LAYOUT
}

# The final audit. final-audit-context.py reads the LAST line of the file as the
# verdict, and audit-findings.py parses the findings table's ID and Blocks
# columns.
_layout_final_audit() {
    cat <<'LAYOUT'
Findings go in a table whose columns include `ID` and `Blocks`, each row
carrying evidence, a correction, and YES or NO in Blocks:

| ID | Finding | Evidence | Correction | Blocks |
|---|---|---|---|---|
| FA-1 | Checklist MC-3 not executed | VERIFICATION_REPORT.md:22 | Run MC-3 | YES |

The VERY LAST line of the document is the verdict, alone on its line, exactly
one of:

READY
READY WITH NON-BLOCKING ISSUES
NOT READY

Nothing may follow it -- no summary, no sign-off, no trailing prose. A verdict
placed anywhere else is not found, and the stage is rejected. `NOT READY`
requires at least one finding row with Blocks = YES.
LAYOUT
}

# The change plan. plan-scope.sh reads the frozen change scope from a level-2
# `## Change-impact table` and takes each backticked path in its rows as the
# plan committing to that file. No prompt stated this, so a planner that wrote
# `Change-impact table:` as a bold label produced a plan whose scope could not
# be resolved, and the run stopped needing an approved-plan edit to continue.
_layout_change_plan() {
    cat <<'LAYOUT'
The frozen change scope is read from a level-2 heading spelled exactly
`## Change-impact table`, followed by a table. A bold label or a `###` heading
is NOT recognised, and the driver cannot resolve the scope without it.

## Change-impact table

| Component | Change | Test coverage |
|---|---|---|
| `scripts/lib/example.sh` | add the guard | `scripts/tests/example-test.sh` |

Name every file the change touches in backticks, in the Component cell, and the
tests that must change with it in Test coverage. Repo-relative paths only: a
leading slash reads as a route, not a file. These rows are the plan committing
to a file set, and later stages check the diff against them.

Every numbered implementation step MUST end with `Owns:`, listing the exact
repo-relative files it alone may edit (or `*` only for a final reconcile step),
and `Depends on:`, listing prerequisite step numbers or `none`. These fields
are the driver's only inputs for safe parallel implementation worktrees. Do
not omit them or infer dependencies from prose.
LAYOUT
    _layout_id_tables
}

# file -> required layout. Silent for a document no parser constrains: an
# invented rule costs tokens on every run and binds nothing.
document_layout() {
    case "${1##*/}" in
        MANUAL_CHECKLIST.md|MANUAL_CHECKLIST.base.md) _layout_manual_checklist ;;
        PREFLIGHT_REPORT.md|TEST_REVIEW.md|VERIFICATION_REPORT.md)
            _layout_acceptance_gate ;;
        ADVERSARIAL_REVIEW.md) _layout_adversarial_review ;;
        FINAL_AUDIT.md) _layout_final_audit ;;
        CHANGE_PLAN.md) _layout_change_plan ;;
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|\
        CHANGE_SPEC.md|BASELINE_REPORT.md|DEFECTS.md)
            _layout_id_tables ;;
        *) return 1 ;;
    esac
}

# The stage prompt may explain how to investigate, but this is the last word on
# what is delivered. It is emitted for every artifact, including reports
# without a parser-specific layout, so an agent cannot substitute a progress
# narrative, filename, or prose summary for the requested document.
document_final_response_contract() {
    local file="$1"
    printf 'Final-response contract for `%s` (binding):\n\n' "$file"
    case "${file##*/}" in
        REQUIREMENTS_INTERPRETATION.md)
            cat <<'CONTRACT'
Return a requirements interpretation, not a plan or a review. Start with `# Requirements interpretation`; then give only: the requested outcome, an ID-keyed requirements/behaviors/invariants table, assumptions and ambiguities, and acceptance criteria. State unknowns as explicit questions or constraints; do not invent an implementation, file list, commands, or verdict.
CONTRACT
            ;;
        PROJECT_PLAN.md)
            cat <<'CONTRACT'
Return an executable proposal, not a requirements restatement or review. Start with `# Project plan`; then give only: objective and constraints, current-state findings, ID-keyed behavior/invariant coverage, ordered implementation steps with exact files and changes, verification commands/evidence, risks/rollback, and open decisions. Do not claim implementation or test results.
Every numbered implementation step must end with `Owns:` (exact repo-relative files, or `*` only for a final reconcile step) and `Depends on:` (prior step numbers or `none`). The parallel implementation scheduler consumes these declarations directly; never omit or infer them.
CONTRACT
            ;;
        UPDATED_PROJECT_PLAN.md)
            cat <<'CONTRACT'
Return the complete revised executable proposal, not a review response. Start with `# Updated project plan`; then give only: the retained objective, a disposition for every review finding, the corrected ordered implementation plan, ID-keyed behavior/invariant coverage, verification commands/evidence, risks/rollback, and remaining approval decisions. Do not repeat the review as prose or claim implementation.
Every numbered implementation step must end with `Owns:` (exact repo-relative files, or `*` only for a final reconcile step) and `Depends on:` (prior step numbers or `none`). The parallel implementation scheduler consumes these declarations directly; never omit or infer them.
CONTRACT
            ;;
        BASELINE_REPORT.md)
            cat <<'CONTRACT'
Return observed baseline evidence, not a future plan. Start with `# Baseline report`; then give only: scope/environment, current behavior and affected files, commands actually run with their results, ID-keyed baseline findings, and the pre-change verification command block. Do not prescribe edits, fabricate results, or give a release verdict.
CONTRACT
            ;;
        CHANGE_SPEC.md)
            cat <<'CONTRACT'
Return a frozen change specification, not an implementation plan. Start with `# Change specification`; then give only: requested change, ID-keyed requirements/behaviors/invariants, preserved behavior, acceptance criteria, explicit non-goals, and compatibility/rollback constraints. Do not list coding steps, assert tests passed, or make an audit verdict.
CONTRACT
            ;;
        CHANGE_PLAN.md|UPDATED_CHANGE_PLAN.md)
            cat <<'CONTRACT'
Return an executable change plan, not a specification or review. Start with `# Change plan`; then give only: scope and constraints, the exact `## Change-impact table`, ordered file-level implementation steps, requirement-to-step traceability, verification commands/evidence, rollback, and unresolved approval decisions. Do not claim the edits or tests were performed.
Every numbered implementation step must end with `Owns:` (exact repo-relative files, or `*` only for a final reconcile step) and `Depends on:` (prior step numbers or `none`). The parallel implementation scheduler consumes these declarations directly; never omit or infer them.
CONTRACT
            ;;
        ADVERSARIAL_REVIEW.md)
            cat <<'CONTRACT'
Return an adversarial assessment of the supplied plan only. Start directly with zero or more `## AR-001: Title` findings in the required finding format, then end with `## Overall assessment`. Every finding must identify a concrete failure mode and correction; do not write a plan, implementation notes, test report, conversation, or generic praise. If clean, say `No findings` in the overall assessment.
CONTRACT
            ;;
        PREFLIGHT_REPORT.md)
            cat <<'CONTRACT'
Return a preflight readiness report, not a plan or final audit. Start with `# Preflight report`; then give only: checked prerequisites/environment, the approved-plan verification commands and outcomes, blockers with recovery actions, and exactly one final `## Acceptance gate` table. Do not modify scope, invent execution evidence, or issue a release verdict.
CONTRACT
            ;;
        IMPLEMENTATION_NOTES.md)
            cat <<'CONTRACT'
Return an implementation record, not a plan or test report. Start with `# Implementation notes`; then give only: completed changes by file, requirement/plan-step traceability, intentional deviations with reasons, unresolved blockers, and handoff notes. Distinguish completed work from proposed work; do not duplicate raw test output or declare the release ready.
CONTRACT
            ;;
        AUTOMATED_TEST_REPORT.md)
            cat <<'CONTRACT'
Return automated-test evidence only. Start with `# Automated test report`; then give only: environment, each command actually executed, result/status, concise failure evidence or output location, coverage gaps, and next action for non-passes. Do not describe implementation decisions, propose a plan, or use a final audit verdict.
CONTRACT
            ;;
        CHANGE_TEST_REPORT.md)
            cat <<'CONTRACT'
Return change-specific test evidence only. Start with `# Change test report`; then give only: changed requirement/behavior IDs, the exact checks run for each, actual result/evidence, regressions or gaps, and required follow-up. Do not repeat implementation notes, restate the whole baseline, or issue a release verdict.
CONTRACT
            ;;
        TEST_REVIEW.md)
            cat <<'CONTRACT'
Return an independent test-readiness review, not test execution output. Start with `# Test review`; then give only: adequacy findings, missing or weak coverage, evidence references, required corrections, and exactly one final `## Acceptance gate` table. Do not write tests, claim unrun checks passed, or give the final release verdict.
CONTRACT
            ;;
        MANUAL_CHECKLIST.md|MANUAL_CHECKLIST.base.md)
            cat <<'CONTRACT'
Return an executable human test checklist only. Start with `# Manual checklist`; then give only the required MC-ID check headings and fields, followed by traceability if needed. Every check must be independently runnable and have explicit preconditions, exact action, expected result, evidence, actual result, and status. Do not write test results before execution, a plan, or a release verdict.
Every check must also contain `Exclusive resources` and `Depends on` in that order; use `none` for each when no lock or ordering requirement exists. These declarations are consumed directly by the parallel checklist scheduler, so never omit or infer them.
CONTRACT
            ;;
        VERIFICATION_REPORT.md)
            cat <<'CONTRACT'
Return execution evidence for the manual/verification checks only. Start with `# Verification report`; then give only: each executed check ID, actual result, status, evidence, failures/blockers, and exactly one final `## Acceptance gate` table. Do not alter the checklist, propose implementation, or pronounce final release readiness.
CONTRACT
            ;;
        DEFECTS.md)
            cat <<'CONTRACT'
Return a defect register only. Start with `# Defects`; then give only one ID-keyed entry per observed defect or blocker: severity, reproduction/evidence, affected requirement or check, current status, owner/next action, and disposition. Do not include clean test narration, a plan, or an audit verdict. If none were observed, state `No defects found` and the evidence scope.
CONTRACT
            ;;
        FINAL_AUDIT.md)
            cat <<'CONTRACT'
Return the release audit only. Start with `# Final audit`; then give only the findings table with evidence, correction, and `Blocks` for each issue, followed by the required verdict as the very last line. Do not include an implementation diary, rerun test output, remediation plan, greeting, or any text after the verdict.
CONTRACT
            ;;
        *)
            cat <<'CONTRACT'
Return only the complete named artifact in its stage-specific Markdown format. Do not add a greeting, progress narrative, code fence, wrapper, claim that it was written elsewhere, or a summary after its final required section.
CONTRACT
            ;;
    esac
}

# The block appended to a stage's prompt, one section per document it writes.
document_layout_prompt() {
    local stage="$1" file layout first=1
    while IFS= read -r file; do
        layout="$(document_layout "$file" 2>/dev/null || true)"
        if [[ "$first" == 1 ]]; then
            printf '\n\n# Required artifact and final-response contracts (binding)\n\n'
            printf 'The driver consumes these documents directly. A document that is\n'
            printf 'correct in substance but delivered in another shape is rejected unread.\n'
            first=0
        fi
        printf '\n## %s\n\n' "$file"
        [[ -z "$layout" ]] || printf '%s\n\n' "$layout"
        document_final_response_contract "$file"
    done < <(stage_documents "$stage")
}
