#!/usr/bin/env bash
# Run the updated-change-plan stage while the operator reads the plan gate.
#
# The greenfield driver has had this for a while (stagegate.sh:1504): start the
# next stage during a gate, keep the result only if the gated bytes are
# unchanged at approval. The change driver could not reuse it directly, because
# its updated-change-plan stage revises CHANGE_PLAN.md *in place* -- the very
# file the gate is hashing and the operator is reading. Speculating it against
# the live tree would rewrite a document mid-review and then discard the work.
#
# So the speculative run happens in a sandbox: a git worktree mirroring the tree
# plus its uncommitted overlay, which triage_guard.make_sandbox already builds
# for recovery. The stage revises CHANGE_PLAN.md there. On adoption the file is
# copied back, and only when the gate's inputs hash the same as when the run
# started. If anything changed, the sandbox is dropped and the stage runs
# normally, exactly as if speculation had never happened.
#
# Nothing here can make a gate pass. It only decides whether work already done
# is reusable.

SPEC_DIR="${SPEC_DIR:-$STATE_DIR/speculative}"
SPEC_TREE="$SPEC_DIR/tree"
WORKFLOW_SPECULATE="${WORKFLOW_SPECULATE:-1}"

spec_pid=""
spec_stage=""

# Called from the driver's EXIT trap: a speculative stage must never outlive the
# run that started it.
cancel_speculation() {
    if [[ -n "$spec_pid" ]] && kill -0 "$spec_pid" 2>/dev/null; then
        echo "Cancelling speculative $spec_stage..."
        kill "$spec_pid" 2>/dev/null || true
        wait "$spec_pid" 2>/dev/null || true
    fi
    spec_pid=""
    spec_stage=""
    [[ -d "$SPEC_TREE" ]] && speculation_drop_tree
    return 0
}

speculation_drop_tree() {
    python3 - "$PROJECT_ROOT" "$SPEC_TREE" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, __import__('os').environ['ROOT'] + '/scripts/lib')
from triage_guard import drop_sandbox
drop_sandbox(sys.argv[1], sys.argv[2])
PY
}

# speculate_updated_plan <gate_file>...  -- the files the gate hashes.
speculate_updated_plan() {
    [[ "$WORKFLOW_SPECULATE" == "1" ]] || return 0
    [[ -z "$spec_pid" ]] || return 0
    local file
    for file in "$@"; do
        [[ -s "$file" ]] || return 0
    done

    mkdir -p "$SPEC_DIR" || return 0
    if ! ROOT="$ROOT" python3 - "$PROJECT_ROOT" "$SPEC_TREE" <<'PY'
import sys
sys.path.insert(0, __import__('os').environ['ROOT'] + '/scripts/lib')
from triage_guard import make_sandbox
make_sandbox(sys.argv[1], sys.argv[2])
PY
    then
        echo "Speculation unavailable: could not mirror the working tree."
        return 0
    fi

    # The hash of every gated file, so adoption can prove nothing moved.
    : > "$SPEC_DIR/updated-change-plan.input"
    for file in "$@"; do
        printf '%s  %s\n' "$(hash_file "$file")" "$file" >> "$SPEC_DIR/updated-change-plan.input"
    done

    echo "Drafting the updated plan in the background while you review."
    echo "It is used only if the documents above are unchanged at approval."

    (
        cd "$SPEC_TREE" || exit 1
        UNCLE_SPECULATIVE=true UNCLE_PROJECT_ROOT="$SPEC_TREE" \
            run_claude prompts/change/updated-change-plan.md updated-change-plan \
                "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" 60 "$BUDGET_UPDATED_PLAN"
    ) > "$LOG_DIR/updated-change-plan.speculative.log" 2>&1 < /dev/null &
    spec_pid=$!
    spec_stage="updated-change-plan"
}

# Succeeds when the speculative plan is in place and usable, so the caller can
# skip the stage. Fails for every other reason, leaving the tree untouched.
adopt_updated_plan() {
    local status=0 file recorded current
    [[ "$spec_stage" == "updated-change-plan" ]] || return 1

    echo
    echo "Waiting for the updated plan drafted during review..."
    wait "$spec_pid" || status=$?
    spec_pid=""
    spec_stage=""

    if [[ "$status" -ne 0 ]]; then
        echo "Speculative updated plan failed (status $status). Running it again."
        echo "Log: $LOG_DIR/updated-change-plan.speculative.log"
        speculation_drop_tree
        return 1
    fi

    while read -r recorded file; do
        current="$(hash_file "$file" 2>/dev/null || true)"
        if [[ "$recorded" != "$current" ]]; then
            echo "$file changed during review. Discarding the speculative plan."
            speculation_drop_tree
            return 1
        fi
    done < "$SPEC_DIR/updated-change-plan.input"

    if [[ ! -s "$SPEC_TREE/CHANGE_PLAN.md" ]]; then
        echo "Speculative updated plan produced no document. Running it again."
        speculation_drop_tree
        return 1
    fi

    cp "$SPEC_TREE/CHANGE_PLAN.md" CHANGE_PLAN.md || { speculation_drop_tree; return 1; }
    speculation_drop_tree
    echo "Adopted the updated plan drafted during review — inputs unchanged."
    echo "Log: $LOG_DIR/updated-change-plan.speculative.log"
    return 0
}
