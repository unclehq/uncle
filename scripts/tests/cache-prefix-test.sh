#!/usr/bin/env bash
# Byte-level prefix and instruction-preservation checks; no Git/model fixtures.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
python3 -B - "$ROOT" "$TMP" <<'PY'
from collections import Counter
from pathlib import Path
import os, sys
sys.path.insert(0, sys.argv[1] + '/scripts/lib')
import updated_plan_edits as edits
import updated_plan_ops as ops
import updated_plan_synthesis_prompt as synthesis
root = Path(sys.argv[2])
plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan',
        'narrative': '# Plan\n\n## Behavior\n\nKeep café and all requirements.\n',
        'verification_commands': 'python3 check.py'}
review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
          'findings': [{'id': 'AR-001', 'fix': 'Keep checks'}, {'id': 'AR-002', 'fix': 'Keep gates'}]}
base = root / 'base.md'
base.write_text(synthesis.prompt(plan, review, None), encoding='utf-8')
for module in (edits, ops):
    for change in (False, True):
        edits.CHANGE = ops.CHANGE = change
        values = []
        for owner, ids in ((True, ['AR-001']), (False, ['AR-002'])):
            out = root / 'out.md'
            module.write_prompt(base, ids, out, owns_fields=owner)
            after = out.read_bytes()
            original = edits.defer_reply_example
            try:
                edits.defer_reply_example = lambda text: text
                module.write_prompt(base, ids, out, owns_fields=owner)
                before = out.read_bytes()
            finally:
                edits.defer_reply_example = original
            # Exact permutation of one block, including UTF-8 bytes and all instructions.
            intro = b'\n\nDo not write a top-level `narrative` key'
            start = before.index(intro)
            end = before.index(b'\n```', before.index(b'```json', start)) + len(b'\n```')
            block = before[start:end]
            assert after.count(block) == 1
            assert before[:start] + before[end:] == after.replace(block, b'', 1)
            assert Counter(before.splitlines()) == Counter(after.splitlines())
            values.append(after)
        a, b = values
        prefix = os.path.commonprefix(values)
        assert b'and all requirements.' in prefix
        assert b'AR-002' in prefix   # full review before per-writer assignment
        if module is ops:
            assert b'## Plan model (JSON)' in prefix
            assert b'## You decide each finding yourself (binding)' in prefix
        assert b'## Your slice' not in a[:a.index(intro)]
        assert b'"protected_verification_paths":"..."' not in b
        if not change:
            assert b'"protected_verification_paths":"..."' in a
assert edits.defer_reply_example('custom prompt without an example') == 'custom prompt without an example'
print('Writer prefixes include the entire plan/review; all instruction bytes preserved (ops/patch, app/change).')
PY
cd "$TMP"
mkdir -p logs .uncle/workflow
LOG_DIR="$TMP/logs"; STATE_DIR="$TMP/.uncle/workflow"
. "$ROOT/scripts/lib/gates.sh"
printf 'Worker A: step 1, /tmp/a, 2026-01-01\n' > a.md
printf 'Worker B: step 2, /tmp/b, 2026-02-02\n' > b.md
a="$(gated_prompt a.md updated-plan-worker-edits-1)"
b="$(gated_prompt b.md updated-plan-worker-edits-2)"
x="$(gated_prompt a.md implementation-step-1)"
y="$(gated_prompt b.md repair)"
python3 -B - "$a" "$b" "$x" "$y" "$ROOT" <<'PY'
from pathlib import Path
import os, sys
a,b,x,y=(Path(f).read_bytes() for f in sys.argv[1:5])
prefix=os.path.commonprefix((a,b))
assert b'Compact worker contract' in prefix and b'validates all evidence' in prefix
assert a.endswith(Path('a.md').read_bytes()) and b.endswith(Path('b.md').read_bytes())
prefix=os.path.commonprefix((x,y))
assert b'Acceptance provenance' in prefix and b'Tool-call economy' in prefix
rules=Path(sys.argv[5], 'lib/gates/EXECUTION_RULES.md').read_bytes()
assert rules in prefix
assert Path('a.md').read_bytes() in x and Path('b.md').read_bytes() in y
print('Fallback worker shared prefix: %d bytes; cross-stage gate prefix: %d bytes.' % (len(os.path.commonprefix((a,b))),len(prefix)))
PY
