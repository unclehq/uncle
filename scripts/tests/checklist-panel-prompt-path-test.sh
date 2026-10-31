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
mkdir -p "$STATE_DIR/documents"
CODEX_EFFORT_CHECKLIST=low
# Stub only the external runner; exercise template resolution and packet
# collation with the real panel code from a separate project directory.
uncle_stage_runner() { echo codex; }
run_codex() {
    local id
    case "$3" in
        *coverage) id=MC-100 ;;
        *invariants) id=MC-200 ;;
        *resources) id=MC-300 ;;
        *regressions) id=MC-400 ;;
        *) return 1 ;;
    esac
    printf '{"schema":"uncle.artifact/v1","kind":"manual-checklist-worker-packet","checks":[{"id":"%s","exact_action":"Check %s","expected_result":"Greeting visible"}]}\n' "$id" "$id" > "$2"
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
WORKFLOW_MANUAL_CHECKLIST_PANEL=1 run_checklist_panel base prompts/change/manual-checklist-base.md
[[ "$CHECKLIST_PANEL_DIRECT" == 1 ]]
cp "$CHECKLIST_PANEL_PROMPT" panel-out.json
EOF

bash harness.sh
grep -q '.' synthesis-out.md
diff synthesis-out.md "$ROOT/prompts/change/manual-checklist-base.md"
python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json panel-out.json
[[ "$(jq '.checks | length' panel-out.json)" == 4 ]]
echo 'checklist-panel-prompt-path-test.sh: run_checklist_panel resolves its template against ROOT, not cwd'
