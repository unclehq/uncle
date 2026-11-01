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
# is a runner, an effort, and a model (claude, codex, and kimi take a
# vendor id). The env it produces is what the drivers
# read, so that mapping is the contract under test: a stage with no model
# stored must export an *empty* one, which the drivers read as "pass no model
# flag".

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

# Discovery uses isolated PATH files, never client execution.
run_case <<'PYDISC'
import os, sys, tempfile, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["UNCLE_TUI"]).parent))
import uncle_tui as m
# This test is specifically about the PATH-discovery fallback, which an
# operator-configured DEFAULT_RUNNER short-circuits; isolate it from that.
m.DEFAULT_RUNNER = ""
bash = "/bin/bash"
root = Path(m.ROOT)
original = os.environ["PATH"]
with tempfile.TemporaryDirectory() as tmp:
    bindir = Path(tmp)
    names = ["claude", "codex", "kimi", "opencode"]
    for mask in range(16):
        for i, name in enumerate(names):
            path = bindir / name
            if path.exists():
                path.unlink()
            if mask & (1 << i):
                path.write_text("#!/bin/sh\nexit 97\n")
                path.chmod(0o755)
        os.environ["PATH"] = tmp
        expected = [("self-hosted" if n == "opencode" else n)
                    for i, n in enumerate(names) if mask & (1 << i)]
        for side in (m.AGENT, m.REVIEWER):
            assert m.runners_for(side) == expected, (mask, side, m.runners_for(side))
        t = m.UncleTUI.__new__(m.UncleTUI)
        t.stage_runners = {}
        default = expected[0] if expected else ""
        assert t.stage_runner("derive-brief") == default
        result = subprocess.run([bash, "-c",
            # Isolated the same way as m.DEFAULT_RUNNER above: this probe is
            # about the installed-agent scan, not the operator-configured default.
            '. "$1/scripts/lib/stage-config.sh"; UNCLE_DEFAULT_RUNNER=; uncle_stage_runner derive-brief',
            "test", str(root)], env=dict(os.environ, UNCLE_CONFIG="/nonexistent"),
            capture_output=True, text=True)
        assert result.stdout == default, (mask, result.stdout)
    # AR-001: inferred Claude must not erase a saved model.
    os.environ["PATH"] = original
    m.CONFIG_PATH = str(bindir / "config")
    for name in names:
        (bindir / name).unlink()
    for name in ("codex", "claude"):
        (bindir / name).write_text("")
        (bindir / name).chmod(0o755)
    os.environ["PATH"] = tmp
    # derive-brief, not requirements: requirements is not in STAGES, so
    # load_config skips its lines and a KeyError would mask this assertion.
    Path(m.CONFIG_PATH).write_text("derive-brief.model deepseek/deepseek-v4-flash\n")
    t.load_config()
    t.stage_efforts["derive-brief"] = "high"
    t.save_config()
    (bindir / "claude").unlink()
    t.load_config()
    assert t.stage_runner("derive-brief") == "codex"
    assert t.stage_models["derive-brief"] == "deepseek/deepseek-v4-flash"
    assert not t.stage_runners
os.environ["PATH"] = original
print("  discovery: 16 subsets, both sides, shell parity; inferred save passed")
PYDISC

# These fixtures assume only codex is installed.
mkdir -p "$TMP/bin"
printf '#!/bin/sh\nexit 97\n' > "$TMP/bin/codex"
chmod +x "$TMP/bin/codex"
# Keep utilities available while excluding any installed agents.
for tool in python3 bash tr rm diff head mkdir cat; do
    ln -s "$(command -v "$tool")" "$TMP/bin/$tool"
done
TEST_ORIGINAL_PATH="$PATH"
export PATH="$TMP/bin"

# --- fields, defaults, and the env contract --------------------------------

run_case <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)
# This section is specifically about the "only codex is installed, nothing
# configured" discovery scenario, which an operator-configured DEFAULT_RUNNER
# short-circuits; isolate it from that (see the PYDISC case above).
m.DEFAULT_RUNNER = ""

failed = []
checks = [0]
def check(name, expected, actual):
    checks[0] += 1
    if expected != actual:
        failed.append("%s — expected %r, got %r" % (name, expected, actual))

