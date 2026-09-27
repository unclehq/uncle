#!/usr/bin/env bash
# run_checklist_panel on a self-hosted (local model) runner.
#
# 1. Serial workers never fill `pids`; the wait loop over the empty array
#    died on bash 3.2 with "pids[@]: unbound variable" (issue 97 run).
# 2. Each local worker spent 17-40 turns re-reading four small canonical JSON
#    files; the inputs are now inlined, read tools withheld, and turns capped.
# 3. The base panel no longer runs alongside implementation on a self-hosted
#    endpoint, where it only slows the stage the run is waiting on.
# Hosted runners keep their read-based prompt and background fan-out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ROOT
PASS=0 FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

extract() { awk -v fn="$1" '$0 == fn "() {" {p=1} p {print} p && /^}$/ {exit}' "$ROOT/scripts/change-workflow.sh"; }

run_panel() { # run_panel <runner> <project dir>
    local runner="$1" project="$2"
    mkdir -p "$project/.uncle/workflow/logs" "$project/.uncle/workflow/documents"
    local doc
    for doc in BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW; do
        printf '{"schema":"uncle.artifact/v1","kind":"doc","marker":"MARKER-%s"}\n' "$doc" \
            > "$project/.uncle/workflow/documents/$doc.json"
    done
    {
        cat <<EOF
set -euo pipefail
STATE_DIR=.uncle/workflow
LOG_DIR=.uncle/workflow/logs
CODEX_EFFORT_CHECKLIST=low
uncle_stage_runner() { printf '%s' "$runner"; }
EOF
        cat <<'EOF'
run_codex() {
    local prompt="$1" output="$2" lens id
    lens="$(basename "$output" .json)"
    printf '%s|%s|%s\n' "$lens" "${UNCLE_INLINE_INPUTS:-}" "${UNCLE_WORKER_MAX_TURNS:-}" >> calls
    cp "$prompt" "seen-$lens.md"
    id="$(grep -o 'MC-[0-9]* through' "$prompt" | head -1 | cut -d' ' -f1)"
    printf '{"schema":"uncle.artifact/v1","kind":"manual-checklist-worker-packet","checks":[{"id":"%s","exact_action":"a","expected_result":"b"}]}\n' "$id" > "$output"
}
EOF
        extract resolve_prompt
        extract checklist_worker_codex
        extract run_checklist_panel
        printf 'run_checklist_panel base prompts/change/manual-checklist-base.md\necho PANEL_OK\n'
    } > "$project/harness.sh"
    (cd "$project" && bash harness.sh 2>&1)
}

# --- self-hosted --------------------------------------------------------
out="$(run_panel self-hosted "$work/local" || true)"
case "$out" in *"unbound variable"*) bad sh-no-crash "serial panel crashed: $out" ;; *) ok ;; esac
case "$out" in *PANEL_OK*) ok ;; *) bad sh-completes "panel did not complete: $out" ;; esac
for lens in coverage invariants resources regressions; do
    grep -qx "$lens|1|10" "$work/local/calls" 2>/dev/null && ok \
        || bad "sh-env-$lens" "expected inline inputs and a 10-turn cap for $lens; got: $(cat "$work/local/calls" 2>/dev/null)"
done
for doc in BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW; do
    grep -q "MARKER-$doc" "$work/local/seen-regressions.md" 2>/dev/null && ok \
        || bad "sh-inlined-$doc" "$doc was not inlined into the worker prompt"
done
grep -q 'Do not call Read' "$work/local/seen-coverage.md" 2>/dev/null && ok \
    || bad sh-no-read "the inline prompt does not forbid reading"

# --- hosted runner: unchanged read-based contract -------------------------
out="$(run_panel codex "$work/hosted" || true)"
case "$out" in *PANEL_OK*) ok ;; *) bad hosted-completes "hosted panel did not complete: $out" ;; esac
grep -qx "coverage||" "$work/hosted/calls" 2>/dev/null && ok \
    || bad hosted-env "hosted workers must not get the self-hosted limits: $(cat "$work/hosted/calls" 2>/dev/null)"
if grep -q MARKER- "$work/hosted/seen-coverage.md" 2>/dev/null; then
    bad hosted-not-inlined "hosted worker prompt was inlined"
else ok; fi

# --- base panel does not overlap implementation on self-hosted -------------
{
    printf 'set -euo pipefail\n'
    printf 'uncle_stage_runner() { printf "%%s" "$RUNNER"; }\n'
    extract checklist_base_overlaps_implementation
} > "$work/overlap.sh"
RUNNER=self-hosted bash -c ". '$work/overlap.sh'; checklist_base_overlaps_implementation" \
    && bad overlap-local "self-hosted base panel still overlaps implementation" || ok
RUNNER=codex bash -c ". '$work/overlap.sh'; checklist_base_overlaps_implementation" \
    && ok || bad overlap-hosted "hosted base panel no longer overlaps implementation"
# Both call sites must consult it: the IMPLEMENT start and the deferred start.
[[ "$(grep -c 'checklist_base_overlaps_implementation' "$ROOT/scripts/change-workflow.sh")" -ge 3 ]] && ok \
    || bad overlap-callers "IMPLEMENT start and deferred start must both use checklist_base_overlaps_implementation"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "checklist-panel-self-hosted-test.sh: $FAIL of $((PASS + FAIL)) checks FAILED"
    exit 1
fi
echo "checklist-panel-self-hosted-test.sh: $PASS checks passed"
