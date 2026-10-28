#!/usr/bin/env bash
# run_project_plan_sections with typed blocks: the outline is a JSON packet, every other worker answers with blocks, the
# driver renders each packet into its section file and assembles both the Markdown plan and the plan model.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
export WORKFLOW_PLAN_BLOCKS=1
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^(project_plan_section_run|project_plan_section_finish|run_project_plan_sections)\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

export ROOT_DIR="$ROOT"
python3 -B - "$TMP/good" <<'PY'
import importlib.util, os, sys
from pathlib import Path
root = Path(os.environ['ROOT_DIR'])
spec = importlib.util.spec_from_file_location('t', root / 'scripts' / 'tests' / 'project-plan-sections-test.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
Path(sys.argv[1]).mkdir(parents=True)
module.good_files(sys.argv[1], trace=True)
PY

run_case() {   # name mode [hosted|local]
    local name="$1" mode="$2" runner="${3:-hosted}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/logs"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
        if [[ "$runner" == hosted ]]; then stage_supports_structured_output() { return 0; }; fi
        if [[ "$runner" == local ]]; then stage_uses_self_hosted() { return 0; }; fi
        run_claude() {   # prompt stage
            local worker="${2#project-plan-section-}"
            printf '%s\n' "$worker" >> "$STATE_DIR/order"
            echo "$worker schema=${UNCLE_OUTPUT_SCHEMA_FILE:-none} out=${UNCLE_STRUCTURED_OUTPUT_PATH:-none} kinds=$(grep -o 'project-plan-[a-z]*-[a-z]*-packet\|project-plan-outline-packet' "$1" | sort -u | tr '\n' ' ')" >> "$STATE_DIR/calls"
            sleep 0.2
            if [[ "$mode:$worker" == badpacket:commands ]]; then echo '{"sections":[]}' > "$UNCLE_WORKER_PACKET_PATH"; return 0; fi
            if [[ "$mode:$worker" == lane:closing ]]; then
                ROOT_DIR="$ROOT" python3 -B - "$UNCLE_WORKER_PACKET_PATH" <<'PY'
import json, sys
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'project-plan-section-model-packet',
           'sections': [{'heading': '7. Domain invariants', 'blocks': [{'kind': 'prose', 'text': 'stolen'}]}]}, open(sys.argv[1], 'w'))
PY
                return 0
            fi
            ROOT_DIR="$ROOT" python3 -B - "$TMP/good/$worker.md" "$UNCLE_WORKER_PACKET_PATH" "$worker" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ['ROOT_DIR'] + '/scripts/lib')
import plan_model as pm, project_plan_sections as S
worker, target = sys.argv[3], sys.argv[2]
if worker == 'outline':
    packet = {'schema': 'uncle.artifact/v1', 'kind': 'project-plan-outline-packet', 'stack': 'React, Vite, Vitest',
              'components': [{'id': 'C-1', 'name': 'App', 'responsibility': 'root', 'files': 'src/App.jsx'}],
              'steps': [{'number': '1', 'title': 'Scaffold', 'owns': 'package.json', 'depends_on': ''}],
              'decisions': [{'id': 'D-1', 'text': 'Vite'}], 'restrictions': [{'id': 'R-1', 'text': 'no network', 'source_kind': 'USER'}],
              'tests': [{'runner': 'vitest', 'files': 'tests/a.test.js'}], 'requirement_map': [{'requirement': 'R-1', 'components': 'C-1'}]}
else:
    data, body = S.trace_lines(open(sys.argv[1]).read())
    sections = []
    for line, content in S.blocks(body):
        blocks = pm.import_markdown(line + '\n\n' + (content or '(empty)'))['sections'][0]['blocks']
        sections.append({'heading': line[3:], 'blocks': [pm.flat_of(b) for b in blocks]})
    packet = {'schema': 'uncle.artifact/v1', 'kind': 'project-plan-section-model-packet', 'sections': sections}
    trace = [{'kind': kind, 'requirement': req, 'ids': ids} for kind, rows in data.items() for req, ids in rows.items()]
    if trace:
        packet['trace'] = trace