t = m.UncleTUI.__new__(m.UncleTUI)          # the screen's state, without curses
t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
t.stage_base_urls, t.stage_api_keys = {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False

# There are no global rows left: every row is a stage.
check("row per stage", len(m.STAGES), len(m.CONFIG_STAGES))
check("no reviewer catch-all row", False, "reviewer" in m.CONFIG_STAGES)
check("reviewer stages are configurable", True,
      all(s in m.CONFIG_STAGES
          for s in ("adversarial-review", "manual-checklist", "final-audit")))

# An unconfigured stage runs on the defaults.
check("default runner with only codex installed", "codex", t.stage_runner("derive-brief"))
check("default effort", m.DEFAULT_EFFORT, t.stage_effort("derive-brief"))

# AC-1: claude and kimi take a model row; codex keeps network above its model
# row. AC-4: stage_model returns the stored id for those runners, "" with none
# stored (I-4 RELAXED: a stored model is no longer forced to "").
t.stage_runners["requirements"] = "claude"
check("claude shows a model row", ["runner", "effort", "model"],
      t.stage_fields("requirements"))
check("a claude stage with no model stored resolves to empty", "",
      t.stage_model("requirements"))
t.stage_models["requirements"] = "claude-opus-5"
check("claude stage_model returns the stored id", "claude-opus-5",
      t.stage_model("requirements"))
del t.stage_models["requirements"]

t.stage_runners["requirements"] = "kimi"
check("kimi shows a model row", ["runner", "effort", "model"],
      t.stage_fields("requirements"))
t.stage_models["requirements"] = "moonshotai/kimi-k2.6"
check("kimi stage_model returns the raw stored id", "moonshotai/kimi-k2.6",
      t.stage_model("requirements"))
del t.stage_models["requirements"]

# self-hosted takes a model and, like claude or codex, an effort.
t.stage_runners["derive-brief"] = "self-hosted"
check("self-hosted shows effort and model", ["runner", "effort", "model"],
      t.stage_fields("derive-brief"))
t.picker_kind, t.picker_target, t.pick_filter = "effort", "derive-brief", ""
check("the effort picker offers all supported levels",
      [("option", "none"), ("option", "low"), ("option", "medium"), ("option", "high"),
       ("custom", "Custom… (type an effort)")], t._picker_rows())

# Its model picker takes custom ids.
t.picker_kind, t.picker_target, t.pick_filter = "model", "derive-brief", ""
check("the self-hosted model picker takes a custom id", True,
      any(kind == "custom" for kind, _ in t._picker_rows()))
t._set_field("derive-brief", "model", "my-fine-tune:latest")
check("a custom self-hosted model id is stored", "my-fine-tune:latest",
      t.stage_models["derive-brief"])
t.stage_models.pop("derive-brief")
t.stage_runners.pop("derive-brief")

# codex is the only runner that sandboxes a stage, so it is the only one with a
# network to open. Showing the row anywhere else would offer a setting that
# changes nothing about how the stage runs.
t.stage_runners["execute-checklist"] = "codex"
check("codex shows a network field", ["runner", "effort", "network", "model"],
      t.stage_fields("execute-checklist"))
check("a codex stage with no model stored resolves to empty", "",
      t.stage_model("execute-checklist"))
t.stage_models["execute-checklist"] = "gpt-5.1-codex"
check("codex stage_model returns the stored id", "gpt-5.1-codex",
      t.stage_model("execute-checklist"))
del t.stage_models["execute-checklist"]
check("codex has no billing field", False,
      "billing" in t.stage_fields("execute-checklist"))
t.stage_runners["derive-brief"] = "kimi"
check("kimi has no network field", False,
      "network" in t.stage_fields("derive-brief"))
t.stage_runners.pop("derive-brief")
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

# --- vendor model pickers (claude/codex/kimi) --------------------------------

# AC-2: each runner's model picker offers only its own catalogue, Custom last.
# Self-hosted's picker (above) is untouched: it offers discovered models.
t.stage_runners["execute-checklist"] = "codex"
vendor_cases = [
    ("claude", "requirements", m.MODEL_CATALOG_CLAUDE),
    ("codex", "execute-checklist", m.MODEL_CATALOG_CODEX),
    ("kimi", "requirements", m.MODEL_CATALOG_KIMI),
]
for runner, stage, catalog in vendor_cases:
    t.stage_runners.pop("requirements", None)
    t.stage_runners[stage] = runner
    t.picker_kind, t.picker_target, t.pick_filter = "model", stage, ""
    expected_rows = []
    for group, entries in catalog:
        expected_rows.append(("header", group))
        expected_rows.extend(("model", mid) for _label, mid in entries)
    expected_rows.append(("custom", "Custom… (type a model id)"))
    check("the %s picker offers its own catalogue" % runner,
          expected_rows, t._picker_rows())
    check("the %s picker keeps its Custom row last" % runner, "custom",
          t._picker_rows()[-1][0])
    t.pick_filter = catalog[0][1][0][0].split()[0].lower()
    check("the %s picker filters by label" % runner, True,
          all(k != "header" for k, _ in t._picker_filtered()))
    t.pick_filter = ""
t.stage_models["requirements"] = "moonshotai/kimi-k2.6"
t.picker_target = "requirements"
check("the kimi picker knows the stored id", "moonshotai/kimi-k2.6",
      t._picker_current())
del t.stage_models["requirements"]

# AC-3: every offered id must pass its runner shim's filter. The claude
# allowlist and codex blank set are the literal patterns from
# reviewer-claude.sh:84 and agent-codex.sh:67; keep them in step with the
# shims when the catalogues grow.
CLAUDE_ALLOW = ("claude", "opus", "sonnet", "haiku")
CODEX_BLANK = {"opus", "sonnet", "o3", "kimi"}
claude_ids = [mid for _g, entries in m.MODEL_CATALOG_CLAUDE for _l, mid in entries]
check("every claude id passes the shim allowlist", True,
      all(any(mid.startswith(p) for p in CLAUDE_ALLOW) for mid in claude_ids))
codex_ids = [mid for _g, entries in m.MODEL_CATALOG_CODEX for _l, mid in entries]
check("no codex id is in the shim blank list", True,
      all(mid not in CODEX_BLANK and not mid.startswith("kimi:")
          for mid in codex_ids))
kimi_ids = [mid for _g, entries in m.MODEL_CATALOG_KIMI for _l, mid in entries]
check("catalogue ids are unique across the vendor lists", True,
      len(claude_ids + codex_ids + kimi_ids)
      == len(set(claude_ids + codex_ids + kimi_ids)))

# AC-5: the row names the stored id with its label, and the runner's own
# default when nothing is stored.
vendor_displays = [
    ("claude", "claude-opus-5", "claude-opus-5  Claude Opus 5",
     "claude-sonnet-5  (default)  Claude Sonnet 5"),
    ("codex", "gpt-5.1-codex", "gpt-5.1-codex  GPT-5.1 Codex", "codex default  (default)"),
    ("kimi", "moonshotai/kimi-k2.6", "moonshotai/kimi-k2.6  Kimi K2.6",
     "moonshotai/kimi-k2.7-code-highspeed  (default)  Kimi K2.7 Code Highspeed"),
]
for runner, stored, stored_text, default_text in vendor_displays:
    t.stage_runners.pop("requirements", None)
    t.stage_runners["requirements"] = runner
    check("%s model row reads the runner default" % runner, default_text,
          t._field_display("requirements", "model"))
    t.stage_models["requirements"] = stored
    check("%s model row reads the stored id and label" % runner, stored_text,
          t._field_display("requirements", "model"))
    del t.stage_models["requirements"]

# AC-6: Custom validation is runner-aware: claude/codex/kimi need only a
# non-empty id.
check("a slash-free id is a claude model", True, m.valid_model_id("opus", "claude"))
check("a slash-free id is a codex model", True,
      m.valid_model_id("gpt-5.1-codex", "codex"))
check("a raw moonshot id is a kimi model", True,
      m.valid_model_id("moonshotai/kimi-k2.6", "kimi"))
check("an empty id is rejected for claude", False, m.valid_model_id("", "claude"))
check("an empty id is rejected for codex", False, m.valid_model_id("", "codex"))
check("an empty id is rejected for kimi", False, m.valid_model_id("", "kimi"))

# _confirm_text is a key handler: it needs the editing state and a notice.
t.state, t.stage_sel, t.notice = "config_edit", 0, ""
t.picker_kind, t.picker_target, t.pick_filter = "model", "requirements", ""
for runner in ("claude", "codex", "kimi"):
    t.stage_runners["requirements"] = runner
    mid = "opus" if runner == "claude" else runner + "-custom-1"
    t.state, t.input_buf = "config_edit", mid
    t._confirm_text()
    check("a slash-free custom id is stored for %s" % runner,
          mid, t.stage_models.get("requirements"))
    t.state, t.input_buf = "config_edit", "   "
    t._confirm_text()
    check("an empty custom id is rejected for %s" % runner,
          "enter a model id for %s" % runner, t.notice)
    del t.stage_models["requirements"]
t.input_buf = ""
t.notice = ""

# AC-8: switching the runner keeps a stored model dormant, and the row comes
# back when the runner does (I-6).
t.stage_runners["requirements"] = "kimi"
t.stage_models["requirements"] = "moonshotai/kimi-k2.6"
t.stage_runners["requirements"] = "claude"
check("a kimi model is dormant under claude", "moonshotai/kimi-k2.6",
      t.stage_models["requirements"])
check("dormant or not, the stored value is kept",
      "moonshotai/kimi-k2.6", t.stage_model("requirements"))
t.stage_runners["requirements"] = "mystery"
check("no model row appears for an unknown runner", False,
      "model" in t.stage_fields("requirements"))
t.stage_runners["requirements"] = "kimi"
check("the model row is back with the runner",
      ["runner", "effort", "model"], t.stage_fields("requirements"))
check("and the stored id is back on it",
      "moonshotai/kimi-k2.6  Kimi K2.6",
      t._field_display("requirements", "model"))
del t.stage_models["requirements"]

# AC-10: the descriptions never mention the removed runner.
for key in ("field:runner", "field:model"):
    check("CONFIG_DESC[%s] omits the removed runner" % key, False,
          "cline" in m.CONFIG_DESC[key].lower())
check("the model description names the vendor runners", True,
      all(r in m.CONFIG_DESC["field:model"] for r in ("claude", "codex", "kimi")))

t.stage_models.pop("requirements", None)
t.stage_runners.pop("requirements", None)

# Which stage can open a socket is worth seeing without opening a popup, and
# only where it means something: a value left on a claude stage is not a socket.
t.stage_runners["project-plan"] = "claude"
t.stage_networks["project-plan"] = "true"
t.config_section = "stages"
rows = {r.split()[0]: r for r in t._config_items()}
check("a codex stage with network on says so", True,
      "network" in rows["execute-checklist"])
check("a claude stage does not claim a network", False,
      "network" in rows["project-plan"])
t.stage_networks.clear()
t.stage_runners.pop("project-plan")

# Runner choices are side-appropriate: codex has no agent shim.
check("installed agent runners", ["codex"], m.runners_for(m.AGENT))
check("installed reviewer runners", ["codex"], m.runners_for(m.REVIEWER))
check("kimi reviewer resolves to its own shim", True,
      m.runner_command("kimi", m.REVIEWER).endswith("reviewer-kimi.sh"))
check("an agent stage runs an agent shim", True,
      m.runner_command("kimi", m.AGENT).endswith("agent-kimi.sh"))
def _rejects(runner, side):
    try:
        m.runner_command(runner, side)
    except ValueError as e:
        return str(e)
    return None
for _side in (m.AGENT, m.REVIEWER):
    _msg = _rejects("cline", _side)
    check("cline is rejected on side %s" % _side, True,
          bool(_msg) and "Cline support was removed" in _msg and "claude, codex, kimi or self-hosted" in _msg)
    _msg = _rejects("Cline", _side)
    check("Cline (any case) is rejected on side %s" % _side, True,
          bool(_msg) and "Cline support was removed" in _msg)
    _msg = _rejects("bogus", _side)
    check("unknown runner is rejected on side %s with the exact D2 text" % _side, True,
          _msg == "uncle: runner 'bogus' is not supported (Cline support was removed). Set it to claude, codex, kimi or self-hosted with 'uncle' -> Configure.")
check("cline is not a selectable runner", False,
      "cline" in m.AGENT_RUNNERS or "cline" in m.REVIEWER_RUNNERS)

# A saved cline/typo runner: notice shown, stage left unselected (not cline,
# no fallback), no cline in the runner list, config bytes untouched (D4/D6).
import tempfile
for saved, want in (("cline", "Cline support was removed"), ("Cline", "Cline support was removed"),
                    ("bogus", "runner 'bogus' is not supported (Cline support was removed)")):
    with tempfile.TemporaryDirectory() as _d:
        _cfg = os.path.join(_d, "config")
        _body = "project-plan.runner %s\nproject-plan.effort high\n" % saved
        open(_cfg, "w").write(_body)
        _old, m.CONFIG_PATH = m.CONFIG_PATH, _cfg
        try:
            _t = m.UncleTUI.__new__(m.UncleTUI)
            _t.stage_runners, _t.stage_models, _t.stage_efforts = {}, {}, {}
            _t.stage_base_urls, _t.stage_api_keys, _t.stage_networks = {}, {}, {}
            _t._config_stamp, _t._reload_tick, _t.first_run = None, 0, False
            _t.notice = ""
            _t.load_config()
            _sel = _t.stage_runner("project-plan")
        finally:
            m.CONFIG_PATH = _old
        check("saved %r runner is not selected" % saved, "", _sel)
        check("saved %r runner shows the notice" % saved, m.unsupported_runner_message(saved), _t.notice)
        check("notice for %r has the expected wording" % saved, True, want in _t.notice)
        check("notice for %r names the replacements" % saved,
              True, "claude, codex, kimi or self-hosted" in _t.notice)
        check("saved %r config bytes are unchanged" % saved, _body, open(_cfg).read())
        check("no cline in the runner list after load", False, "cline" in m.runners_for(m.AGENT))
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
t.stage_models["project-plan"] = "vendor/kimi-k3"
t.stage_efforts["project-plan"] = "high"
env = t.stage_env()
check("the config path is passed", os.environ["UNCLE_CONFIG"], env.get("UNCLE_CONFIG"))
derived = [k for k in env if k.startswith("WORKFLOW_")]
check("no per-stage snapshot is exported", [], derived)
# These would win over the per-stage values inside the shims.
check("no removed-runner variable is exported", False,
      any("CLINE" in k.upper() for k in env))

if failed:
    for f in failed:
        print("FAIL: " + f)
    raise SystemExit(1)
print("  fields/defaults/env: %d checks passed" % checks[0])
PY

# --- round trip, and migration off the old global format -------------------

run_case <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)

