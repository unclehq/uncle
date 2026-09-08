#!/usr/bin/env bash
# Which purse a cline stage spends.
#
# cline takes no billing flag: within its default provider the modelType
# prefix decides, so `cline-pass/kimi-k3` and a vendor-prefixed `kimi-k3` are
# two purchases of the same model. That makes the model id authoritative and
# the setting a default -- and it means a setting that disagrees with an
# explicit model must lose, or the config would describe a run that never
# happened.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
UNCLE_CONFIG="$work/config"

eq() { [ "$2" = "$3" ] || { echo "FAIL $1: expected '$3', got '$2'" >&2; exit 1; }; }

# Absent, unset, and unrecognized all mean the subscription: that is what the
# tool has always done, and a silent switch to metered billing is not a default.
for value in "" garbage clinepass CLINEPASS; do
    printf 'requirements.runner cline\nrequirements.billing %s\n' "$value" > "$UNCLE_CONFIG"
    eq "billing '$value'" "$(uncle_stage_billing requirements)" clinepass
done
printf 'requirements.runner cline\n' > "$UNCLE_CONFIG"
eq "no billing line" "$(uncle_stage_billing requirements)" clinepass
eq "default model follows it" "$(uncle_stage_model requirements)" cline-pass/deepseek-v4-pro

# Every spelling an operator is likely to write for the metered side.
for value in cline-usage usage usage-based CLINE-USAGE; do
    printf 'requirements.runner cline\nrequirements.billing %s\n' "$value" > "$UNCLE_CONFIG"
    eq "billing '$value'" "$(uncle_stage_billing requirements)" cline-usage
done
eq "its default model differs" "$(uncle_stage_model requirements)" deepseek/deepseek-v4-flash

# A global key is the fallback; a stage key wins over it.
printf 'requirements.runner cline\nbilling cline-usage\n' > "$UNCLE_CONFIG"
eq "global billing" "$(uncle_stage_billing requirements)" cline-usage
printf 'requirements.runner cline\nrequirements.billing clinepass\nbilling cline-usage\n' > "$UNCLE_CONFIG"
eq "stage beats global" "$(uncle_stage_billing requirements)" clinepass

# An explicit model is what cline actually receives, so it decides.
printf 'requirements.runner cline\nrequirements.model anthropic/claude-opus-5\n' > "$UNCLE_CONFIG"
eq "a paid vendor id means usage billing" "$(uncle_stage_billing requirements)" cline-usage
printf 'requirements.runner cline\nrequirements.model cline-pass/kimi-k3\n' > "$UNCLE_CONFIG"
eq "a cline-pass id means the subscription" "$(uncle_stage_billing requirements)" clinepass

# ... including when the billing line disagrees with it, in both directions.
printf 'requirements.runner cline\nrequirements.billing cline-usage\nrequirements.model cline-pass/kimi-k3\n' > "$UNCLE_CONFIG"
eq "the model wins over the setting" "$(uncle_stage_billing requirements)" clinepass
eq "and the model is still passed through" "$(uncle_stage_model requirements)" cline-pass/kimi-k3
printf 'requirements.runner cline\nrequirements.billing clinepass\nrequirements.model anthropic/claude-opus-5\n' > "$UNCLE_CONFIG"
eq "the model wins the other way too" "$(uncle_stage_billing requirements)" cline-usage

# A legacy bare "<stage> <model>" line is a model, so it decides too.
printf 'requirements.runner cline\nrequirements anthropic/claude-opus-5\n' > "$UNCLE_CONFIG"
eq "a legacy bare model line decides" "$(uncle_stage_billing requirements)" cline-usage

# A free model runs under either billing, so it decides nothing: the setting
# still holds, and switching billing must not be read as a contradiction.
printf 'requirements.runner cline\nrequirements.model poolside/laguna-s-2.1\n' > "$UNCLE_CONFIG"
eq "a free model leaves the default alone" "$(uncle_stage_billing requirements)" clinepass
printf 'requirements.runner cline\nrequirements.billing cline-usage\nrequirements.model poolside/laguna-s-2.1\n' > "$UNCLE_CONFIG"
eq "a free model keeps usage billing" "$(uncle_stage_billing requirements)" cline-usage
eq "and is still what runs" "$(uncle_stage_model requirements)" poolside/laguna-s-2.1
printf 'requirements.runner cline\nrequirements.billing clinepass\nrequirements.model meituan/longcat-2.0\n' > "$UNCLE_CONFIG"
eq "a free model keeps the subscription setting" "$(uncle_stage_billing requirements)" clinepass

# Step variants inherit the parent stage's setting.
printf 'implementation.runner cline\nimplementation.billing cline-usage\n' > "$UNCLE_CONFIG"
eq "step variants inherit" "$(uncle_stage_billing implementation-step-3)" cline-usage

# Billing means nothing to a runner that takes no model.
printf 'requirements.runner codex\nrequirements.billing cline-usage\n' > "$UNCLE_CONFIG"
eq "a codex stage still gets no model" "$(uncle_stage_model requirements)" ""

echo 'stage-billing-test.sh: defaults, spellings, global fallback, and model-wins-over-setting passed'