json.dump(packet, open(target, 'w'))
PY
        }
        . "$TMP/fn.sh"
        run_project_plan_sections "$dir/plan.md" > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}

run_case ok ok hosted
w="$TMP/ok/.uncle/workflow"; parts="$w/project-plan-sections"
check "hosted: plan assembled"                      test "$(cat "$w/rc")" == 0
check "hosted: the plan is Markdown for people"     grep -q '^## 6\. Observable behaviors' "$TMP/ok/plan.md"
check "hosted: twelve workers, no model trace"         bash -c 'test "$(wc -l < "$1" | tr -d " ")" == 12 && ! grep -q "^trace" "$1"' _ "$w/order"
check "hosted: every worker had a schema"          bash -c 'test "$(grep -c "schema=.*/schemas/" "$1")" == 12' _ "$w/calls"
check "hosted: the outline had the outline schema" bash -c 'grep "^outline " "$1" | grep -q "project-plan-outline-packet"' _ "$w/calls"
check "hosted: workers were asked for blocks"      bash -c 'grep "^behaviors " "$1" | grep -q "project-plan-section-model-packet"' _ "$w/calls"
check "hosted: workers read the outline as JSON"   grep -q 'outline.json' "$parts/prompts/behaviors.md"
check "hosted: the outline schema is the outline"  python3 - "$parts/schemas/outline.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))['properties']
sys.exit(0 if 'requirement_map' in p and p['kind'] == {'const': 'project-plan-outline-packet'} else 1)
PY
check "hosted: a worker's schema lists its lane (titles without ##)" python3 - "$parts/schemas/behaviors.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
heading = s['properties']['sections']['items']['properties']['heading']['enum']
sys.exit(0 if '6. Observable behaviors' in heading and '7. Domain invariants' not in heading and 'trace' in s['properties'] else 1)
PY
check "hosted: section 13 built by the driver"     grep -q '| R-1 | B-1, B-2 | I-1 | C-1 | T-1 | none |' "$TMP/ok/plan.md"
check "hosted: the model was assembled"            test -s "$parts/model.json"
check "hosted: the model has the same plan"        python3 - "$parts/model.json" "$TMP/ok/plan.md" <<'PY'
import collections, json, os, sys
sys.path.insert(0, os.environ['ROOT_DIR'] + '/scripts/lib')
import plan_model as pm
model = json.load(open(sys.argv[1]))
want = collections.Counter(pm.words(open(sys.argv[2]).read().split('## Verification commands')[0]))
got = collections.Counter(pm.words(pm.render(model)))
ok = not (want - got) and not (got - want) and pm.validate(model)[0] == []
sys.exit(0 if ok else 1)
PY
check "hosted: the driver built section 13 as typed rows" python3 - "$parts/model.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
kinds = {b.get('row_kind') for s in m['sections'] for b in s['blocks'] if b['kind'] == 'rows'}
sys.exit(0 if 'traceability' in kinds else 1)     # section 13, built from the workers' trace data
PY

run_case local ok local
w="$TMP/local/.uncle/workflow"
check "local: plan assembled"                      test "$(cat "$w/rc")" == 0
check "local: packet path, no schema flag"         bash -c '! grep -q "schema=/\|schema=.*schemas" "$1" && grep -q "out=none" "$1"' _ "$w/calls"
check "local: a prompt names exactly one packet kind" bash -c 'for k in outline behaviors; do test "$(grep "^$k " "$1" | grep -o "project-plan-[a-z-]*packet" | sort -u | wc -l | tr -d " ")" == 1 || exit 1; done' _ "$w/calls"

run_case bad badpacket hosted
check "bad packet: refused after one retry, nothing left" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/plan.md" && test "$(grep -c "^commands" "$1/.uncle/workflow/order")" == 2' _ "$TMP/bad"

run_case lane lane hosted
check "section out of lane: refused, nothing left" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/plan.md"' _ "$TMP/lane"
check "blocks are the default"                     grep -qF 'WORKFLOW_PLAN_BLOCKS:-1' "$ROOT/scripts/stagegate.sh"

[[ "$fails" == 0 ]] && echo "project-plan-blocks-driver-test.sh: all checks passed" || exit 1
