#!/usr/bin/env bash
# When the four lens workers all return valid packets, run_checklist_panel
# merges them itself and sets CHECKLIST_PANEL_DIRECT=1 -- the fast path a real
# run with a real model takes every time. start_codex_bg then exits the
# background subshell immediately, so the reviewer CLI never runs and
# .uncle/workflow/logs/manual-checklist-base.log is never created.
#
# Two things downstream assumed that log and a rendered view exist anyway:
#
#   record_codex_cost   ran `jq ... "$log"` unguarded. Under `set -euo
#                       pipefail` a missing file is jq exit 2, which killed
#                       the driver at the end of IMPLEMENT, after the whole
#                       implementation had already been paid for.
#   MANUAL_CHECKLIST.base.md
#                       is required by wait_codex_bg, by the CHECKLIST state,
#                       and by manual-checklist-context.py, but the panel
#                       only rendered a view for the delta pass.
#
# The existing panel tests stub run_codex with `"findings":[]`, which is not a
# valid checklist packet, so every one of them takes the non-direct path and
# none of them ever reached this. Use real packets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ROOT

mkdir -p "$work/project/.uncle/workflow/logs" "$work/project/.uncle/workflow/documents"
cd "$work/project"

cat > harness.sh <<'EOF'
set -euo pipefail
STATE_DIR=.uncle/workflow
LOG_DIR=.uncle/workflow/logs
LEDGER_FILE=.uncle/workflow/cost.tsv
CODEX_EFFORT_CHECKLIST=low

# A hosted runner, so the panel keeps its concurrent fan-out.
uncle_stage_runner() { printf 'claude'; }

# Every worker returns one valid check in its own assigned ID range, which is
# what a real lens worker delivers and what makes the merge succeed.
run_codex() {
    local prompt_file="$1" output_file="$2" stage="$3" id=100
    case "$stage" in
        *coverage*)    id=100 ;;
        *invariants*)  id=200 ;;
        *resources*)   id=300 ;;
        *regressions*) id=400 ;;
    esac
    printf '{"schema":"uncle.artifact/v1","kind":"manual-checklist-worker-packet","checks":[{"id":"MC-%s","exact_action":"Open the page","expected_result":"Greeting visible"}]}\n' "$id" > "$output_file"
}
EOF
awk '/^resolve_prompt\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^record_cost\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^record_codex_cost\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
awk '/^run_checklist_panel\(\)/{p=1} p{print} p && /^}$/{exit}' "$ROOT/scripts/change-workflow.sh" >> harness.sh
cat >> harness.sh <<'EOF'
run_checklist_panel base prompts/change/manual-checklist-base.md
printf '%s\n' "${CHECKLIST_PANEL_DIRECT:-0}" > direct-flag

# The driver reaches this with the reviewer log absent, because the fast path
# above returned before any reviewer was launched.
[[ -e "$LOG_DIR/manual-checklist-base.log" ]] && { echo "fixture wrong: a reviewer log exists" >&2; exit 1; }
record_codex_cost manual-checklist-base 3
printf 'survived\n' > cost-survived
EOF

status=0
bash harness.sh || status=$?

fail() { echo "checklist-base-direct-path-test.sh: FAIL: $*" >&2; exit 1; }

[[ "$status" == 0 ]] || fail "the panel fast path exited $status (jq on a missing reviewer log is exit 2)"
[[ "$(cat direct-flag 2>/dev/null || true)" == 1 ]] || fail 'valid worker packets should take the direct merge path'
[[ -s cost-survived ]] || fail 'record_codex_cost did not survive a missing reviewer log'
[[ -s .uncle/workflow/documents/MANUAL_CHECKLIST.base.json ]] || fail 'merged canonical checklist missing'
[[ -s .uncle/workflow/MANUAL_CHECKLIST.base.md ]] || fail 'the direct path must render MANUAL_CHECKLIST.base.md; wait_codex_bg and the CHECKLIST state both require it'
grep -q 'MC-100' .uncle/workflow/MANUAL_CHECKLIST.base.md || fail 'rendered base checklist lost its checks'
grep -q 'MC-400' .uncle/workflow/MANUAL_CHECKLIST.base.md || fail 'rendered base checklist lost a lens'

echo 'checklist-base-direct-path-test.sh: the checklist-base fast path renders its view and survives a missing reviewer log'