failed = []
checks = [0]
def check(name, expected, actual):
    checks[0] += 1
    if expected != actual:
        failed.append("%s — expected %r, got %r" % (name, expected, actual))

def fresh():
    t = m.UncleTUI.__new__(m.UncleTUI)
    t.stage_runners, t.stage_models, t.stage_efforts = {}, {}, {}
    t.stage_base_urls, t.stage_api_keys = {}, {}
    t.stage_networks, t.stage_billings = {}, {}
    t._config_stamp, t._reload_tick, t.first_run = None, 0, False
    return t

# What the screen writes, it reads back.
t = fresh()
t._set_field("derive-brief", "runner", "claude")
t._set_field("project-plan", "model", "vendor/kimi-k3")
t._set_field("project-plan", "effort", "high")
t._set_field("final-audit", "runner", "codex")

back = fresh()
back.load_config()
check("runner round-trips", "claude", back.stage_runners.get("derive-brief"))
check("model round-trips", "vendor/kimi-k3", back.stage_models.get("project-plan"))
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
check("a network line on a claude stage survives a rewrite", "true",
      back.stage_networks.get("project-plan"))
back.save_config()
again = fresh()
again.load_config()
check("and survives the next one too", "true", again.stage_networks.get("project-plan"))

# Clearing the row (d, for default) takes the line back out.
again._set_field("execute-checklist", "network", "")
text = open(os.environ["UNCLE_CONFIG"]).read()
check("cleared network is not written", False, "execute-checklist.network" in text)

