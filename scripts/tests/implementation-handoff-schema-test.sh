#!/usr/bin/env bash
# The implementation agent is told to write .uncle/workflow/documents/
# CHANGE_TEST_REPORT.json itself. When it invents its own shape instead --
# a real run produced {"source": "...; step 7 and step 8 fragments",
# "rows": [...]} -- the file is present and non-empty, so --missing-only
# preserved it, and the validation that follows failed with an uncaught
# CalledProcessError traceback.
#
# That traceback did not stop anything. The driver calls the enclosing
# function as `run_stepwise_implementation ... || step_status=$?`, which
# suspends errexit for the whole function body, so the stage ran on and
# reported success while an artifact its own schema rejects sat on disk.
#
# An artifact that is not the kind its consumer validates is not a handoff.
# Rewrite it conservatively, and fail loudly if even that will not validate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

project="$work/project"
mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/docs"
git -C "$project" init -q 2>/dev/null || true

fail() { echo "implementation-handoff-schema-test.sh: FAIL: $*" >&2; exit 1; }

# The exact shape the agent wrote, verbatim in structure.
cat > "$project/.uncle/workflow/documents/CHANGE_TEST_REPORT.json" <<'JSON'
{
  "source": ".uncle/docs/CHANGE_TEST_REPORT.md; step 7 and step 8 fragments",
  "rows": [
    {"id": "T-6", "command": "make test-server", "result": "450 passed, 2 skipped, exit 0"},
    {"id": "T-7", "command": "cd client && npm test", "result": "170/170 pass, exit 0"}
  ]
}
JSON

status=0
python3 "$ROOT/scripts/lib/implementation_report_fallback.py" \
    --project "$project" --kind change --missing-only > "$work/out.txt" 2>&1 || status=$?

[[ "$status" == 0 ]] || {
    echo "--- output ---"; cat "$work/out.txt"
    fail "an agent-shaped handoff should be replaced, not fail the fallback (exit $status)"
}
grep -q 'Traceback' "$work/out.txt" && fail 'a validation failure must not surface as a Python traceback'

python3 - "$project" <<'PY' || fail 'the preserved artifact was not replaced with a valid change-test-report'
import json, sys
from pathlib import Path
payload = json.loads((Path(sys.argv[1]) / '.uncle/workflow/documents/CHANGE_TEST_REPORT.json').read_text())
assert payload.get('schema') == 'uncle.artifact/v1', payload.get('schema')
assert payload.get('kind') == 'change-test-report', payload.get('kind')
assert isinstance(payload.get('commands'), list) and payload['commands'], 'needs at least one command row'
assert 'rows' not in payload and 'source' not in payload, 'agent shape survived'
PY

# A conforming report is still left untouched: --missing-only must not
# discard real recorded evidence just because the fallback ran.
cat > "$project/.uncle/workflow/documents/CHANGE_TEST_REPORT.json" <<'JSON'
{"schema": "uncle.artifact/v1", "kind": "change-test-report",
 "commands": [{"command": "make test-server", "status": "PASS", "output": "450 passed", "requirements": []}],
 "coverage_gaps": [], "next_action": "none"}
JSON
python3 "$ROOT/scripts/lib/implementation_report_fallback.py" \
    --project "$project" --kind change --missing-only > /dev/null 2>&1 \
    || fail 'a valid existing report should still pass the fallback'
grep -q '450 passed' "$project/.uncle/workflow/documents/CHANGE_TEST_REPORT.json" \
    || fail 'a valid existing report must be preserved, not overwritten'

echo 'implementation-handoff-schema-test.sh: a misshapen handoff is replaced and reported without a traceback'
