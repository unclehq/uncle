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
check("agent runners", ["cline", "claude", "kimi"], m.runners_for(m.AGENT))
check("reviewer runners", ["cline", "codex", "claude"], m.runners_for(m.REVIEWER))
check("codex is not an agent choice", False, "codex" in m.runners_for(m.AGENT))
check("an agent stage runs an agent shim", True,
      m.runner_command("cline", m.AGENT).endswith("agent-cline.sh"))
check("a reviewer stage runs a reviewer shim", True,
      m.runner_command("cline", m.REVIEWER).endswith("reviewer-cline.sh"))

# The env every stage produces.
t.stage_runners["adversarial-review"] = "codex"
t.stage_models["project-plan"] = "cline-pass/kimi-k3"
t.stage_efforts["project-plan"] = "high"
env = t.stage_env()
check("non-cline stage exports an empty model", "", env["WORKFLOW_MODEL_REQUIREMENTS"])
check("non-cline stage still exports its command", "claude",
      env["WORKFLOW_AGENT_CMD_REQUIREMENTS"])
check("cline stage exports its model", "cline-pass/kimi-k3",
      env["WORKFLOW_MODEL_PROJECT_PLAN"])
check("cline stage exports its effort", "high", env["WORKFLOW_EFFORT_PROJECT_PLAN"])
check("reviewer stage exports a reviewer command", "codex",
      env["WORKFLOW_REVIEWER_CMD_ADVERSARIAL_REVIEW"])
check("reviewer stage on codex exports no model", "",
      env["WORKFLOW_MODEL_ADVERSARIAL_REVIEW"])
# These would win over the per-stage values inside the shims.
for leaked in ("UNCLE_CLINE_MODEL", "UNCLE_CLINE_EFFORT"):
    check("%s is not exported" % leaked, False, leaked in env)

if failed:
    for f in failed:
        print("FAIL: " + f)
    raise SystemExit(1)
print("  fields/defaults/env: %d checks passed" % 22)
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
    t.first_run = False
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

if [[ "$status" -ne 0 ]]; then
    echo "tui-config-test.sh: failed"
    exit 1
fi

echo "tui-config-test.sh: all checks passed"