# Hand-edited dormant models survive a save for a later runner rollback.
t = fresh()
t.stage_models["implementation"] = "vendor/glm-5.3"
t.stage_runners["implementation"] = "kimi"
t.save_config()
text = open(os.environ["UNCLE_CONFIG"]).read()
check("dormant model line survives", True, "implementation.model vendor/glm-5.3" in text)

# The old global format seeds the stages instead of being dropped.
with open(os.environ["UNCLE_CONFIG"], "w") as fh:
    fh.write("runner claude\nmodel poolside/laguna-s-2.1\neffort low\n"
             "reviewer vendor/glm-5.3\nproject-plan vendor/kimi-k3\n")
legacy = fresh()
legacy.load_config()
check("legacy global runner seeds a stage", "claude",
      legacy.stage_runner("implementation"))
check("legacy global effort seeds a stage", "low", legacy.stage_effort("implementation"))
check("legacy global model seeds a stage", "poolside/laguna-s-2.1",
      legacy.stage_model("implementation"))
check("legacy bare stage line is a model", "vendor/kimi-k3",
      legacy.stage_model("project-plan"))
check("legacy reviewer model goes to reviewer stages", "vendor/glm-5.3",
      legacy.stage_model("final-audit"))

# Saving migrates the file: the global keys are gone, per-stage keys remain.
legacy.save_config()
text = open(os.environ["UNCLE_CONFIG"]).read()
lines = [l for l in text.splitlines() if l and not l.startswith("#")]
check("no global runner line survives", False, any(l == "runner claude" for l in lines))
check("no global model line survives", False,
      any(l.startswith("model ") for l in lines))
