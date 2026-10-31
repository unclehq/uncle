#!/usr/bin/env bash
# Stages that write or transcribe a document from inputs that are already decided do not need
# the model to think first. On Claude that thinking is about half a section worker's output
# tokens and half its wall clock (invariants worker: 4,257 -> 2,132 tokens, 27s -> 14s, same
# packet size), and `--effort low` does not turn it off.
#
# Judgment stays on: implementation, repair, adversarial-review, test-review, manual-checklist,
# final-audit, derive-brief, and project-plan-stage-duties (the whole-plan consistency check,
# which is what finds contradictions between independently written sections).
#
#   WORKFLOW_THINKING=on             restores thinking for every stage
#   WORKFLOW_THINKING_OFF_EXTRA      extra space-separated stage globs to switch off
#
# How it is switched off, per runner:
#   claude  MAX_THINKING_TOKENS=0 in the stage's environment.
#   codex   model_reasoning_effort=none, only if the model accepts it (many do not: gpt-6-astra
#           rejects `none` and `minimal` and starts at `low`).
#   kimi    KIMI_MODEL_THINKING_EFFORT=off (the shim's translation of effort `none`).
# Codex and Kimi are probed once per run and model with a one-word request; a runner that
# rejects the value keeps its configured effort, so this can never fail a stage.
#
# Sourcing this file defines functions and nothing else.

# uncle_stage_thinking_off <stage>: succeed when the stage should run without thinking.
uncle_stage_thinking_off() {
    local stage="$1" pattern frozen=0
    [[ "${WORKFLOW_THINKING:-auto}" != on ]] || return 1
    case "$stage" in
        requirements|requirements-investigate|project-plan|project-plan-investigate|project-plan-section-*) return 0 ;;
        updated-plan|updated-plan-*|updated-change-plan|updated-change-plan-*) return 0 ;;
        preflight|preflight-*|preview-build|preview-build-*|module-interfaces) return 0 ;;
        execute-checklist|execute-checklist-*) return 0 ;;
    esac
    # The operator's extra globs must not expand against the working directory.
    [[ $- == *f* ]] && frozen=1
    set -f
    for pattern in ${WORKFLOW_THINKING_OFF_EXTRA:-}; do
        # shellcheck disable=SC2254
        case "$stage" in $pattern) [[ "$frozen" == 1 ]] || set +f; return 0 ;; esac
    done
    [[ "$frozen" == 1 ]] || set +f
    return 1
}

# uncle_runner_accepts_no_thinking <runner> <model>: succeed when Codex or Kimi takes the
# no-thinking setting for this model. Cached for the run; a failed probe says "no".
uncle_runner_accepts_no_thinking() {
    local runner="$1" model="$2" dir="${STATE_DIR:-.uncle/workflow}/effort-none" key scratch out verdict=no
    key="$runner-$(printf '%s' "${model:-default}" | tr -c 'A-Za-z0-9._-' '_')"
    if [[ ! -s "$dir/$key" ]]; then
        mkdir -p "$dir"
        scratch="$(mktemp -d)"
        case "$runner" in
            codex)
                out="$(cd "$scratch" && "${WORKFLOW_CODEX_CMD:-codex}" exec --skip-git-repo-check \
                    ${model:+-m "$model"} -c model_reasoning_effort=none --json \
                    'Reply with the single word ok' </dev/null 2>&1)" || true
                if grep -q 'turn.completed' <<<"$out" && ! grep -q 'turn.failed' <<<"$out"; then verdict=yes; fi
                ;;
            kimi)
                model="${model#kimi:}"; [[ "$model" != kimi ]] || model=""
                out="$(cd "$scratch" && KIMI_MODEL_THINKING_EFFORT=off "${WORKFLOW_KIMI_CMD:-kimi}" \
                    -p 'Reply with the single word ok' ${model:+-m "$model"} --output-format stream-json \
                    </dev/null 2>&1)" || true
                if grep -q '"role":"assistant"' <<<"$out" && ! grep -qi 'error' <<<"$out"; then verdict=yes; fi
                ;;
        esac
        rm -rf "$scratch"
        # Parallel workers may probe at once; each writes the same answer atomically.
        printf '%s\n' "$verdict" > "$dir/$key.$$" && mv -f "$dir/$key.$$" "$dir/$key"
    fi
    [[ "$(cat "$dir/$key")" == yes ]]
}
