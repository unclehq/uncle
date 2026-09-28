#!/usr/bin/env bash
# A self-hosted stage already gets its own delivery contract from
# self_hosted.py's delivery_notice, pointing at the disposable staged copy.
# The shell driver used to unconditionally append a second, conflicting
# contract naming the live tree's $agent_delivery path -- outside that
# sandbox, so the model's Write there was denied. A real run tried that
# denied path, then narrated success without writing anywhere, and the
# stage failed with "plan agent did not write canonical JSON delivery".
#
# This extracts the real case block that builds $effective_prompt (not a
# reimplementation) and runs it standalone for both runner kinds. The block
# is located by the unique runner check inside it, not by position, so it
# does not silently start testing the wrong case statement if the file
# around it changes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0 FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

# extract_case SCRIPT ANCHOR -- the "case ... esac" block (8-space indent)
# that encloses the unique line ANCHOR.
extract_case() {
    local script="$1" anchor="$2" start end
    start="$(awk -v a="$anchor" '
        index($0, a) { print start; exit }
        /case "\$log_name" in/ { start = NR }
    ' "$ROOT/scripts/$script")"
    end="$(awk -v s="$start" 'NR>=s && /^        esac$/ { print NR; exit }' "$ROOT/scripts/$script")"
    [[ -n "$start" && -n "$end" ]] || { echo "extract_case: could not locate block for $anchor in $script" >&2; return 1; }
    sed -n "${start},${end}p" "$ROOT/scripts/$script"
}

run_block() { # run_block <script> <anchor> <runner> <log_name>
    local script="$1" anchor="$2" runner="$3" log_name="$4" work
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' RETURN
    {
        printf 'set -euo pipefail\n'
        printf 'log_name=%q\n' "$log_name"
        printf 'agent_delivery=%q\n' "$work/agent-delivery.json"
        printf 'artifact_error=%q\n' "previous rejection reason"
        printf 'UNCLE_RESOLVED_RUNNER=%q\n' "$runner"
        printf 'effective_prompt=%q\n' "$work/prompt.md"
        printf ': > "$effective_prompt"\n'
        extract_case "$script" "$anchor"
        printf 'cat "$effective_prompt"\n'
    } > "$work/harness.sh"
    bash "$work/harness.sh"
}

check_script() { # check_script <script> <anchor> <log_name>
    local script="$1" anchor="$2" log_name="$3" out

    out="$(run_block "$script" "$anchor" self-hosted "$log_name" 2>&1)"
    case "$out" in
        *"Canonical artifact contract"*) bad "$script-self-hosted-no-contract" "self-hosted still got the live-path contract: $out" ;;
        *) ok ;;
    esac

    out="$(run_block "$script" "$anchor" claude "$log_name" 2>&1)"
    case "$out" in
        *"Canonical artifact contract"*) ok ;;
        *) bad "$script-hosted-keeps-contract" "a hosted runner lost its delivery contract: $out" ;;
    esac
    case "$out" in
        *"previous rejection reason"*) ok ;;
        *) bad "$script-hosted-keeps-retry-error" "a hosted runner's retry error text was dropped: $out" ;;
    esac
}

check_script stagegate.sh 'UNCLE_RESOLVED_RUNNER:-}" != self-hosted' requirements
check_script change-workflow.sh 'UNCLE_RESOLVED_RUNNER:-}" == self-hosted' updated-change-plan

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "self-hosted-delivery-contract-test.sh: $FAIL of $((PASS + FAIL)) checks FAILED"
    exit 1
fi
echo "self-hosted-delivery-contract-test.sh: $PASS checks passed"
