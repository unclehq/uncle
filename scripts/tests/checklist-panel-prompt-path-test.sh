#!/usr/bin/env bash
# run_checklist_panel's fallback prompt names its source template as a bare
# relative path ("prompts/change/manual-checklist-base.md"), which is only
# meaningful relative to the uncle installation (ROOT). change-workflow.sh
# runs with the project under change (PROJECT_ROOT) as its cwd throughout,
# including inside this function's background subshell -- a real run against
# any project other than uncle's own repo hit exactly this: `cp` failed with
# "No such file or directory" because ROOT and PROJECT_ROOT are different
# directories there. Exercise the real function with cwd deliberately set to
# a directory that is not ROOT, the way every real project run actually is.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ROOT

mkdir -p "$work/project" "$work/project/.uncle/workflow/logs" "$work/project/.uncle/workflow/documents"
cd "$work/project"

cat > harness.sh <<'EOF'
set -euo pipefail
STATE_DIR=.uncle/workflow
LOG_DIR=.uncle/workflow/logs
CODEX_EFFORT_CHECKLIST=low
uncle_stage_runner() { echo codex; }
run_codex() {
    # Return a valid worker packet; prompt resolution is asserted from the
    # resulting synthesis template below.
    local prompt_file="$1" output_file="$2"
    local id
    id="$(grep -o 'MC-[0-9]* through' "$prompt_file" | head -1 | cut -d' ' -f1)"
    printf '{"schema":"uncle.artifact/v1","kind":"manual-checklist-worker-packet","checks":[{"id":"%s","exact_action":"Observe the greeting","expected_result":"Greeting visible"}]}\n' "$id" > "$output_file"
}
EOF
printf '%s\n' '. "$ROOT/scripts/lib/workflow-paths-change.sh"' >> harness.sh
awk '/^checklist_worker_codex\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^run_checklist_panel\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
cat >> harness.sh <<'EOF'
# Without a panel, the parent consumes the resolved template directly.
WORKFLOW_MANUAL_CHECKLIST_PANEL=0 run_checklist_panel base prompts/change/manual-checklist-base.md
cp "$CHECKLIST_PANEL_PROMPT" synthesis-out.md
# With a panel, workers now deliver collated canonical JSON, not a synthesis
# prompt. Both paths must work with cwd outside the installation.
run_checklist_panel base prompts/change/manual-checklist-base.md
[[ "$CHECKLIST_PANEL_DIRECT" == 1 ]]
cp "$CHECKLIST_PANEL_PROMPT" panel-out.json
EOF

bash harness.sh
grep -q '.' synthesis-out.md
head -n1 "$ROOT/prompts/change/manual-checklist-base.md" > expected-first-line
diff <(head -n1 synthesis-out.md) expected-first-line
diff "$ROOT/prompts/change/manual-checklist-base.md" synthesis-out.md
python3 - <<'PY'
import json
packet = json.load(open('panel-out.json'))
assert packet['kind'] == 'manual-checklist'
assert [row['id'] for row in packet['checks']] == ['MC-100', 'MC-200', 'MC-300', 'MC-400']
assert packet == json.load(open('.uncle/workflow/documents/MANUAL_CHECKLIST_WORKERS.json'))
PY
echo 'checklist-panel-prompt-path-test.sh: run_checklist_panel resolves its template against ROOT, not cwd'
