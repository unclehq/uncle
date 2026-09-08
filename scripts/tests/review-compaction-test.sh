#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
LOG_DIR="$tmp"
export CALLS="$tmp/calls" CANDIDATE="$tmp/candidate.md"
cat > reviewer <<'STUB'
#!/usr/bin/env bash
printf 'called\n' >> "$CALLS"
printf '%s\n' "$*" > "$CALLS.argv"
out=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == --output-last-message ]]; then shift; out="$1"; fi
    shift
done
case "${MODE:-ok}" in
    fail) exit 7 ;;
    timeout) sleep 30 ;;
    *) cp "$CANDIDATE" "$out" ;;
esac
STUB
chmod +x reviewer
cat > candidate.md <<'EOF'
## Findings
### AR-001 — Verify content
Severity: High
`tests/text.mjs` must reject altered content at 320 px. See R-1.
## Acceptance gate
| ID | Required | Status | Evidence |
|---|---|---|---|
| R-1 | YES | FAIL | AR-001 |
## Commands
```sh
node tests/text.mjs
```
NOT READY
EOF
cp candidate.md original.md
python3 - <<'PY'
from pathlib import Path
p=Path('original.md')
s=p.read_text().replace('## Acceptance gate', 'Repeated background. ' * 100 + '\n## Acceptance gate')
p.write_text(s)
PY
export WORKFLOW_DOC_MAX_BYTES=500 WORKFLOW_DOC_MAX_LINES=40
cp original.md ADVERSARIAL_REVIEW.md
finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" vendor/model high adversarial-review
cmp candidate.md ADVERSARIAL_REVIEW.md
[[ $(wc -l < "$CALLS") -eq 1 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
rg -q -- '--sandbox read-only -m vendor/model -c model_reasoning_effort=high' "$CALLS.argv"
[[ $(find "$tmp" -name original.md | wc -l) -ge 2 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Already-fitting reviews cost no extra invocation.
finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review
[[ $(wc -l < "$CALLS") -eq 1 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
for mode in fail timeout oversized lost-id changed-status; do
    cp original.md ADVERSARIAL_REVIEW.md
    cp candidate.md good.md
    case "$mode" in
        oversized) cp original.md candidate.md ;;
        lost-id) sed 's/AR-001/AR-002/g' good.md > candidate.md ;;
        changed-status) sed 's/YES | FAIL/YES | PASS/' good.md > candidate.md ;;
    esac
    before=$(wc -l < "$CALLS")
    if MODE="$mode" WORKFLOW_REVIEW_COMPACT_SECONDS=1 \
        finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review > rejected 2>&1; then
        echo "unexpected success: $mode"; exit 1
    fi
    cmp original.md ADVERSARIAL_REVIEW.md
    [[ $(wc -l < "$CALLS") -eq $((before + 1)) ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    mv good.md candidate.md
done
# Explicit opt-out does not call the reviewer.
before=$(wc -l < "$CALLS")
if WORKFLOW_REVIEW_COMPACT=0 finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review > /dev/null 2>&1; then exit 1; fi
[[ $(wc -l < "$CALLS") -eq "$before" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Guard details independently: no table, command, heading, threshold or verdict loss.
python3 - "$ROOT" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('compact', Path(sys.argv[1])/'scripts/lib/compact-review.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
original=Path('candidate.md').read_text()
m.validate(original, original.replace('Severity: High', 'Severity: High; References: R-1'), 1000, 100)
for candidate in [original.replace('320', '321'), original.replace('Severity: High', 'Severity: Low'),
                  original.replace('Severity: High', 'Severity: High; Severity: Low'),
                  original.replace('node tests/text.mjs', 'true'), original.replace('## Commands', '## Other'),
                  original.replace('NOT READY', 'READY'), original.replace('`tests/text.mjs`', '`tests/other.mjs`')]:
    try: m.validate(original,candidate,1000,100)
    except ValueError: pass
    else: raise AssertionError('changed contract accepted')
PY
echo 'review-compaction-test: passed'
