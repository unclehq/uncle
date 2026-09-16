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

# file -> required layout. Silent for a document no parser constrains: an
# invented rule costs tokens on every run and binds nothing.
document_layout() {
    case "${1##*/}" in
        MANUAL_CHECKLIST.md|MANUAL_CHECKLIST.base.md) _layout_manual_checklist ;;
        PREFLIGHT_REPORT.md|TEST_REVIEW.md|VERIFICATION_REPORT.md|FINAL_AUDIT.md)
            _layout_acceptance_gate ;;
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|\
        CHANGE_SPEC.md|CHANGE_PLAN.md|ADVERSARIAL_REVIEW.md|BASELINE_REPORT.md|\
        DEFECTS.md)
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
