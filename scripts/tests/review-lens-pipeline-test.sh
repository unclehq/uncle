#!/usr/bin/env bash
# A fast failed lens retries before a slow lens completes; final collation waits.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
awk '/^(run_adversarial_review_lens|run_adversarial_review_panel)\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/functions.sh"
. "$TMP/functions.sh"
ensure_project_plan_json() { return 0; }
# Only the final renderer is replaced. Packet validation and collation are real.
python3() {
    if [[ "${2:-}" == "$ROOT/scripts/lib/adversarial_packets.py" ]]; then
        [[ -e "$STATE_DIR/slow-finished" && -e "$STATE_DIR/retried" ]] || return 1
        touch "$STATE_DIR/published"
    else
        command python3 "$@"
    fi
}
run_codex_review() {
    local prompt="$1" output="$2" name="$3" i=0
    printf '%s\n' "$name" >> "$STATE_DIR/calls"
    case "$name" in
        adversarial-review-worker-regression)
            printf 'invalid json' > "$output"; return 1 ;;
        adversarial-review-worker-regression-retry)
            [[ ! -e "$STATE_DIR/slow-finished" ]] || return 1
            [[ ! -e "$STATE_DIR/published" ]] || return 1
            touch "$STATE_DIR/retried"
            if [[ "$mode" == failed ]]; then printf 'still invalid' > "$output"; return 1; fi
            ;;
        adversarial-review-worker-testability)
            # Deterministic rendezvous: the old all-workers barrier times out.
            while [[ ! -e "$STATE_DIR/retried" && "$i" -lt 100 ]]; do
                sleep .05; i=$((i+1))
            done
            [[ -e "$STATE_DIR/retried" ]] || return 1
            [[ ! -e "$STATE_DIR/published" ]] || return 1
            touch "$STATE_DIR/slow-finished"
            ;;
    esac
    printf '{"schema":"uncle.artifact/v1","kind":"adversarial-review-worker-packet","findings":[]}' > "$output"
}
for mode in success failed; do
    STATE_DIR="$TMP/$mode"; LOG_DIR="$STATE_DIR/logs"
    mkdir -p "$LOG_DIR" "$STATE_DIR/documents"
    if run_adversarial_review_panel; then status=0; else status=$?; fi
    [[ -e "$STATE_DIR/retried" && -e "$STATE_DIR/slow-finished" ]]
    [[ "$(wc -l < "$STATE_DIR/calls" | tr -d ' ')" == 5 ]]
    if [[ "$mode" == success ]]; then
        [[ "$status" == 0 && -e "$STATE_DIR/published" ]]
        command python3 - "$STATE_DIR/documents/ADVERSARIAL_REVIEW_WORKERS.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert [w['source'] for w in p['workers']] == ['requirements','regression','security','testability']
assert all(w['status']=='ok' for w in p['workers'])
PY
    else
        [[ "$status" != 0 && ! -e "$STATE_DIR/published" ]]
        [[ ! -e "$STATE_DIR/documents/ADVERSARIAL_REVIEW_WORKERS.json" ]]
    fi
done
# Preserve the first reviewer's errexit boundary, even though the coordinator
# must still validate/retry a packet from an unsuccessful reviewer process.
STATE_DIR="$TMP/errexit"; mkdir -p "$STATE_DIR/prompts"
printf 'prompt\n' > "$STATE_DIR/prompts/regression.md"
run_codex_review() {
    if [[ "$3" != *-retry ]]; then
        false
        touch "$STATE_DIR/errexit-was-disabled"
    fi
    printf '{"schema":"uncle.artifact/v1","kind":"adversarial-review-worker-packet","findings":[]}' > "$2"
}
run_adversarial_review_lens "$STATE_DIR" regression &
reviewer_test_pid=$!
wait "$reviewer_test_pid"
[[ ! -e "$STATE_DIR/errexit-was-disabled" ]]
[[ -s "$STATE_DIR/regression.json" ]]
printf 'Per-lens validation overlaps slow workers; one retry; failed panel cannot publish.\n'
