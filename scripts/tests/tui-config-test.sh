#!/usr/bin/env bash
set -euo pipefail
if ! python3 -c 'import curses' >/dev/null 2>&1; then
    echo "SKIP: curses is unavailable (install windows-curses on Windows)."
    exit 0
fi

# Fixture tests for the Configure screen's per-stage config (uncle_tui.py).
# Hermetic: a temp .uncle/config, no curses, no workflow ever started.
#
# The screen has one row per stage and no global rows. What each stage stores
# is a runner, an effort, and — only when the runner is cline — a model. The
# env it produces is what the drivers read, so that mapping is the contract
# under test: a non-cline stage must export an *empty* model, which the drivers
# read as "pass no model flag".

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/proj/.uncle"

if ! python3 -c pass > /dev/null 2>&1; then
    echo "tui-config-test.sh: skipped, python3 is not available"
    exit 0
fi

FAILED=0
COUNT=0

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

run_case() {
    UNCLE_CONFIG="$TMP/proj/.uncle/config" UNCLE_TUI="$ROOT/uncle_tui.py" python3 - "$@"
}

status=0

# --- fields, defaults, and the env contract --------------------------------

run_case <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)

failed = []
def check(name, expected, actual):
    if expected != actual:
        failed.append("%s — expected %r, got %r" % (name, expected, actual))

t = m.UncleTUI.__new__(m.UncleTUI)          # the screen's state, without curses
t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False

# There are no global rows left: every row is a stage.
check("row per stage", len(m.STAGES), len(m.CONFIG_STAGES))
check("no reviewer catch-all row", False, "reviewer" in m.CONFIG_STAGES)
check("reviewer stages are configurable", True,
      all(s in m.CONFIG_STAGES
          for s in ("adversarial-review", "manual-checklist", "final-audit")))

# An unconfigured stage runs on the defaults.
check("default runner", m.DEFAULT_RUNNER, t.stage_runner("requirements"))
check("default effort", m.DEFAULT_EFFORT, t.stage_effort("requirements"))
check("default cline model", m.DEFAULT_CLINE_MODEL, t.stage_model("requirements"))

# cline is the only runner with a model field.
check("cline shows billing and model", ["runner", "effort", "billing", "model"],
      t.stage_fields("requirements"))
t.stage_runners["requirements"] = "claude"
check("claude hides both", ["runner", "effort"],
      t.stage_fields("requirements"))
check("claude resolves to no model", "", t.stage_model("requirements"))

# codex is the only runner that sandboxes a stage, so it is the only one with a
# network to open. Showing the row anywhere else would offer a setting that
# changes nothing about how the stage runs.
t.stage_runners["execute-checklist"] = "codex"
check("codex shows a network field", ["runner", "effort", "network"],
      t.stage_fields("execute-checklist"))
check("cline has no network field", False,
      "network" in t.stage_fields("project-plan"))
check("codex has no billing field", False,
      "billing" in t.stage_fields("execute-checklist"))
check("kimi has no network field", False,
      "network" in t.stage_fields("requirements"))
check("network is off by default", "false", t.stage_network("execute-checklist"))

# The picker behind the row. Two states and no custom row: a typed value would
# read as a setting while meaning nothing to the flag it becomes.
t.picker_kind, t.picker_target, t.pick_filter = "network", "execute-checklist", ""
check("the network picker offers both states",
      [("option", "false"), ("option", "true")], t._picker_rows())
check("the network picker takes no custom value", False,
      any(kind == "custom" for kind, _ in t._picker_rows()))
check("the network picker knows the current value", "false", t._picker_current())
t.stage_networks["execute-checklist"] = "true"
check("the network picker follows the stage", "true", t._picker_current())

# --- billing decides which model list exists ---------------------------------
# cline takes no billing flag: the modelType prefix is what cline reads, so
# `cline-pass/kimi-k3` and a vendor-prefixed `kimi-k3` are two purchases of
# the same model. Picking billing is picking which catalogue the model row
# offers, and the two must not bleed into each other.
check("billing defaults to the subscription", m.DEFAULT_BILLING,
      t.stage_billing("project-plan"))
check("the subscription list leads with the clinepass group",
      ["Subscribed (ClinePass)", "Free"], [g for g, _ in m.model_catalog(m.CLINEPASS)])
check("usage billing offers a different list", True,
      [g for g, _ in m.model_catalog(m.CLINE_USAGE)] != [g for g, _ in m.model_catalog(m.CLINEPASS)])
check("every subscription id is prefixed", True,
      all(i.startswith("cline-pass/")
          for g, e in m.model_catalog(m.CLINEPASS) if g != "Free" for _, i in e))
check("no usage id is", True,
      not any(i.startswith("cline-pass/")
              for _, e in m.model_catalog(m.CLINE_USAGE) for _, i in e))

