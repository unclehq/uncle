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
CODEX_EFFORT_CHECKLIST=low
run_codex() {
    # The stub reviewer: proves it received the real template's content by
    # copying its first line into the packet, exactly as run_codex is
    # trusted to invoke the model with whatever prompt file it is given.
    local prompt_file="$1" output_file="$2"
    head -n1 "$prompt_file" > "$output_file"
}
EOF
awk '/^resolve_prompt\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^run_checklist_panel\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
cat >> harness.sh <<'EOF'
run_checklist_panel base prompts/change/manual-checklist-base.md
cp "$CHECKLIST_PANEL_PROMPT" synthesis-out.md
EOF

bash harness.sh
grep -q '.' synthesis-out.md
head -n1 "$ROOT/prompts/change/manual-checklist-base.md" > expected-first-line
diff <(head -n1 synthesis-out.md) expected-first-line
grep -q 'Specialist checklist packets' synthesis-out.md
echo 'checklist-panel-prompt-path-test.sh: run_checklist_panel resolves its template against ROOT, not cwd'
