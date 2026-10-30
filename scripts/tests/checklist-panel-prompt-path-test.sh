#!/usr/bin/env bash
# run_checklist_panel's synthesis prompt names its source template as a bare
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

mkdir -p "$work/project" "$work/project/.uncle/workflow/logs"
cd "$work/project"

cat > harness.sh <<'EOF'
set -euo pipefail
STATE_DIR=.uncle/workflow
LOG_DIR=.uncle/workflow/logs
mkdir -p "$STATE_DIR/documents"
CODEX_EFFORT_CHECKLIST=low
# The worker-packet panel (WORKFLOW_MANUAL_CHECKLIST_PANEL=1, the default)
# no longer does prompt-template synthesis at all for the "base" pass -- it
# renders a JSON checklist document directly (CHECKLIST_PANEL_DIRECT=1) and
# never touches CHECKLIST_PANEL_PROMPT as a Markdown template; that is what
# the panel's own worker/packet tests cover. The relative-path bug this test
# exists for is the one line in run_checklist_panel that runs unconditionally
# before that fork: resolve_prompt(source). Disabling the panel isolates
# exactly that line, which is all this test is about.
WORKFLOW_MANUAL_CHECKLIST_PANEL=0
EOF
awk '/^resolve_prompt\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^run_checklist_panel\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
cat >> harness.sh <<'EOF'
run_checklist_panel base prompts/change/manual-checklist-base.md
cp "$CHECKLIST_PANEL_PROMPT" synthesis-out.md
EOF

bash harness.sh
grep -q '.' synthesis-out.md
diff synthesis-out.md "$ROOT/prompts/change/manual-checklist-base.md"
echo 'checklist-panel-prompt-path-test.sh: run_checklist_panel resolves its template against ROOT, not cwd'
