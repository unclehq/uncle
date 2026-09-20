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
field, in this order, one per line. A check missing `Exact action` or
`Expected result` is rejected before execution starts.
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

# The block appended to a stage's prompt, one section per document it writes.
document_layout_prompt() {
    local stage="$1" file layout first=1
    while IFS= read -r file; do
        layout="$(document_layout "$file")" || continue
        if [[ "$first" == 1 ]]; then
            printf '\n\n# Required layout (binding)\n\n'
            printf 'The driver parses these documents. A document that is correct in\n'
            printf 'substance but written in another shape is rejected unread.\n'
            first=0
        fi
        printf '\n## %s\n\n%s\n' "$file" "$layout"
    done < <(stage_documents "$stage")
}
