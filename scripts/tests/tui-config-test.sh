#!/usr/bin/env bash
set -euo pipefail

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

if ! command -v python3 > /dev/null 2>&1; then
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
check("cline shows a model field", ["runner", "effort", "model"],
      t.stage_fields("requirements"))
t.stage_runners["requirements"] = "claude"
check("claude hides the model field", ["runner", "effort"],
      t.stage_fields("requirements"))
check("claude resolves to no model", "", t.stage_model("requirements"))

# Runner choices are side-appropriate: codex has no agent shim.
check("agent runners", ["cline", "claude", "kimi", "codex"], m.runners_for(m.AGENT))
check("reviewer runners", ["cline", "codex", "claude"], m.runners_for(m.REVIEWER))
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
print("  fields/defaults/env: %d checks passed" % 19)
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
print("  round-trip/migration: %d checks passed" % 17)
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
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t._set_field("requirements", "runner", "kimi")
t._set_field("requirements", "effort", "low")
t._set_field("project-plan", "model", "cline-pass/kimi-k3")
t._set_field("final-audit", "runner", "codex")

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
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t.load_config()
for stage in m.CONFIG_STAGES:
    print("%s\t%s\t%s\t%s" % (stage, t.stage_runner(stage),
                                t.stage_model(stage), t.stage_effort(stage) or "medium"))
PY
)"

actual="$(
    UNCLE_CONFIG="$TMP/proj/.uncle/config" ROOT="$ROOT" bash -c '
        . "$ROOT/scripts/lib/stage-config.sh"
        for stage in requirements project-plan updated-plan preflight implementation \
                     execute-checklist baseline change-spec change-plan \
                     updated-change-plan adversarial-review test-review manual-checklist \
                     final-audit; do
            effort="$(uncle_stage_effort "$stage")"
            printf "%s\t%s\t%s\t%s\n" "$stage" "$(uncle_stage_runner "$stage")" \
                "$(uncle_stage_model "$stage")" "${effort:-medium}"
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
