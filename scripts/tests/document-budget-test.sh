#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
printf 'abc\ndef' > PROJECT_PLAN.md
WORKFLOW_DOC_MAX_BYTES=7 WORKFLOW_DOC_MAX_LINES=2 check_document_budget PROJECT_PLAN.md
if WORKFLOW_DOC_MAX_BYTES=6 check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
if WORKFLOW_DOC_MAX_LINES=1 check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
[[ $(cat PROJECT_PLAN.md) == $'abc\ndef' ]]
for value in 0 invalid -1 1:2; do
    if WORKFLOW_DOC_MAX_BYTES="$value" check_document_budget PROJECT_PLAN.md 2>/dev/null; then exit 1; fi
done
printf 'é' > ADVERSARIAL_REVIEW.md
if WORKFLOW_DOC_MAX_BYTES=1 check_document_budget ADVERSARIAL_REVIEW.md 2>/dev/null; then exit 1; fi
WORKFLOW_DOC_MAX_BYTES=2 check_document_budget ADVERSARIAL_REVIEW.md
printf 'mandatory acceptance evidence' > VERIFICATION_REPORT.md
WORKFLOW_DOC_MAX_BYTES=1 check_document_budget VERIFICATION_REPORT.md
LOG_DIR="$tmp"
printf 'stage instructions' > prompt.md
WORKFLOW_DOC_MAX_BYTES=12345 gated_prompt prompt.md updated-plan > resolved
rg -q '12345 UTF-8 bytes' "$(cat resolved)"
# Exercise the driver's post-agent guard: oversized output cannot reach approval.
awk '/^require_artifact\(\)/ {copy=1} copy {print} copy && /^}/ {exit}' \
    "$ROOT/scripts/stagegate.sh" > guard.sh
[[ -s guard.sh ]]
bash -n guard.sh
. ./guard.sh
if (WORKFLOW_DOC_MAX_BYTES=1 require_artifact PROJECT_PLAN.md; touch advanced) 2>/dev/null; then
    exit 1
fi
[[ ! -e advanced && -s PROJECT_PLAN.md ]]
(WORKFLOW_DOC_MAX_BYTES=7 require_artifact PROJECT_PLAN.md; touch advanced)
[[ -e advanced ]]
echo 'document-budget-test: passed'