check("per-stage lines are written", True,
      any(l.startswith("implementation.runner ") for l in lines))

# AC-7: a stored vendor model round-trips through the file for
# claude/codex/kimi. AR-001: for kimi the config content is what round-trips;
# the shell maps the raw id to the `kimi` dispatch token and exports the raw
# id as WORKFLOW_KIMI_MODEL (asserted on the bash side below).
t = fresh()
t._set_field("implementation", "runner", "claude")
t._set_field("implementation", "model", "claude-opus-5")
t._set_field("execute-checklist", "runner", "codex")
t._set_field("execute-checklist", "model", "gpt-5.1-codex")
t._set_field("final-audit", "runner", "kimi")
t._set_field("final-audit", "model", "moonshotai/kimi-k2.6")
back = fresh()
back.load_config()
check("a claude stage model round-trips", "claude-opus-5",
      back.stage_model("implementation"))
check("a codex stage model round-trips", "gpt-5.1-codex",
      back.stage_model("execute-checklist"))
check("a kimi stage raw model id round-trips", "moonshotai/kimi-k2.6",
      back.stage_model("final-audit"))
check("the file carries the kimi raw id", True,
      "final-audit.model moonshotai/kimi-k2.6\n"
      in open(os.environ["UNCLE_CONFIG"]).read())

