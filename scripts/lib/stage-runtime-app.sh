#!/usr/bin/env bash
# App stage runtime policy bindings. Load stage-runtime.sh first.

stage_runner_config_name() {
    app_stage_runner_config_name "$@"
}

stage_supports_structured_output() {
    app_stage_supports_structured_output "$@"
}

stage_uses_self_hosted() {
    app_stage_uses_self_hosted "$@"
}
