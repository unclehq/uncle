#!/usr/bin/env bash
# The prompt path handed to an isolated parallel worker.
#
# Workers run with their own sandbox as cwd, and the prompts deliberately live
# in the driver-owned workflow tree that sandboxes do not copy -- so the path
# has to be absolute. It was built as "$PWD/$STATE_DIR/parallel/prompts" while
# STATE_DIR is already "$PROJECT_ROOT/.uncle/workflow", putting the project
# root in twice:
#
#   /Users/brian/src/calculator//Users/brian/src/calculator/.uncle/workflow/...
#
# That exists nowhere. Every worker died before running with "parallel worker
# prompt missing", the fan-out reported "Steps failed: 1", and the stage left
# no report to point at -- a real greenfield build stopped at IMPLEMENT that
# way with nothing written.
#
# Two properties, and the doubling bug satisfies neither: the path must be
# absolute, and it must be the one the driver actually writes prompts into.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

FAILED=0
note() { echo "  $1"; }
fail() { echo "  FAIL: $1" >&2; FAILED=1; }

for driver in change-workflow.sh stagegate.sh; do
    line="$(grep -n 'export PARALLEL_PROMPT_DIR=' "$ROOT/scripts/$driver" | head -1)"
    [[ -n "$line" ]] || { fail "$driver no longer exports PARALLEL_PROMPT_DIR"; continue; }

    # The assignment, evaluated with the same shape the driver gives it.
    value="$(PROJECT_ROOT=/tmp/proj \
             STATE_DIR=/tmp/proj/.uncle/workflow \
             PWD=/tmp/proj \
             bash -c 'eval "$(grep -o "PARALLEL_PROMPT_DIR=.*" "$1" | head -1)"; printf "%s" "$PARALLEL_PROMPT_DIR"' _ "$ROOT/scripts/$driver")"

    case "$value" in
        /*) ;;
        *) fail "$driver builds a relative prompt dir ($value); workers run from a sandbox" ;;
    esac
    if [[ "$value" == *"/tmp/proj/tmp/proj"* || "$value" == *"//tmp/proj"* ]]; then
        fail "$driver doubles the project root: $value"
    fi
    [[ "$value" == "/tmp/proj/.uncle/workflow/parallel/prompts" ]] \
        && note "ok: $driver -> $value" \
        || fail "$driver built an unexpected path: $value"
done

# And the worker resolves what it is given, rather than re-deriving it.
worker="$ROOT/scripts/lib/parallel-agent.sh"
grep -q 'prompt="\${PARALLEL_PROMPT_DIR:-[^}]*}/step-\$step.md"' "$worker" \
    && note 'ok: the worker appends only the step file to what it is handed' \
    || fail 'the worker no longer takes PARALLEL_PROMPT_DIR as given'

# The failure this guards against, end to end: a missing prompt must refuse
# loudly rather than run a worker with no instruction.
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
out="$(PARALLEL_PROMPT_DIR="$work/absent" PARALLEL_AGENT_CMD=true \
       bash "$worker" 1 2>&1)"; status=$?
[[ "$status" == 2 ]] && note 'ok: a missing prompt exits 2' || fail "missing prompt exited $status, wanted 2"
printf '%s' "$out" | grep -q 'parallel worker prompt missing' \
    && note 'ok: and says so' || fail "unclear message: $out"

if [[ "$FAILED" == 0 ]]; then
    echo 'parallel-prompt-path-test.sh: the worker prompt path is absolute and unduplicated'
else
    echo 'parallel-prompt-path-test.sh: FAILED' >&2
fi
exit "$FAILED"
