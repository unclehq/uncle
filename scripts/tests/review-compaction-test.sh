#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
LOG_DIR="$tmp"
unset WORKFLOW_DOC_BUDGET_ENFORCE
export CALLS="$tmp/calls"
cat > reviewer <<'STUB'
#!/usr/bin/env bash
printf 'unexpected compaction runner\n' >> "$CALLS"
exit 7
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
s=p.read_text(encoding='utf-8').replace('## Acceptance gate', 'Repeated background. ' * 100 + '\n## Acceptance gate')
p.write_bytes(s.encode("utf-8"))
PY
export WORKFLOW_DOC_MAX_BYTES=500 WORKFLOW_DOC_MAX_LINES=40
# Compaction belongs to the producing stage. Finishing checks the report,
# preserves it when oversized, and never invokes another model.
cp original.md ADVERSARIAL_REVIEW.md
finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" vendor/model high adversarial-review > advisory 2>&1
cmp original.md ADVERSARIAL_REVIEW.md
[[ ! -e "$CALLS" ]]
# Fitting reports also remain unchanged without another invocation.
cp candidate.md ADVERSARIAL_REVIEW.md
finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review
cmp candidate.md ADVERSARIAL_REVIEW.md
[[ ! -e "$CALLS" ]]
# Strict budgets still reject oversized reports without modifying their content.
cp original.md ADVERSARIAL_REVIEW.md
if WORKFLOW_DOC_BUDGET_ENFORCE=1 \
    finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review </dev/null > enforced 2>&1; then
    echo 'FAIL: enforced budget accepted oversized report'; exit 1
fi
cmp original.md ADVERSARIAL_REVIEW.md
[[ ! -e "$CALLS" ]]
# Missing or empty output cannot advance even with advisory budgets.
for file in missing.md empty.md; do
    [[ "$file" != empty.md ]] || : > "$file"
    if finish_review_budget "$file" "$tmp/reviewer" '' '' adversarial-review > invalid 2>&1; then
        echo "FAIL: accepted $file"; exit 1
    fi
done
# Guard details independently: no table, command, heading, threshold or verdict loss.
python3 - "$ROOT" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('compact', Path(sys.argv[1])/'scripts/lib/compact-review.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
original=Path('candidate.md').read_text(encoding='utf-8')
m.validate(original, original.replace('Severity: High', 'Severity: High; References: R-1'), 1000, 100)
for candidate in [original.replace('320', '321'), original.replace('Severity: High', 'Severity: Low'),
                  original.replace('Severity: High', 'Severity: High; Severity: Low'),
                  original.replace('node tests/text.mjs', 'true'), original.replace('## Commands', '## Other'),
                  original.replace('NOT READY', 'READY'), original.replace('`tests/text.mjs`', '`tests/other.mjs`')]:
    try: m.validate(original,candidate,1000,100)
    except ValueError: pass
    else: raise AssertionError('changed contract accepted')
PY
# Repair evidence before compaction, so rejected candidates leave a usable
# original even when it exceeds the advisory budget. FAIL stays FAIL.
. "$ROOT/scripts/lib/acceptance.sh"
python3 - "$ROOT" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('repair', Path(sys.argv[1])/'scripts/lib/repair-acceptance.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
original = Path('original.md').read_text().replace('| AR-001 |', '| `echo hello | grep hello` |')
fixed = m.repair(original)
assert '`echo hello &#124; grep hello`' in fixed
assert '| R-1 | YES | FAIL |' in fixed
assert m.repair(fixed) == fixed
assert m.repair(original.replace('## Acceptance gate', '## Other')) == original.replace('## Acceptance gate', '## Other')
Path('ADVERSARIAL_REVIEW.md').write_bytes(original.encode())
Path('expected.md').write_bytes(fixed.encode())
PY
finish_review_budget ADVERSARIAL_REVIEW.md "$tmp/reviewer" '' '' adversarial-review > repaired 2>&1
cmp expected.md ADVERSARIAL_REVIEW.md
[[ "$(acceptance_result ADVERSARIAL_REVIEW.md R-1)" == REPAIR ]] \
    || { echo 'FAIL: repaired failing report must route to repair'; exit 1; }
[[ -n "$(find .uncle/workflow/logs -name '*before-table-repair-*.md')" ]]
# adversarial-review is a compact-first stage: in advisory mode it is held to
# ZERO size-only passes and the two-pass text is deliberately replaced, not
# added to. Assert the two-pass limit where it applies, under enforcement.
WORKFLOW_DOC_BUDGET_ENFORCE=1 document_budget_prompt adversarial-review > budget-prompt
grep -q 'at most TWO passes total during this stage' budget-prompt
grep -q 'same model and context' budget-prompt
grep -q 'finish without any size-only' budget-prompt
grep -q 'After pass 2, stop size-only edits' budget-prompt
# ...and that advisory mode states the stricter policy rather than nothing.
document_budget_prompt adversarial-review > advisory-prompt
grep -q 'do ZERO size-only compaction passes' advisory-prompt
grep -q 'Never return a filename, progress note, or summary in place of the document.' advisory-prompt
[[ ! -e "$CALLS" ]]
echo 'review-compaction-test: passed'