if failed:
    for f in failed:
        print("FAIL: " + f)
    raise SystemExit(1)
print("  round-trip/migration: %d checks passed" % checks[0])
PY

# AC-7, kimi shell side (AR-001): a stored raw id prints the dispatch token
# and exports the raw id as WORKFLOW_KIMI_MODEL.
kimi_shell="$(UNCLE_CONFIG="$TMP/proj/.uncle/config" ROOT="$ROOT" TMPOUT="$TMP/kimi.out" bash -c '''
    . "$ROOT/scripts/lib/stage-config.sh"
    # No command substitution: its subshell would swallow the export.
    uncle_stage_model final-audit > "$TMPOUT"
    printf "%s|%s" "$(< "$TMPOUT")" "${WORKFLOW_KIMI_MODEL-}"''')"
COUNT=$((COUNT + 1))
if [[ "$kimi_shell" != "kimi|moonshotai/kimi-k2.6" ]]; then
    fail "kimi shell: expected kimi|moonshotai/kimi-k2.6, got $kimi_shell"
fi

# A6: runnerless legacy selections survive saves and a default-runner change.
run_case <<'PY' || status=1
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec)
sys.modules["tui"] = m
spec.loader.exec_module(m)

def load():
    t = m.UncleTUI.__new__(m.UncleTUI)
    t.load_config()
    return t

fixtures = {
    "global": "model poolside/laguna-s-2.1\n",
    "bare": "implementation poolside/laguna-s-2.1\n",
    "stage": "implementation.model poolside/laguna-s-2.1\n",
    "precedence": (
        "model poolside/laguna-s-2.1\n"
        "reviewer vendor/glm-5.3\n"
        "implementation vendor/kimi-k3\n"
        "implementation.model poolside/laguna-s-2.1\n"
    ),
}
checks = 0
for name, config in fixtures.items():
    with open(os.environ["UNCLE_CONFIG"], "w") as fh:
        fh.write(config)
    m.DEFAULT_RUNNER = "claude"
    t = load()
    expected_models = dict(t.stage_models)
    if name == "precedence":
        assert t.stage_models["implementation"] == "poolside/laguna-s-2.1"
        assert t.stage_models["final-audit"] == "vendor/glm-5.3"
        checks += 2
    for cycle in range(2):
        assert not t.stage_runners, (name, "runner keys materialized")
        # Repair inherits an unset selection from implementation, matching the
        # shell's uncle_stage_key() contract.
        assert all(t.stage_runner(s) == "claude"
                   and t.stage_model(s) == (t.stage_models.get(s, "") or
                                              (t.stage_models.get("implementation", "") if s == "repair" else ""))
                   for s in m.CONFIG_STAGES), (name, "stored model not live")
        t.save_config()
        t = load()
        assert t.stage_models == expected_models, (name, "model loss")
        checks += 3
    m.DEFAULT_RUNNER = "codex"
    t = load()
    assert not t.stage_runners, (name, "default runner pinned")
    for stage, model in expected_models.items():
        assert t.stage_runner(stage) == "codex" and t.stage_model(stage) == model
        checks += 1
    checks += 1
# self-hosted runs last: the file left behind feeds the parity check below, and
# a vendor runner there would not compare equal across the sides.
for runner in ("claude", "kimi", "codex", "self-hosted"):
    with open(os.environ["UNCLE_CONFIG"], "w") as fh:
        fh.write("implementation.runner %s\nimplementation.model poolside/laguna-s-2.1\n" % runner)
    t = load()
    expected_models = dict(t.stage_models)
    t.save_config()
    t = load()
    assert t.stage_runner("implementation") == runner
    assert t.stage_models == expected_models, (runner, "dormant model loss")
    checks += 2
print("  dormant selections/rollback: %d checks passed" % checks)
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
t.stage_base_urls, t.stage_api_keys = {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t._set_field("derive-brief", "runner", "kimi")
t._set_field("derive-brief", "effort", "low")
t._set_field("project-plan", "model", "vendor/kimi-k3")
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
t.stage_base_urls, t.stage_api_keys = {}, {}
t.stage_networks, t.stage_billings = {}, {}
t._config_stamp, t._reload_tick, t.first_run = None, 0, False
t.load_config()
for stage in m.CONFIG_STAGES:
    runner = t.stage_runner(stage)
    # The Kimi adapter --model value is its dispatch token.  Its raw
    # provider id remains in WORKFLOW_KIMI_MODEL, so do not compare that
    # transport detail to a raw UI field here.
    model = "kimi" if runner == "kimi" else t.stage_model(stage)
    print("%s\t%s\t%s\t%s\t%s" % (stage, runner,
                                model, t.stage_effort(stage) or "medium",
                                t.stage_network(stage)))
PY
)"

# The screen only writes CONFIG_STAGES (requirements/baseline are not in
# STAGES), so the driver side reads back exactly that list, in the same order.
stage_list="$(UNCLE_TUI="$ROOT/uncle_tui.py" python3 - <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec); sys.modules["tui"] = m
spec.loader.exec_module(m)
print(" ".join(m.CONFIG_STAGES))
PY
)"
actual="$(
    UNCLE_CONFIG="$TMP/proj/.uncle/config" ROOT="$ROOT" STAGE_LIST="$stage_list" bash -c '
        . "$ROOT/scripts/lib/stage-config.sh"
        for stage in $STAGE_LIST; do
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

# .uncle holds run state, cost logs, and (via self_hosted.py) API keys -- a
# project's first ever load_config() call, before .uncle/config exists, must
# make sure an existing .gitignore never lets it slip into a commit. Each of
# these uses its own project root and .uncle/config, not the shared fixture
# above run_case always points at -- that config already exists by now.
gitignore_load_config() {
    local proj="$1"
    UNCLE_CONFIG="$proj/.uncle/config" UNCLE_PROJECT_ROOT="$proj" UNCLE_TUI="$ROOT/uncle_tui.py" python3 - <<'PYGIT'
import os, sys
sys.path.insert(0, os.path.dirname(os.environ["UNCLE_TUI"]))
import uncle_tui as m
t = m.UncleTUI.__new__(m.UncleTUI)
t.load_config()
PYGIT
}

GPROJ="$TMP/gitignore-existing"
mkdir -p "$GPROJ"
printf 'node_modules/\n' > "$GPROJ/.gitignore"
gitignore_load_config "$GPROJ"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ/.gitignore")" == $'node_modules/\n.uncle/*\n!.uncle/docs/' ]] \
    || fail "first run did not add .uncle to an existing .gitignore: $(cat "$GPROJ/.gitignore")"

GPROJ2="$TMP/gitignore-none"
mkdir -p "$GPROJ2"
gitignore_load_config "$GPROJ2"
COUNT=$((COUNT + 1))
[[ ! -e "$GPROJ2/.gitignore" ]] || fail "first run created a .gitignore where none existed"

GPROJ3="$TMP/gitignore-already-listed"
mkdir -p "$GPROJ3"
printf 'dist/\n.uncle/\ncoverage/\n' > "$GPROJ3/.gitignore"
gitignore_load_config "$GPROJ3"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ3/.gitignore")" == $'dist/\n.uncle/*\n!.uncle/docs/\ncoverage/' ]] \
    || fail "a bare .uncle entry was not upgraded in place: $(cat "$GPROJ3/.gitignore")"

GPROJ4="$TMP/gitignore-already-upgraded"
mkdir -p "$GPROJ4"
printf '.uncle/*\n!.uncle/docs/\n' > "$GPROJ4/.gitignore"
gitignore_load_config "$GPROJ4"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ4/.gitignore")" == $'.uncle/*\n!.uncle/docs/' ]] \
    || fail "an already-upgraded .gitignore was changed: $(cat "$GPROJ4/.gitignore")"

# A stale bare entry after prior canonical pairs used to cause every TUI
# first-run refresh to append one more pair. Repair all existing duplication
# once, then prove another refresh is byte-for-byte idempotent.
GPROJ5="$TMP/gitignore-duplicate-legacy"
mkdir -p "$GPROJ5"
printf '.uncle/*\n!.uncle/docs/\nnode_modules/\n.uncle/*\n!.uncle/docs/\n.uncle\n' > "$GPROJ5/.gitignore"
gitignore_load_config "$GPROJ5"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ5/.gitignore")" == $'.uncle/*\n!.uncle/docs/\nnode_modules/' ]] \
    || fail "duplicate .uncle rules were not normalized: $(cat "$GPROJ5/.gitignore")"
before="$(cat "$GPROJ5/.gitignore")"
gitignore_load_config "$GPROJ5"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ5/.gitignore")" == "$before" ]] \
    || fail "normalizing .uncle rules was not idempotent"

# Existing configurations must normalize legacy ignores too: this is the
# common upgrade path, and docs must be visible to git before the first new
# workflow is launched.
GPROJ6="$TMP/gitignore-existing-config"
mkdir -p "$GPROJ6/.uncle"
printf 'implementation.runner self-hosted\n' > "$GPROJ6/.uncle/config"
printf '.uncle/\n' > "$GPROJ6/.gitignore"
gitignore_load_config "$GPROJ6"
COUNT=$((COUNT + 1))
[[ "$(cat "$GPROJ6/.gitignore")" == $'.uncle/*\n!.uncle/docs/' ]] \
    || fail "an existing config did not unignore workflow docs: $(cat "$GPROJ6/.gitignore")"

if [[ "$status" -ne 0 || "$FAILED" -ne 0 ]]; then
    echo "tui-config-test.sh: failed"
    exit 1
fi

echo "tui-config-test.sh: all checks passed"