# The id decides on its own, so a custom id the catalogue never heard of still
# lands on the right side.
check("a cline-pass id reads as the subscription", m.CLINEPASS,
      m.billing_of_model("cline-pass/anything"))
check("a vendor id reads as usage billing", m.CLINE_USAGE,
      m.billing_of_model("some-vendor/anything"))

# An explicit paid model settles billing even with no billing set. A free one
# does not, because it runs under either.
t.stage_models["project-plan"] = "anthropic/claude-opus-5"
check("a paid model settles it", m.CLINE_USAGE, t.stage_billing("project-plan"))
t.stage_models["project-plan"] = "poolside/laguna-s-2.1"
check("a free model settles nothing", m.DEFAULT_BILLING, t.stage_billing("project-plan"))
check("a free model suits the subscription", True,
      m.model_suits_billing("poolside/laguna-s-2.1", m.CLINEPASS))
check("and suits usage billing", True,
      m.model_suits_billing("poolside/laguna-s-2.1", m.CLINE_USAGE))
check("a clinepass model does not suit usage billing", False,
      m.model_suits_billing("cline-pass/kimi-k3", m.CLINE_USAGE))
del t.stage_models["project-plan"]

# The free group is offered under both billings -- the same four models, since
# they cost nothing either way.
free_clinepass = [i for g, e in m.model_catalog(m.CLINEPASS) if g == "Free" for _, i in e]
free_usage = [i for g, e in m.model_catalog(m.CLINE_USAGE) if g == "Free" for _, i in e]
check("the free group appears under the subscription", True, len(free_clinepass) > 0)
check("the free group is identical in both", free_clinepass, free_usage)
check("Laguna is offered in both", True,
      "poolside/laguna-s-2.1" in free_clinepass and "poolside/laguna-s-2.1" in free_usage)

# The default model follows the billing, since the lists are disjoint.
t.stage_billings["project-plan"] = m.CLINE_USAGE
check("usage billing has its own default model",
      m.DEFAULT_MODEL_FOR_BILLING[m.CLINE_USAGE], t.stage_model("project-plan"))
t.stage_billings["project-plan"] = m.CLINEPASS
check("the subscription keeps the old default",
      m.DEFAULT_MODEL_FOR_BILLING[m.CLINEPASS], t.stage_model("project-plan"))

# The picker offers the list for the stage it was opened on.
t.picker_kind, t.picker_target, t.pick_filter = "model", "project-plan", ""
check("the picker offers subscription models under the subscription", True,
      any(i.startswith("cline-pass/")
          for k, i in t._picker_rows() if k == "model"))
t.stage_billings["project-plan"] = m.CLINE_USAGE
check("and none of them under usage billing", True,
      not any(i.startswith("cline-pass/")
              for k, i in t._picker_rows() if k == "model"))
check("while the free models stay on offer", True,
      any(i in m.FREE_MODEL_IDS for k, i in t._picker_rows() if k == "model"))
t.picker_kind = "billing"
check("the billing picker offers both purses",
      [("option", m.CLINEPASS), ("option", m.CLINE_USAGE)], t._picker_rows())
check("it takes no custom value", False,
      any(k == "custom" for k, _ in t._picker_rows()))
t.stage_billings.clear()

# Which stage can open a socket is worth seeing without opening a popup, and
# only where it means something: a value left on a cline stage is not a socket.
t.stage_networks["project-plan"] = "true"
rows = {r.split()[0]: r for r in t._config_items()}
check("a codex stage with network on says so", True,
      "network" in rows["execute-checklist"])
check("a cline stage does not claim a network", False,
      "network" in rows["project-plan"])
t.stage_networks.clear()

# Runner choices are side-appropriate: codex has no agent shim.
check("agent runners", ["cline", "claude", "kimi", "codex"], m.runners_for(m.AGENT))
check("reviewer runners", ["cline", "codex", "claude", "kimi"], m.runners_for(m.REVIEWER))
check("kimi reviewer resolves to its own shim", True,
      m.runner_command("kimi", m.REVIEWER).endswith("reviewer-kimi.sh"))
check("an agent stage runs an agent shim", True,
      m.runner_command("cline", m.AGENT).endswith("agent-cline.sh"))
check("a reviewer stage runs a reviewer shim", True,
      m.runner_command("cline", m.REVIEWER).endswith("reviewer-cline.sh"))
# codex runs both sides, and the side decides which shim — write access for an
# agent stage, read-only for a reviewer stage.
check("codex as an agent runs the agent shim", True,
      m.runner_command("codex", m.AGENT).endswith("agent-codex.sh"))
check("codex as a reviewer runs codex itself", "codex",
      m.runner_command("codex", m.REVIEWER))

