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
Usage: codex-review-plan.sh [-h|--help]

Run the reviewer CLI against the approved .uncle/docs/PROJECT_PLAN.md and write
.uncle/docs/ADVERSARIAL_REVIEW.md (Stage 2 of the new-application workflow).

Takes no positional arguments. Requires REQUIREMENTS.md, .uncle/docs/PROJECT_PLAN.md, and
a matching approval record in .uncle/workflow/approvals/PROJECT_PLAN.sha256.
Configuration is via WORKFLOW_* environment variables (see scripts/README.md).
EOF
}

case "$#:${1:-}" in
    0:)            ;;
    1:-h|1:--help) usage; exit 0 ;;
    *)             printf 'Unknown argument: %s\n' "${1:-}" >&2; usage >&2; exit 1 ;;
esac

test -s REQUIREMENTS.md
test -s .uncle/docs/PROJECT_PLAN.md
test -s .uncle/workflow/approvals/PROJECT_PLAN.sha256

expected="$(cat .uncle/workflow/approvals/PROJECT_PLAN.sha256)"
# shasum on macOS, sha256sum on Linux, openssl anywhere else.
if command -v shasum > /dev/null 2>&1; then
    actual="$(shasum -a 256 .uncle/docs/PROJECT_PLAN.md | awk '{print $1}')"
elif command -v sha256sum > /dev/null 2>&1; then
    actual="$(sha256sum .uncle/docs/PROJECT_PLAN.md | awk '{print $1}')"
else
    actual="$(openssl dgst -sha256 .uncle/docs/PROJECT_PLAN.md | awk '{print $NF}')"
fi

if [[ "$expected" != "$actual" ]]; then
    echo ".uncle/docs/PROJECT_PLAN.md changed after approval."
    echo "Review and approve it again before continuing."
    exit 1
fi

REVIEWER_CMD="${WORKFLOW_REVIEWER_CMD:-codex}"
. "$ROOT/scripts/lib/gates.sh"
budget_prompt="$(document_budget_prompt adversarial-review)"

"$REVIEWER_CMD" exec \
    --ephemeral \
    --sandbox read-only \
    --output-last-message .uncle/docs/ADVERSARIAL_REVIEW.md \
    "$(cat <<'PROMPT'
Act as an independent adversarial principal engineer.

Read REQUIREMENTS.md and .uncle/docs/PROJECT_PLAN.md.

Do not implement the project.
Do not modify .uncle/docs/PROJECT_PLAN.md.
Do not assume that compilation proves correctness.

Create an adversarial review covering:

1. Requirements that are omitted, misunderstood, or ambiguous
2. Behaviors that are underspecified
3. Invariants that are missing, weak, or untestable
4. Incorrect domain assumptions
5. State-ownership and concurrency hazards
6. Failure modes and edge cases
7. Security and operational risks
8. Tests that could pass despite incorrect behavior
9. Overengineering and unnecessary scope
10. Features that should be cut under time pressure
11. Problems likely to arise from AI-generated code
12. A recommended implementation order

For every finding include:

- finding ID;
- severity: Critical, High, Medium, or Low;
- affected behavior or invariant;
- evidence from the requirements or plan;
- concrete failure scenario;
- recommended correction;
- proposed verification.

End with:

- Blocking findings
- Non-blocking improvements
- Suggested plan changes
- Overall assessment

Write only the review. Do not claim that any implementation exists.
PROMPT
printf '%s\n' "$budget_prompt"
)"

LOG_DIR="$ROOT/.uncle/workflow/logs"
mkdir -p "$LOG_DIR"
finish_review_budget .uncle/docs/ADVERSARIAL_REVIEW.md "$REVIEWER_CMD" "" "" adversarial-review
echo "Created .uncle/docs/ADVERSARIAL_REVIEW.md"
echo "Workflow paused for human review."
