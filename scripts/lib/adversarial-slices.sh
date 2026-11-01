# Private units retain the existing reviewer, admission pool, and publication barrier.
run_adversarial_review_slice() {
    local directory="$1" lens="$2" index="$3" mode="$4" prompt output name pid error
    prompt="$directory/slices/prompts/$lens-$index.md"
    output="$directory/slices/$lens-$index.json"
    name="adversarial-review-worker-$lens-slice-$index"
    export UNCLE_ADVERSARIAL_SLICE=1
    workflow_model_enter adversarial-review REVIEWER || return 1
    (
        if [[ "$mode" == change ]]; then
            UNCLE_NONINTERACTIVE=1 run_codex "$prompt" "$output" "$name" "$CODEX_EFFORT_REVIEW" < /dev/null
        else
            UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "$name" < /dev/null
        fi
    ) &
    pid=$!
    wait "$pid" || true
    if ! error="$(python3 -B "$ROOT/scripts/lib/adversarial_slices.py" validate "$output" 2>&1)"; then
        printf '\n## Required retry\n\nThe preceding packet was rejected: %s\nReturn one complete adversarial-review-worker-packet JSON object for this assigned unit.\n' "$error" >> "$prompt"
        rm -f "$output" "$output.delivery.json"
        (
            if [[ "$mode" == change ]]; then
                UNCLE_NONINTERACTIVE=1 run_codex "$prompt" "$output" "$name-retry" "$CODEX_EFFORT_REVIEW" < /dev/null
            else
                UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "$name-retry" < /dev/null
            fi
        ) &
        pid=$!
        wait "$pid" || true
        python3 -B "$ROOT/scripts/lib/adversarial_slices.py" validate "$output" || return 1
    fi
}

run_adversarial_review_slices() {
    local directory="$1" plan="$2" context="$3" count="$4" mode="$5" lens index pid failed=0
    local -a pids=()
    . "$ROOT/scripts/lib/model-jobs.sh"
    python3 -B "$ROOT/scripts/lib/adversarial_slices.py" prepare "$directory" "$plan" "$context" "$count" || return 1
    for lens in requirements regression security testability; do
        for ((index=1; index<=count; index++)); do
            ( run_adversarial_review_slice "$directory" "$lens" "$index" "$mode" ) \
                > "$LOG_DIR/adversarial-review-worker-$lens-slice-$index.log" 2>&1 &
            pids+=("$!")
        done
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || failed=1
    done
    for lens in requirements regression security testability; do
        for ((index=1; index<=count; index++)); do
            cat "$LOG_DIR/adversarial-review-worker-$lens-slice-$index.log"
        done > "$LOG_DIR/adversarial-review-worker-$lens.log"
    done
    [[ "$failed" == 0 ]] || return 1
    python3 -B "$ROOT/scripts/lib/adversarial_slices.py" merge "$directory" "$count" --runner "$(workflow_model_runner adversarial-review REVIEWER)"
}
