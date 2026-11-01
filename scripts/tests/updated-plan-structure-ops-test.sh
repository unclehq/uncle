#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
STATE_DIR=.uncle/workflow; LOG_DIR="$STATE_DIR/logs"
mkdir -p "$STATE_DIR/documents" "$LOG_DIR" .uncle/docs
. "$ROOT/scripts/lib/updated-plan-repair.sh"
python3 - "$ROOT" <<'PY'
import sys,json
from pathlib import Path
sys.path.insert(0, sys.argv[1]+'/scripts/lib')
import artifact_json
p={'schema':'uncle.artifact/v1','kind':'plan','narrative':'# Plan\n\n## Implementation order\n\n1. **Core** — Write core.\n   Owns: `src/core.js`\n',
   'verification_commands':'npm test','protected_verification_paths':'tests/core.test.js',
   'dispositions':[{'finding':'AR-1','disposition':'Accepted','reason':'test','plan_change':'Add tests/core.test.js to Step 1 Owns.'}]}
Path('.uncle/workflow/documents/PROJECT_PLAN.json').write_text(json.dumps(p))
Path('.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json').write_text(json.dumps(p))
Path('.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text(artifact_json.render_plan(p,protected=True))
PY
run_claude() { echo 'unexpected model call' >&2; return 99; }
run_updated_plan_structure_repair "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" \
    'a protected verification path with no owning implementation step' updated-plan
python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" .uncle/docs/UPDATED_PROJECT_PLAN.md "$PWD" "$STATE_DIR"
python3 - "$ROOT" <<'PY'
import sys,json
from pathlib import Path
sys.path.insert(0, sys.argv[1]+'/scripts/lib')
import artifact_json
p=json.loads(Path('.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json').read_text())
p['protected_verification_paths']='tests/unknown.test.js'
p['dispositions']=[]
Path('.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json').write_text(json.dumps(p))
Path('.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text(artifact_json.render_plan(p,protected=True))
PY
run_claude() {
    [[ "$UNCLE_WORKER_MAX_TURNS" == 3 && "$UNCLE_UPDATED_PLAN_ANSWER_TOKENS" == 4096 ]]
    printf 'call\n' >> "$STATE_DIR/calls"
    [[ "$2" == updated-plan-worker-edits-structure ]]
    printf '%s\n' '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[{"op":"set_step","id":"step-1","fields":{"owns":"src/core.js, tests/core.test.js, tests/unknown.test.js"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
}
run_updated_plan_structure_repair "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" \
    'a protected verification path with no owning implementation step' updated-plan
[[ "$(wc -l < "$STATE_DIR/calls" | tr -d ' ')" == 1 ]]
python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" .uncle/docs/UPDATED_PROJECT_PLAN.md "$PWD" "$STATE_DIR"
# The change-plan approval gate uses the same deterministic edit-only repair.
python3 - "$ROOT" <<'PY2'
import sys,json
from pathlib import Path
sys.path.insert(0, sys.argv[1]+'/scripts/lib')
import artifact_json
p=json.loads(Path('.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json').read_text())
p.update(kind='change-plan', protected_verification_paths='tests/core.spec.js', dispositions=[])
Path('.uncle/workflow/documents/CHANGE_PLAN.json').write_text(json.dumps(p))
Path('.uncle/docs/CHANGE_PLAN.md').write_text(artifact_json.render_change_plan(p,require_dispositions=True))
PY2
run_claude() { echo 'unexpected change model call' >&2; return 99; }
run_updated_plan_structure_repair "$STATE_DIR/documents/CHANGE_PLAN.json" \
    'a protected verification path with no owning implementation step' updated-change-plan
python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" .uncle/docs/CHANGE_PLAN.md "$PWD" "$STATE_DIR"
# Structural feedback must bypass a cached speculative plan and all synthesis paths.
awk '/^run_gated_stage\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > functions.sh
. ./functions.sh
printf 'repair\n' > "$STATE_DIR/updated-plan-structure-feedback.md"
adopt_speculation() { touch unexpected-speculation; return 0; }
run_stage() { [[ "$1" == UPDATED_PLAN ]]; }
run_gated_stage UPDATED_PLAN review plan
[[ ! -e unexpected-speculation ]]
python3 - "$ROOT/scripts/stagegate.sh" <<'PY'
import sys
s=open(sys.argv[1]).read()
branch=s[s.index('        UPDATED_PLAN)\n            if [[ -s'):]
repair=branch[:branch.index('            # A review with findings')]
assert 'run_updated_plan_structure_repair' in repair
assert 'return 0' in repair
assert 'run_updated_plan_fast_path' not in repair
assert 'Return the complete corrected plan' not in s
PY
echo 'updated-plan-structure-ops-test.sh: deterministic repair, one scoped call and retry routing passed'
