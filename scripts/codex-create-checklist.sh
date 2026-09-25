#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${UNCLE_RUNTIME_ROOT:-}" && -d "$UNCLE_RUNTIME_ROOT/scripts" ]]; then
    ROOT="$(cd -L "$UNCLE_RUNTIME_ROOT" && pwd -L)"
else
    ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"
export DOCUMENT_BUDGET_SOURCE=REQUIREMENTS.md

usage() {
    cat <<'EOF'
Usage: codex-create-checklist.sh [-h|--help]

Run the reviewer CLI against the approved .uncle/docs/UPDATED_PROJECT_PLAN.md and the
automated-test report, and write .uncle/docs/MANUAL_CHECKLIST.md (Stage 6 of the
new-application workflow).

Takes no positional arguments. Requires REQUIREMENTS.md,
.uncle/docs/UPDATED_PROJECT_PLAN.md, .uncle/docs/AUTOMATED_TEST_REPORT.md, and a matching approval
record in .uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256.
Configuration is via WORKFLOW_* environment variables (see scripts/README.md).
EOF
}

case "$#:${1:-}" in
    0:)            ;;
    1:-h|1:--help) usage; exit 0 ;;
    *)             printf 'Unknown argument: %s\n' "${1:-}" >&2; usage >&2; exit 1 ;;
esac

test -s REQUIREMENTS.md
test -s .uncle/docs/UPDATED_PROJECT_PLAN.md
test -s .uncle/docs/AUTOMATED_TEST_REPORT.md
test -s .uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256

expected="$(cat .uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256)"
# shasum on macOS, sha256sum on Linux, openssl anywhere else.
if command -v shasum > /dev/null 2>&1; then
    actual="$(shasum -a 256 .uncle/docs/UPDATED_PROJECT_PLAN.md | awk '{print $1}')"
elif command -v sha256sum > /dev/null 2>&1; then
    actual="$(sha256sum .uncle/docs/UPDATED_PROJECT_PLAN.md | awk '{print $1}')"
else
    actual="$(openssl dgst -sha256 .uncle/docs/UPDATED_PROJECT_PLAN.md | awk '{print $NF}')"
fi

if [[ "$expected" != "$actual" ]]; then
    echo ".uncle/docs/UPDATED_PROJECT_PLAN.md changed after approval."
    exit 1
fi

REVIEWER_CMD="${WORKFLOW_REVIEWER_CMD:-codex}"
. "$ROOT/scripts/lib/gates.sh"
budget_prompt="$(document_budget_prompt manual-checklist)"

"$REVIEWER_CMD" exec \
    --ephemeral \
    --sandbox read-only \
    --output-last-message .uncle/docs/MANUAL_CHECKLIST.md \
    "$(cat <<'PROMPT'
Act as an independent release-verification engineer.

Inspect:

- REQUIREMENTS.md
- .uncle/docs/PROJECT_PLAN.md
- .uncle/docs/ADVERSARIAL_REVIEW.md
- .uncle/docs/UPDATED_PROJECT_PLAN.md
- .uncle/docs/AUTOMATED_TEST_REPORT.md
- implementation source files
- automated tests
- startup and build scripts

Do not modify source code.
Do not claim any check passed.
Do not merely repeat automated tests.

Create .uncle/docs/MANUAL_CHECKLIST.md.

The checklist must verify:

1. Every documented user-visible behavior
2. Every system behavior
3. Every invariant that can be observed manually
4. Startup and shutdown
5. Backend and frontend integration
6. Invalid inputs
7. Boundary values
8. Stale and out-of-order events
9. Inventory limits
10. Accounting behavior
11. Error visibility
12. Recovery behavior
13. Restart behavior
14. Requirements not covered by automated tests

Each item must contain:

- check ID;
- priority: Critical, Important, or Optional;
- related behavior IDs;
- related invariant IDs;
- prerequisites;
- exact action;
- expected result;
- evidence to capture;
- actual result placeholder;
- status placeholder: NOT RUN.

Separate the checklist into:

- Smoke checks
- Behavior checks
- Invariant checks
- Failure-path checks
- Full-stack checks
- Regression checks
- Optional checks

End with a requirements-to-check traceability table.
PROMPT
printf '%s\n' "$budget_prompt"
)"

LOG_DIR="$ROOT/.uncle/workflow/logs"
mkdir -p "$LOG_DIR"
finish_review_budget .uncle/docs/MANUAL_CHECKLIST.md "$REVIEWER_CMD" "" "" manual-checklist
echo "Created .uncle/docs/MANUAL_CHECKLIST.md"
