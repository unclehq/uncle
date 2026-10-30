#!/usr/bin/env bash
# Change stage runtime policy bindings. Load stage-runtime.sh first.

stage_supports_structured_output() {
    change_stage_supports_structured_output "$@"
}

stage_uses_self_hosted() {
    change_stage_uses_self_hosted "$@"
}