# The environment the driver is given. Per-stage settings are deliberately
# absent: the drivers read .uncle/config themselves, at the moment each stage
# starts, so an edit made at a human gate reaches the stages after it. A
# snapshot exported here would win over that file and silently freeze the run.
t.stage_runners["adversarial-review"] = "codex"
t.stage_models["project-plan"] = "cline-pass/kimi-k3"
t.stage_efforts["project-plan"] = "high"
env = t.stage_env()
check("the config path is passed", os.environ["UNCLE_CONFIG"], env.get("UNCLE_CONFIG"))
derived = [k for k in env if k.startswith("WORKFLOW_")]
check("no per-stage snapshot is exported", [], derived)
# These would win over the per-stage values inside the shims.
for leaked in ("UNCLE_CLINE_MODEL", "UNCLE_CLINE_EFFORT"):
    check("%s is not exported" % leaked, False, leaked in env)

if failed:
    for f in failed:
        print("FAIL: " + f)
    raise SystemExit(1)
print("  fields/defaults/env: %d checks passed" % 53)
PY

# --- round trip, and migration off the old global format -------------------

run_case <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)

failed = []
def check(name, expected, actual):
    if expected != actual:
        failed.append("%s — expected %r, got %r" % (name, expected, actual))

def fresh():
    t = m.UncleTUI.__new__(m.UncleTUI)
    t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
    t.stage_networks, t.stage_billings = {}, {}
    t._config_stamp, t._reload_tick, t.first_run = None, 0, False
    return t

# What the screen writes, it reads back.
t = fresh()
t._set_field("requirements", "runner", "claude")
t._set_field("project-plan", "model", "cline-pass/kimi-k3")
t._set_field("project-plan", "effort", "high")
t._set_field("final-audit", "runner", "codex")

back = fresh()
back.load_config()
check("runner round-trips", "claude", back.stage_runners.get("requirements"))
check("model round-trips", "cline-pass/kimi-k3", back.stage_models.get("project-plan"))
check("effort round-trips", "high", back.stage_efforts.get("project-plan"))
check("reviewer runner round-trips", "codex", back.stage_runners.get("final-audit"))

# The setting that decides whether a stage can bind a port has to survive the
# file, and has to survive a rewrite of it even on a stage whose runner does not
# read it — dropping a hand-edited line silently is how an operator ends up
# rerunning a stage that quietly lost its network.
t = fresh()
t._set_field("execute-checklist", "runner", "codex")
t._set_field("execute-checklist", "network", "true")
t._set_field("project-plan", "network", "true")
back = fresh()
back.load_config()
check("network round-trips", "true", back.stage_networks.get("execute-checklist"))
check("a network line on a cline stage survives a rewrite", "true",
      back.stage_networks.get("project-plan"))
back.save_config()
again = fresh()
again.load_config()
check("and survives the next one too", "true", again.stage_networks.get("project-plan"))

# Switching billing drops a model belonging to the other purse, rather than
# carrying it across and quietly spending the wrong one.
t = fresh()
t._set_field("project-plan", "runner", "cline")
t._set_field("project-plan", "model", "cline-pass/kimi-k3")
t.picker_kind, t.picker_target, t.pick_filter = "billing", "project-plan", ""
t.pick_sel = [i for i, (k, v) in enumerate(t._picker_rows()) if v == m.CLINE_USAGE][0]
t._picker_confirm()
check("the other purse's model is dropped", "", t.stage_models.get("project-plan", ""))
check("the new billing is stored", m.CLINE_USAGE, t.stage_billings.get("project-plan"))
check("so the stage falls back to the usage default",
      m.DEFAULT_MODEL_FOR_BILLING[m.CLINE_USAGE], t.stage_model("project-plan"))

# A model belonging to the chosen purse survives the same switch.
t = fresh()
t._set_field("project-plan", "runner", "cline")
t._set_field("project-plan", "billing", m.CLINE_USAGE)
t._set_field("project-plan", "model", "deepseek/deepseek-v4-flash")
t.picker_kind, t.picker_target, t.pick_filter = "billing", "project-plan", ""
t.pick_sel = [i for i, (k, v) in enumerate(t._picker_rows()) if v == m.CLINE_USAGE][0]
t._picker_confirm()
check("a matching model is kept", "deepseek/deepseek-v4-flash",
      t.stage_models.get("project-plan"))

# Billing round-trips through the file, and the drivers read it back.
back = fresh()
back.load_config()
check("billing round-trips", m.CLINE_USAGE, back.stage_billings.get("project-plan"))

# Clearing the row (d, for default) takes the line back out.
again._set_field("execute-checklist", "network", "")
text = open(os.environ["UNCLE_CONFIG"]).read()
check("cleared network is not written", False, "execute-checklist.network" in text)

