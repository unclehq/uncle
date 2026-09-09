#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
STATE_DIR=.uncle/workflow
WORKFLOW_BUDGET_PROMPT=1
# Everything below is about the raise-the-limit dialog, which only exists
# when the budget is being enforced. By default an overrun is advisory and
# there is nothing to approve -- asserted at the end.
WORKFLOW_DOC_BUDGET_ENFORCE=1
printf 'Brief\n' > REQUIREMENTS.md
python3 - <<'PY'
from pathlib import Path
Path('MANUAL_CHECKLIST.md').write_text('x'*12063+'\n')
PY
before="$(cksum MANUAL_CHECKLIST.md)"
if check_document_budget MANUAL_CHECKLIST.md <<<'n'; then exit 1; fi
if check_document_budget MANUAL_CHECKLIST.md </dev/null; then exit 1; fi
if check_document_budget MANUAL_CHECKLIST.md probe <<<'y'; then exit 1; fi
check_document_budget MANUAL_CHECKLIST.md <<<'y'
[[ "$(cksum MANUAL_CHECKLIST.md)" == "$before" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
check_document_budget MANUAL_CHECKLIST.md </dev/null
printf 'Different brief\n' > REQUIREMENTS.md
if check_document_budget MANUAL_CHECKLIST.md </dev/null; then exit 1; fi
printf 'Brief\n' > REQUIREMENTS.md
# Ensure both byte and line overages can be approved.
python3 - <<'PY'
from pathlib import Path
Path('MANUAL_CHECKLIST.md').write_text('line\n'*600)
PY
check_document_budget MANUAL_CHECKLIST.md <<<'y'
check_document_budget MANUAL_CHECKLIST.md </dev/null
# Advisory by default: no dialog, no stop, document untouched.
python3 - <<'PY'
from pathlib import Path
Path('MANUAL_CHECKLIST.md').write_text('x'*12063+'\n')
PY
before="$(cksum MANUAL_CHECKLIST.md)"
rm -rf .uncle/workflow/document-budgets
out="$(WORKFLOW_DOC_BUDGET_ENFORCE=0 check_document_budget MANUAL_CHECKLIST.md </dev/null 2>&1)" \
    || { echo "FAIL $0:$LINENO an advisory overrun must not fail" >&2; exit 1; }
case "$out" in
    *'[Y/N]'*) echo "FAIL $0:$LINENO advisory mode must not open the dialog" >&2; exit 1 ;;
esac
case "$out" in
    *'budget is advisory'*) ;;
    *) echo "FAIL $0:$LINENO advisory mode must say so: $out" >&2; exit 1 ;;
esac
[[ "$(cksum MANUAL_CHECKLIST.md)" == "$before" ]] \
    || { echo "FAIL $0:$LINENO the document must be left alone" >&2; exit 1; }

echo 'document-budget-prompt-test.sh: approve, decline, EOF, probe, resume, source change, line limits, and the advisory default passed'
