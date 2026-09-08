#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
STATE_DIR=.uncle/workflow
WORKFLOW_BUDGET_PROMPT=1
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
[[ "$(cksum MANUAL_CHECKLIST.md)" == "$before" ]]
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
echo 'document-budget-prompt-test.sh: approve, decline, EOF, probe, resume, source change, and line limits passed'