# A model on a non-cline stage is not written: nothing would read it.
t = fresh()
t._set_field("requirements", "model", "cline-pass/glm-5.3")
t._set_field("requirements", "runner", "kimi")
text = open(os.environ["UNCLE_CONFIG"]).read()
check("no model line for a non-cline stage", False, "requirements.model" in text)

# The old global format seeds the stages instead of being dropped.
with open(os.environ["UNCLE_CONFIG"], "w") as fh:
    fh.write("runner cline\nmodel poolside/laguna-s-2.1\neffort low\n"
             "reviewer cline-pass/glm-5.3\nproject-plan cline-pass/kimi-k3\n")
legacy = fresh()
legacy.load_config()
check("legacy global runner seeds a stage", "cline",
      legacy.stage_runner("implementation"))
check("legacy global effort seeds a stage", "low", legacy.stage_effort("implementation"))
check("legacy global model seeds a stage", "poolside/laguna-s-2.1",
      legacy.stage_model("implementation"))
check("legacy bare stage line is a model", "cline-pass/kimi-k3",
      legacy.stage_model("project-plan"))
check("legacy reviewer model goes to reviewer stages", "cline-pass/glm-5.3",
      legacy.stage_model("final-audit"))

# Saving migrates the file: the global keys are gone, per-stage keys remain.
legacy.save_config()
text = open(os.environ["UNCLE_CONFIG"]).read()
lines = [l for l in text.splitlines() if l and not l.startswith("#")]
check("no global runner line survives", False, any(l == "runner cline" for l in lines))
check("no global model line survives", False,
      any(l.startswith("model ") for l in lines))
check("per-stage lines are written", True,
      any(l.startswith("implementation.runner ") for l in lines))

# A model id must be one cline can parse.
check("a display name is rejected", False, m.valid_model_id("Laguna S 2.1"))
check("an id is accepted", True, m.valid_model_id("cline-pass/kimi-k3"))
check("empty means the runner's own default", True, m.valid_model_id(""))

if failed:
    for f in failed:
        print("FAIL: " + f)
    raise SystemExit(1)
print("  round-trip/migration: %d checks passed" % 27)
PY

# --- the screen and the drivers must read the same file the same way -------

run_case > /dev/null <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)

t = m.UncleTUI.__new__(m.UncleTUI)
t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t._set_field("requirements", "runner", "kimi")
t._set_field("requirements", "effort", "low")
t._set_field("project-plan", "model", "cline-pass/kimi-k3")
t._set_field("final-audit", "runner", "codex")
# Written by the screen, read back by the drivers: the setting that decides
# whether a checklist stage can bind a port must survive the round trip.
t._set_field("execute-checklist", "runner", "codex")
t._set_field("execute-checklist", "network", "true")

# What the screen thinks each stage will run, for the bash side to confirm.
for stage in m.CONFIG_STAGES:
    print("%s\t%s\t%s\t%s" % (stage, t.stage_runner(stage),
                                t.stage_model(stage), t.stage_effort(stage)))
PY

expect="$(UNCLE_CONFIG="$TMP/proj/.uncle/config" UNCLE_TUI="$ROOT/uncle_tui.py" python3 - <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec); sys.modules["tui"] = m
spec.loader.exec_module(m)
t = m.UncleTUI.__new__(m.UncleTUI)
t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t.load_config()
for stage in m.CONFIG_STAGES:
    print("%s\t%s\t%s\t%s\t%s" % (stage, t.stage_runner(stage),
                                t.stage_model(stage), t.stage_effort(stage) or "medium",
                                t.stage_network(stage)))
PY
)"

actual="$(
    UNCLE_CONFIG="$TMP/proj/.uncle/config" ROOT="$ROOT" bash -c '
        . "$ROOT/scripts/lib/stage-config.sh"
        for stage in requirements baseline change-spec project-plan change-plan \
                     adversarial-review updated-plan updated-change-plan preflight \
                     implementation test-review manual-checklist execute-checklist \
                     final-audit; do
            effort="$(uncle_stage_effort "$stage")"
            printf "%s\t%s\t%s\t%s\t%s\n" "$stage" "$(uncle_stage_runner "$stage")" \
                "$(uncle_stage_model "$stage")" "$effort" \
                "$(uncle_stage_network "$stage")"
        done'
)"

COUNT=$((COUNT + 1))
if [[ "$expect" != "$actual" ]]; then
    fail "the drivers resolve the config differently from the screen"
    diff <(printf '%s\n' "$expect") <(printf '%s\n' "$actual") | head -20
fi

if [[ "$status" -ne 0 || "$FAILED" -ne 0 ]]; then
    echo "tui-config-test.sh: failed"
    exit 1
fi

echo "tui-config-test.sh: all checks passed"
