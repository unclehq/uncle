#!/usr/bin/env bash
# codex's workspace-write sandbox denies loopback binds, so a stage that has to
# serve the product it verifies needs network access turned on deliberately.
# Default off: the boundary is the point.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
UNCLE_CONFIG="$work/config"

# Absent config, absent key, and an explicit false all mean no network.
for stage in requirements preflight implementation execute-checklist final-audit; do
    rm -f "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    printf 'other-stage.network true\n' > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    printf '%s.network false\n' "$stage" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# Every spelling an operator is likely to write.
for value in true TRUE yes on 1; do
    printf 'execute-checklist.network %s\n' "$value" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network execute-checklist)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# Anything unrecognized stays off rather than guessing in the risky direction.
for value in maybe '' 0 no off; do
    printf 'execute-checklist.network %s\n' "$value" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network execute-checklist)" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# A global key is the fallback, a stage key wins over it.
printf 'network true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf 'implementation.network false\nnetwork true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation)" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# Step variants inherit the parent stage's setting.
printf 'implementation.network true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation-step-3)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# Status reporting has different signatures and variant lookup in each family.
. "$ROOT/scripts/tests/workflow_fixture.sh"
for family in app change; do
    (
        workflow_fixture_source "$ROOT/scripts/lib/stage-runtime.sh" \
            "$ROOT/scripts/lib/stage-runtime-$family.sh"
        STATUS_STAGE_SEQ='implementation manual-checklist'
        UNCLE_STATUS_FILE="$work/$family status.json"
        stage_turns() { printf 17; }
        uncle_stage_network() { printf '%s' "$1"; }
        check_context() {
            local expected_stage="$1" expected_index="$2" expected_turns="$3"
            local expected_network="$4" expected_model="$5" expected_mode="$6"
            # A child must receive the exports, not just values in this shell.
            [[ "$(bash -c 'printf "%s|%s|%s|%s|%s" "${UNCLE_STATUS_STAGE-}" "${UNCLE_STATUS_STAGE_INDEX-}" "${UNCLE_STATUS_STAGE_TOTAL-}" "${UNCLE_STATUS_STAGE_TURNS-}" "${UNCLE_STAGE_NETWORK-}"')" == \
                "$expected_stage|$expected_index|2|$expected_turns|$expected_network" ]] \
                || { echo "FAIL $family status exports for $expected_stage" >&2; exit 1; }
            printf '{"event":"start","model":"%s","mode":"%s","stage":"%s","stage_index":%s,"stage_total":2,"stage_turns":%s}\n' \
                "$expected_model" "$expected_mode" "$expected_stage" "$expected_index" "$expected_turns" \
                > "$work/expected-$family.json"
            cmp -s "$work/expected-$family.json" "$UNCLE_STATUS_FILE" \
                || { echo "FAIL $family status bytes for $expected_stage" >&2; exit 1; }
        }
        for stage in implementation implementation-step-3 manual-checklist manual-checklist-base manual-checklist-delta; do
            : > "$UNCLE_STATUS_FILE"
            if [[ "$family" == app ]]; then
                case "$stage" in implementation) index=1 ;; manual-checklist) index=2 ;; *) index=0 ;; esac
                status_stage_context "$stage" fixture-model plan
                check_context "$stage" "$index" 17 "$stage" fixture-model plan
            else
                case "$stage" in
                    implementation|implementation-step-3) index=1; network_stage=implementation ;;
                    *) index=2; network_stage=manual-checklist ;;
                esac
                status_stage_context "$stage" 23 fixture-model plan
                check_context "$stage" "$index" 23 "$network_stage" fixture-model plan
            fi
        done
        : > "$UNCLE_STATUS_FILE"
        status_stage_context implementation
        if [[ "$family" == app ]]; then turns=17; else turns=0; fi
        check_context implementation 1 "$turns" implementation '(runner default)' act
    )
done

echo 'stage-network-test.sh: network defaults, inheritance, and family status signatures/exports/event bytes passed'
