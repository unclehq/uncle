#!/usr/bin/env python3
"""Full-screen terminal UI for uncle.

A curses interface: pick a workflow, then run the chosen driver while streaming
its output. The cline model, reasoning effort, and per-stage overrides are set
in the Configure screen (persisted to `.uncle/config`). A fixed status bar shows
the current model and Act/Plan mode for the running stage.
"""
import shlex
import shutil
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import importlib.util

try:
    import curses
except ImportError:  # Windows has no curses in the stdlib
    sys.stderr.write(
        "uncle: this screen needs curses.\n"
        "  Windows: pip install windows-curses\n"
        "  Linux:   install your distribution's python3 curses package\n"
        "The line-based menu in `uncle` is used instead.\n")
    raise SystemExit(1)

ROOT = os.path.dirname(os.path.realpath(__file__))
CLINE_CONFIG = os.environ.get("CLINE_CONFIG", os.path.expanduser("~/.cline/data/settings/providers.json"))

WORKFLOWS = [
    ("New application", [os.path.join(ROOT, "scripts", "stagegate.sh")]),
    ("From GitHub issue", [os.path.join(ROOT, "scripts", "from-issue.sh")]),
    ("Change request", [os.path.join(ROOT, "scripts", "change-workflow.sh")]),
]
EFFORTS = ["high", "medium", "low"]
ISSUE_MODES = [("auto", ""), ("change request", "--change"), ("new application", "--new")]
# The per-project config lives in the caller's project root, so each project
# gets its own model/effort/runner settings. The `uncle` launcher exports
# UNCLE_PROJECT_ROOT (= the cwd it was invoked from) because it cd's into the
# install libexec before launching this TUI; without it os.getcwd() would be
# the install dir and config edits would land in the wrong .uncle/.
_CONFIGURE_FIRST_RUN = object()  # sentinel: leave in place until set in __init__


def _project_root():
    root = os.environ.get("UNCLE_PROJECT_ROOT")
    if root and os.path.isabs(root):
        return root
    return os.getcwd()


def _default_config_path():
    return os.path.join(_project_root(), ".uncle", "config")


CONFIG_PATH = os.environ.get("UNCLE_CONFIG", _default_config_path())

# Every stage is configured on its own: which runner drives it, how much
# reasoning effort it gets, and — only when that runner is cline, which is the
# one runner whose CLI takes no useful default — which model it runs.
#
# Keys are the drivers' stage log names, so a key maps straight onto the
# WORKFLOW_*_<STAGE> variables the drivers already read.
AGENT, REVIEWER = "agent", "reviewer"
# Merge both workflow sequences, keeping branch-specific stages beside their
# counterparts and shared review/execution stages in execution order.
STAGES = [
    ("requirements", AGENT),
    ("baseline", AGENT),
    ("change-spec", AGENT),
    ("project-plan", AGENT),
    ("change-plan", AGENT),
    ("adversarial-review", REVIEWER),
    ("updated-plan", AGENT),
    ("updated-change-plan", AGENT),
    ("preflight", AGENT),
    ("implementation", AGENT),
    ("test-review", REVIEWER),
    ("manual-checklist", REVIEWER),
    ("execute-checklist", AGENT),
    ("final-audit", REVIEWER),
]
STAGE_SIDE = dict(STAGES)
CONFIG_STAGES = [name for name, _ in STAGES]

# Runners are offered per side, because the two sides are not interchangeable:
# an agent stage writes code and needs an agent CLI running with write access,
# a reviewer stage must be read-only. Each side has its own shim per runner —
# scripts/agent-*.sh and scripts/reviewer-*.sh — and the shim is what enforces
# that difference. codex, for instance, runs `--sandbox workspace-write` as an
# agent and `--sandbox read-only` as a reviewer.
AGENT_RUNNERS = ["cline", "claude", "kimi", "codex"]
REVIEWER_RUNNERS = ["cline", "codex", "claude", "kimi"]

# Applied to any stage the operator has not configured.
DEFAULT_RUNNER = "cline"
DEFAULT_EFFORT = "medium"
DEFAULT_CLINE_MODEL = "cline-pass/deepseek-v4-pro"

STAGE_FIELDS = ("runner", "effort", "model")

# Models offered in the Configure → model picker, grouped by plan.
#
# Each entry is (label, id). The id is what gets written to .uncle/config and
# passed to `cline -m`, and cline requires it in `modelType/model` form; the
# label is display only. A bare display name is rejected by cline with
# "invalid model format", so the picker must never store one.
MODEL_CATALOG = [
    ("Subscribed (ClinePass)", [
        ("Qwen3.8 Max", "cline-pass/qwen3.8-max"),
        ("GLM-5.2", "cline-pass/glm-5.2"),
        ("DeepSeek V4 Pro", "cline-pass/deepseek-v4-pro"),
        ("GLM-5.3-Flash", "cline-pass/glm-5.3-flash"),
        ("Kimi K3", "cline-pass/kimi-k3"),
        ("GLM-5.3", "cline-pass/glm-5.3"),
        ("Kimi K2.7 Code", "cline-pass/kimi-k2.7-code"),
        ("DeepSeek V4 Flash", "cline-pass/deepseek-v4-flash"),
        ("Kimi K2.6", "cline-pass/kimi-k2.6"),
        ("Qwen3.7 Plus", "cline-pass/qwen3.7-plus"),
        ("Qwen3.7 Max", "cline-pass/qwen3.7-max"),
        ("MiniMax-M3", "cline-pass/minimax-m3"),
        ("MiMo-V2.5-Pro", "cline-pass/mimo-v2.5-pro"),
        ("MiMo-V2.5", "cline-pass/mimo-v2.5"),
    ]),
    ("Free", [
        ("DeepSeek V4 Flash", "deepseek/deepseek-v4-flash"),
        ("GLM-5.3-Flash", "z-ai/glm-5.3-flash"),
        ("Laguna S 2.1", "poolside/laguna-s-2.1"),
    ]),
]

# id -> label, for the picker's display column and its filter.
MODEL_LABELS = {mid: label for _, entries in MODEL_CATALOG for label, mid in entries}


def valid_model_id(value):
    """cline model ids are `modelType/model`; an empty value means its default."""
    return not value or "/" in value

# Full description for each Configure item. Only the description of the row
# currently under the cursor is shown, in a panel to the right of the options.
CONFIG_DESC = {
    "preflight": (
        "Checks required tools, browser access, input data, and reviewer "
        "arrangements before a new application is implemented. Missing "
        "prerequisites pause the run."
    ),
    "test-review": (
        "Independently reviews acceptance coverage, assertions, expected "
        "results, and evidence that critical tests reject defects. Failures "
        "return the new application to repair and a fresh diff approval."
    ),
    "field:runner": (
        "The CLI that drives this stage. cline, claude, kimi, and codex can "
        "run an agent stage, where they write code; cline, codex, claude, and kimi "
        "can run the read-only reviewer stages. Each stage picks its own, so a cheap model "
        "can transcribe requirements while a strong one plans, and the "
        "reviewer can be a different program from the implementer. Only cline "
        "takes a model below: claude, kimi, and codex are given no model flag "
        "and use their own default."
    ),
    "field:effort": (
        "Reasoning effort for this stage: high, medium, or low. Higher effort "
        "usually means more careful work and more tokens. Every runner "
        "supports it — cline as --thinking, claude as an effort flag, codex as "
        "model_reasoning_effort."
    ),
    "field:model": (
        "The cline model this stage runs, as a `modelType/model` id (for "
        "example cline-pass/kimi-k3). Shown only when the runner is cline, "
        "because it is the only runner uncle passes a model to. A display "
        "name such as \"Kimi K3\" is not an id and is refused before the "
        "stage starts."
    ),
    "adversarial-review": (
        "The reviewer stage that attacks the plan before any code is written, "
        "looking for gaps, wrong assumptions, and unstated failure modes. It "
        "is read-only and owns its own artifact, so give it a runner that did "
        "not write the plan it is reviewing."
    ),
    "manual-checklist": (
        "The reviewer stage that writes the manual verification checklist from "
        "the frozen, approved artifacts. It reads the plan, the source, and "
        "the automated test report, and produces the checks a human runs by "
        "hand."
    ),
    "final-audit": (
        "The reviewer stage that audits the finished change and returns the "
        "verdict that decides whether the run can complete. READY or READY "
        "WITH NON-BLOCKING ISSUES finishes; anything else stops the run."
    ),
    "runner": (
        "The CLI program that drives the agent and reviewer stages of every "
        "workflow. Choose one of cline, claude, kimi, or codex. The runner "
        "decides which agent and reviewer scripts the workflow invokes, so you "
        "can plug in a different coding agent without touching the rest of the "
        "pipeline. Press Enter on this row to cycle through the runners."
    ),
    "model": (
        "The global model ID used for all agent stages (requirements, planning, "
        "implementation, and so on). Every stage that does not set its own "
        "override below falls back to this model. Leave it empty to use "
        "cline's default, which is the last-used provider's model. Individual "
        "stages can still override it further down this list."
    ),
    "effort": (
        "The reasoning effort applied to every stage, one of high, medium, or "
        "low. Effort controls how much thought the model invests in each step; "
        "higher effort usually means more careful planning and reviewing but "
        "also more tokens. Use medium as a balanced default, high for complex "
        "changes, and low for quick iterations. You can type your own value in "
        "the edit screen or cycle it from this row."
    ),
    "requirements": (
        "The stage that interprets the brief and turns it into a concrete, "
        "testable set of requirements. It runs first in the New application "
        "and From GitHub issue workflows. Give it a model ID to use a dedicated "
        "model for this stage, or leave it at (default) to use the global model."
    ),
    "project-plan": (
        "Writes the project plan that translates the requirements into an "
        "ordered set of work. This stage benefits from a strong planning model. "
        "Leave it at (default) to use the global model, or set a specific model "
        "ID if you always want planning to run on a particular model."
    ),
    "updated-plan": (
        "Revises the project plan after the adversarial review catches gaps or "
        "weak spots. Because it reacts to critique, many people route it to a "
        "capable reviewer-oriented model. Leave it at (default) to use the "
        "global model."
    ),
    "implementation": (
        "Writes the actual code and runs the tests. This is the stage where "
        "correctness and respect for existing conventions matter most. Set a "
        "model you trust for coding, or leave it at (default) to use the "
        "global model."
    ),
    "execute-checklist": (
        "Runs the manual checklist against the finished implementation and "
        "records the results. It works through every item and reports pass or "
        "fail so you can see what still stands between the code and shipping. "
        "Leave it at (default) to use the global model."
    ),
    "baseline": (
        "Records the current behavior of the system before a change is made, "
        "so the change can be verified against a known starting point. This "
        "stage runs ahead of change work to capture a before snapshot. Leave "
        "it at (default) to use the global model."
    ),
    "change-spec": (
        "Writes the change specification that precisely defines what will "
        "change and why, including scope, interfaces, and acceptance criteria. "
        "A clear spec keeps the later change planning grounded. Leave it at "
        "(default) to use the global model."
    ),
    "change-plan": (
        "Writes the change plan, turning the change specification into an "
        "ordered implementation plan. Good for routing to a planning model. "
        "Leave it at (default) to use the global model."
    ),
    "updated-change-plan": (
        "Revises the change plan after the adversarial review identifies "
        "improvements or gaps. Like the update-plan stage for new applications, "
        "it reacts to critique. Leave it at (default) to use the global model."
    ),
    "reviewer": (
        "The model used for the adversarial review and audit stages. It is "
        "kept separate from the agent model so you can pair a strong coder "
        "with an even stronger critic. Leave it at (default) to use the global "
        "model."
    ),
}

# The mark shown on the main menu: a fedora'd face with a mustache.
LOGO = [
    "                #@@@@@@##@@@@@@#",
    "                @@@@@@@@@@@@@@@@",
    "                @@@@@@@@@@@@@@@@",
    "               #@@@@@@@@@@@@@@@@#",
    "               @@@@@@@@@@@@@@@@@@",
    "    #@@@@@@@@@ @@@@@@@@@@@@@@@@@@ @@@@@@@@@#",
    "    @@@@@@@@@@                    @@@@@@@@@@",
    "     @@@@@@@@@@@@@@##########@@@@@@@@@@@@@@",
    "       #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#",
    "          #@@##@@@@@@@@@@@@@@@@@@##@@#",
    "       #@@@@@# @@@@@@@@##@@@@@@@@ #@@@@@#",
    "     @@@@@@@@@  @@@@@@    @@@@@@  @@@@@@@@@",
    "    @@@@@@@@@@@                  @@@@@@@@@@@",
    "     @@@@@@@@@@@                @@@@@@@@@@@",
    "      #@@@@@@@@@@              @@@@@@@@@@#",
    "       ##@@@@@@@@@@          @@@@@@@@@@##",
    "    #@@@@@@@@@@@@@@@@#    #@@@@@@@@@@@@@@@@#",
    "  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@",
    "#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#",
    " #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#",
    "    #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#",
    "       #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#",
]
LOGO_W = max(len(line) for line in LOGO)


# Sentinel meaning "the global / default value, not a specific stage".
GLOBAL = "__global__"


def _env_name(prefix, stage):
    return prefix + "".join(c if c.isalnum() else "_" for c in stage.upper())


def stage_env_var(stage):
    return _env_name("WORKFLOW_MODEL_", stage)


def stage_effort_var(stage):
    return _env_name("WORKFLOW_EFFORT_", stage)


def runner_command(runner, side):
    """The CLI that runs one stage, on the agent side or the reviewer side."""
    shim = lambda name: os.path.join(ROOT, "scripts", name)
    if side == REVIEWER:
        table = {
            "cline": shim("reviewer-cline.sh"),
            "codex": "codex",
            "claude": shim("reviewer-claude.sh"),
            "kimi": shim("reviewer-kimi.sh"),
        }
        return table.get(runner, table["cline"])
    table = {
        "cline": shim("agent-cline.sh"),
        "claude": "claude",
        "kimi": shim("agent-kimi.sh"),
        "codex": shim("agent-codex.sh"),
    }
    return table.get(runner, table["cline"])


def runners_for(side):
    return REVIEWER_RUNNERS if side == REVIEWER else AGENT_RUNNERS


def stage_runner_var(stage):
    prefix = ("WORKFLOW_REVIEWER_CMD_" if STAGE_SIDE.get(stage) == REVIEWER
              else "WORKFLOW_AGENT_CMD_")
    return _env_name(prefix, stage)


def list_models():
    models = []
    try:
        with open(CLINE_CONFIG) as fh:
            data = json.load(fh)
        for prov in (data.get("providers") or {}).values():
            model = (prov.get("settings") or {}).get("model")
            if model:
                models.append(model)
    except Exception:
        pass
    return models


def default_model():
    """The model cline uses when no `-m` is given: the last-used provider's model."""
    try:
        with open(CLINE_CONFIG) as fh:
            data = json.load(fh)
        provs = data.get("providers") or {}
        last = data.get("lastUsedProvider")
        if last and last in provs:
            model = (provs[last].get("settings") or {}).get("model")
            if model:
                return model
        for prov in provs.values():
            model = (prov.get("settings") or {}).get("model")
            if model:
                return model
    except Exception:
        pass
    return ""


class UncleTUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.models = list_models()
        self.default_model = default_model()
        self.state = "menu"
        self.sel = 0
        self.workflow_idx = None
        self.issue = ""
        self.issue_mode = ""
        self.input_buf = ""
        self.output = []
        self.proc = None
        self.out_q = queue.Queue()
        self.partial = ""
        self.proc_done = False
        self.prompt_kind = ""
        self.prompt_text = ""
        self.prompt_buf = ""
        self.prompt_seen = 0
        self.status_runner = ""
        self.gate_file = ""
        self.notice_lines = []
        self.view_lines = []
        self.view_title = ""
        self.view_scroll = 0
        self.status_path = None
        self.status_pos = 0
        self.session_stats = None
        self.status_model = ""
        self.status_effort = ""
        self.status_mode = ""
        self.status_stage = ""
        self.status_stage_index = 0
        self.status_stage_total = 0
        # Per-stage settings, keyed by stage log name. Absent means "default".
        self.stage_runners = {}
        self.stage_models = {}
        self.stage_efforts = {}
        self.notice = ""
        self.config_sel = 0
        self.config_scroll = 0
        self.stage_target = CONFIG_STAGES[0]
        self.stage_sel = 0
        self.pick_sel = 0
        self.pick_scroll = 0
        self.pick_filter = ""
        self.picker_kind = "model"
        self.picker_target = CONFIG_STAGES[0]
        self.first_run = False
        self._config_stamp = None
        self._reload_tick = 0
        self.load_config()
        if self.state == "menu" and self.first_run:
            # First time in this project root: open the Configure screen so
            # this project gets set up before anything runs, and create the
            # workspace dir the scripts will write their state/logs into.
            self.state = "config"
            self.config_sel = 0
            try:
                os.makedirs(os.path.join(_project_root(), ".uncle", "workspace"),
                            exist_ok=True)
            except Exception:
                pass
            # Every gate asks you to approve a markdown document. Without a
            # reader installed, the [v] key falls back to raw text — worth
            # saying once, on the way to Configure, rather than at the gate.
            if not self._viewer_command("x"):
                self.state = "notice"
                self.notice_lines = [
                    "Gates ask you to approve a markdown document.",
                    "uncle can show it to you in this window, with:",
                    "",
                    "    brew install glow      (preferred)",
                    "    brew install bat",
                    "",
                    "Neither is installed, so [v] at a gate will show",
                    "the raw text instead. Install either one and it is",
                    "picked up on the next run.",
                ]

    # ---- colors (cline's CLI palette) ----
    def _setup_colors(self):
        self.color = {"title": 0, "accent": 0, "good": 0, "sel": 0, "cursor": 0, "warning": curses.A_BOLD, "bad": curses.A_BOLD, "muted": curses.A_DIM}
        if not curses.has_colors():
            return
        try:
            curses.start_color()
        except Exception:
            return
        try:
            curses.use_default_colors()
            bg = -1
        except Exception:
            bg = curses.COLOR_BLACK
        idx = [0]

        def reg(name, fg, attr=0):
            idx[0] += 1
            curses.init_pair(idx[0], fg, bg)
            self.color[name] = curses.color_pair(idx[0]) | attr

        reg("title", curses.COLOR_CYAN, curses.A_BOLD)
        reg("accent", curses.COLOR_CYAN)
        reg("good", curses.COLOR_GREEN)
        reg("warning", curses.COLOR_YELLOW)
        reg("bad", curses.COLOR_RED, curses.A_BOLD)
        idx[0] += 1
        curses.init_pair(idx[0], curses.COLOR_BLACK, curses.COLOR_CYAN)
        self.color["sel"] = curses.color_pair(idx[0]) | curses.A_BOLD
        idx[0] += 1
        curses.init_pair(idx[0], curses.COLOR_YELLOW, bg)
        self.color["cursor"] = curses.color_pair(idx[0])

    # ---- item lists ----
    def menu_items(self):
        return [w[0] for w in WORKFLOWS] + ["Configure stages", "Quit"]

    def items(self):
        if self.state == "menu":
            return self.menu_items()
        if self.state == "issue_mode":
            return [m[0] for m in ISSUE_MODES]
        if self.state == "config":
            return self._config_items()
        if self.state == "stage":
            return self._stage_items()
        return []

    # ---- config rows ----
    # The Configure screen lists stages, one row each. Enter opens that
    # stage's own popup, which is where runner / effort / model are chosen.
    # There are no global rows: a setting that applies to one stage is easier
    # to reason about than an inheritance chain, and the runner already
    # decides whether a model is meaningful at all.
    def _config_row(self):
        if 0 <= self.config_sel < len(CONFIG_STAGES):
            return CONFIG_STAGES[self.config_sel]
        return ""

    # ---- effective values ----
    def stage_runner(self, stage):
        runner = self.stage_runners.get(stage, "")
        if runner in runners_for(STAGE_SIDE.get(stage, AGENT)):
            return runner
        return runner or DEFAULT_RUNNER

    def stage_effort(self, stage):
        return self.stage_efforts.get(stage, "") or DEFAULT_EFFORT

    def stage_model(self, stage):
        """The model for a stage, or "" when its runner takes none."""
        if self.stage_runner(stage) != "cline":
            return ""
        return self.stage_models.get(stage, "") or DEFAULT_CLINE_MODEL

    def stage_fields(self, stage):
        """The fields this stage's popup shows: model only for cline."""
        if self.stage_runner(stage) == "cline":
            return ["runner", "effort", "model"]
        return ["runner", "effort"]

    def _field_value(self, stage, field):
        """The stored value, empty when the stage inherits the default."""
        if field == "runner":
            return self.stage_runners.get(stage, "")
        if field == "effort":
            return self.stage_efforts.get(stage, "")
        if field == "model":
            return self.stage_models.get(stage, "")
        return ""

    def _field_display(self, stage, field):
        stored = self._field_value(stage, field)
        if stored:
            if field == "model":
                label = MODEL_LABELS.get(stored, "")
                return "%s  %s" % (stored, label) if label else stored
            return stored
        if field == "runner":
            return "%s  (default)" % DEFAULT_RUNNER
        if field == "effort":
            return "%s  (default)" % DEFAULT_EFFORT
        label = MODEL_LABELS.get(DEFAULT_CLINE_MODEL, "")
        return "%s  (default)%s" % (DEFAULT_CLINE_MODEL, "  " + label if label else "")

    def _set_field(self, stage, field, value):
        value = (value or "").strip()
        self.maybe_reload()
        store = {"runner": self.stage_runners,
                 "effort": self.stage_efforts,
                 "model": self.stage_models}.get(field)
        if store is None:
            return
        if value:
            store[stage] = value
        else:
            store.pop(stage, None)
        self.save_config()

    def _config_items(self):
        """One row per stage: the stage, its runner, and what that runner uses."""
        width = max(len(s) for s in CONFIG_STAGES)
        rows = []
        for stage in CONFIG_STAGES:
            parts = [self.stage_runner(stage)]
            model = self.stage_model(stage)
            if model:
                parts.append(MODEL_LABELS.get(model, model))
            parts.append(self.stage_effort(stage))
            rows.append("%s  %s" % (stage.ljust(width), " · ".join(parts)))
        return rows

    def _stage_items(self):
        """Rows of the open stage's popup."""
        stage = self.stage_target
        rows = []
        for field in self.stage_fields(stage):
            rows.append("%s  %s" % (field.ljust(7), self._field_display(stage, field)))
        return rows

    def _stage_field(self):
        fields = self.stage_fields(self.stage_target)
        if 0 <= self.stage_sel < len(fields):
            return fields[self.stage_sel]
        return ""

    def _open_stage(self, stage):
        self.stage_target = stage
        self.stage_sel = 0
        self.notice = ""
        self.state = "stage"

    def _config_desc(self):
        """Description of the highlighted stage, or of the highlighted field."""
        if self.state == "stage":
            field = self._stage_field()
            desc = CONFIG_DESC.get("field:%s" % field, "")
            if field == "runner":
                side = STAGE_SIDE.get(self.stage_target, AGENT)
                desc += " This is a %s stage, so its choices are %s." % (
                    side, ", ".join(runners_for(side)))
            return desc
        return CONFIG_DESC.get(self._config_row(), "")

    # ---- generic picker (model / effort / runner) ----
    def _picker_rows(self):
        """Rows for the active picker: (kind, text), kind in header/option/model/custom."""
        if self.picker_kind == "effort":
            return [("option", e) for e in EFFORTS] + [("custom", "Custom… (type an effort)")]
        if self.picker_kind == "runner":
            side = STAGE_SIDE.get(self.picker_target, AGENT)
            return [("option", r) for r in runners_for(side)]
        rows = []
        for group, entries in MODEL_CATALOG:
            rows.append(("header", group))
            for _label, mid in entries:
                rows.append(("model", mid))
        rows.append(("custom", "Custom… (type a model id)"))
        return rows

    def _picker_filtered(self):
        flt = self.pick_filter.strip().lower()
        rows = self._picker_rows()
        if not flt:
            return rows
        out = []
        for kind, text in rows:
            if kind == "header":
                continue
            label = MODEL_LABELS.get(text, "")
            if kind == "custom" or flt in text.lower() or flt in label.lower():
                out.append((kind, text))
        return out

    def _picker_current(self):
        """The effective value the active picker is choosing on behalf of."""
        stage = self.picker_target
        if self.picker_kind == "runner":
            return self.stage_runner(stage)
        if self.picker_kind == "effort":
            return self.stage_effort(stage)
        return self.stage_model(stage)

    def _open_picker(self, kind, target):
        self.notice = ""
        self.picker_kind = kind
        self.picker_target = target
        self.pick_filter = ""
        cur = (self._picker_current() or "").lower()
        rows = self._picker_filtered()
        self.pick_sel = 0
        for i, (k, text) in enumerate(rows):
            if k in ("model", "option") and text.lower() == cur:
                self.pick_sel = i
                break
        sel_idx = [i for i, (k, _) in enumerate(rows) if k != "header"]
        if self.pick_sel not in sel_idx and sel_idx:
            self.pick_sel = sel_idx[0]
        self.pick_scroll = 0
        self.state = "picker"

    def _picker_move(self, delta):
        """Move selection to the next selectable (non-header) row, wrapping."""
        rows = self._picker_filtered()
        n = len(rows)
        if n == 0:
            return
        sel_idx = [i for i, (k, _) in enumerate(rows) if k != "header"]
        if not sel_idx:
            return
        pos = sel_idx.index(self.pick_sel) if self.pick_sel in sel_idx else 0
        self.pick_sel = sel_idx[(pos + delta) % len(sel_idx)]

    def _reset_pick_sel(self):
        """Set selection to the first selectable (non-header) row, if any."""
        rows = self._picker_filtered()
        for i, (k, _) in enumerate(rows):
            if k != "header":
                self.pick_sel = i
                return
        self.pick_sel = 0

    def _picker_confirm(self):
        rows = self._picker_filtered()
        if not rows:
            return
        kind, text = rows[self.pick_sel]
        if kind == "custom":
            self.state = "config_edit"
            self.notice = ""
            self.input_buf = self.pick_filter.strip() or self._picker_current()
            return
        self._set_field(self.picker_target, self.picker_kind, text)
        # Choosing a non-cline runner drops the model row out of the popup.
        self.stage_sel = min(self.stage_sel,
                             len(self.stage_fields(self.picker_target)) - 1)
        self.state = "stage"

    def cmd_for(self):
        if self.workflow_idx == 1:
            cmd = list(WORKFLOWS[1][1]) + [self.issue]
            if self.issue_mode:
                cmd.append(self.issue_mode)
            return cmd
        return list(WORKFLOWS[self.workflow_idx][1])

    # ---- config ----
    #
    # Grammar, one setting per line:
    #
    #   <stage>.runner  cline | claude | kimi | codex
    #   <stage>.effort  high | medium | low
    #   <stage>.model   a cline model id, and only for a cline stage
    #
    # Older files carried global `runner` / `model` / `effort` lines, a bare
    # `<stage> <model>` line, and a `reviewer <model>` line. Those are still
    # read — as the seed for stages the file does not configure explicitly —
    # and are never written back, so the first save migrates the file.
    LEGACY_REVIEWER_KEY = "reviewer"

    def load_config(self):
        exists = os.path.exists(CONFIG_PATH)
        self.stage_runners = {}
        self.stage_models = {}
        self.stage_efforts = {}
        if not exists:
            # First time in this project root: no config file yet. Mark it so
            # the TUI can drop straight into the Configure screen.
            self.first_run = True
            self._config_stamp = None
            return self.first_run
        self.first_run = False
        legacy = {"runner": "", "model": "", "effort": "", "reviewer": ""}
        try:
            with open(CONFIG_PATH) as fh:
                for line in fh:
                    line = line.split("#", 1)[0].strip()
                    if not line:
                        continue
                    parts = line.split(None, 1)
                    if len(parts) != 2:
                        continue
                    key, val = parts[0].strip(), parts[1].strip()
                    if key in legacy:
                        legacy[key] = val
                    elif "." in key:
                        stage, field = key.rsplit(".", 1)
                        if stage in STAGE_SIDE and field in STAGE_FIELDS:
                            self._store_for(field)[stage] = val
                    elif key in STAGE_SIDE:
                        # Legacy bare "<stage> <model>".
                        self.stage_models[key] = val
        except Exception:
            pass
        self._seed_from_legacy(legacy)
        self._config_stamp = self._stamp()
        return self.first_run

    def _stamp(self):
        """Cheap identity of the config file, to notice edits from outside."""
        try:
            st = os.stat(CONFIG_PATH)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def maybe_reload(self):
        """Re-read .uncle/config if it changed since we last read or wrote it.

        Someone editing the file by hand — or a second uncle in another
        terminal — should not be silently overwritten by this screen's stale
        copy, and should not have to restart uncle to see their change.
        """
        if self._stamp() == self._config_stamp:
            return False
        first_run = self.first_run
        self.load_config()
        self.first_run = first_run
        self._clamp_selection()
        return True

    def _clamp_selection(self):
        """Keep the cursors on rows that still exist after a reload."""
        self.config_sel = max(0, min(getattr(self, "config_sel", 0),
                                     len(CONFIG_STAGES) - 1))
        if getattr(self, "stage_target", "") not in STAGE_SIDE:
            self.stage_target = CONFIG_STAGES[0]
        fields = self.stage_fields(self.stage_target)
        self.stage_sel = max(0, min(getattr(self, "stage_sel", 0), len(fields) - 1))

    def _store_for(self, field):
        return {"runner": self.stage_runners,
                "effort": self.stage_efforts,
                "model": self.stage_models}[field]

    def _seed_from_legacy(self, legacy):
        """Turn old global settings into per-stage ones, without overwriting."""
        for stage in CONFIG_STAGES:
            if legacy["runner"] and stage not in self.stage_runners:
                self.stage_runners[stage] = legacy["runner"]
            if legacy["effort"] and stage not in self.stage_efforts:
                self.stage_efforts[stage] = legacy["effort"]
            model = legacy["model"]
            if STAGE_SIDE.get(stage) == REVIEWER and legacy["reviewer"]:
                model = legacy["reviewer"]
            if model and stage not in self.stage_models:
                self.stage_models[stage] = model

    def save_config(self):
        header = (
            "# Uncle per-stage config: every stage picks its own runner,\n"
            "# reasoning effort, and \u2014 for a cline stage \u2014 model.\n"
            "# Format: <stage>.runner | <stage>.effort | <stage>.model VALUE\n"
            "#   (VALUE = a runner name, a reasoning effort, or a cline model\n"
            "#   id in modelType/model form). Edit from `uncle` -> Configure,\n"
            "#   or by hand.\n"
        )
        try:
            with open(CONFIG_PATH, "w") as fh:
                fh.write(header)
                for stage in CONFIG_STAGES:
                    lines = []
                    runner = self.stage_runners.get(stage, "")
                    if runner:
                        lines.append("%s.runner %s\n" % (stage, runner))
                    if self.stage_efforts.get(stage):
                        lines.append("%s.effort %s\n" % (stage, self.stage_efforts[stage]))
                    # A model belongs to a cline stage only; keeping one on a
                    # claude/kimi/codex stage would be a value nothing reads.
                    if self.stage_models.get(stage) and self.stage_runner(stage) == "cline":
                        lines.append("%s.model %s\n" % (stage, self.stage_models[stage]))
                    if lines:
                        fh.write("\n")
                        for line in lines:
                            fh.write(line)
        except Exception:
            pass
        self._config_stamp = self._stamp()

    def stage_env(self):
        """What the driver needs in its environment — which is almost nothing.

        Per-stage settings are deliberately *not* exported. A run stops at four
        human gates, and that is exactly when an operator decides the next
        stage should run somewhere else; a snapshot taken at launch could not
        see that edit. So the drivers read .uncle/config themselves, at the
        moment each stage starts, and this only tells them which file that is.

        Everything the screen changes is written to that file immediately, so
        the file and the screen never disagree.
        """
        return {"UNCLE_CONFIG": CONFIG_PATH}

    # ---- status channel ----
    def poll_status(self):
        if not self.status_path:
            return False
        before = (self.status_model, self.status_mode, self.status_stage,
                  self.status_stage_index, self.status_stage_total)
        changed = False
        try:
            with open(self.status_path) as fh:
                fh.seek(self.status_pos)
                while True:
                    line = fh.readline()
                    if not line or not line.endswith("\n"):
                        break
                    self._apply_status(line)
                    self.status_pos = fh.tell()
                    changed = True
        except OSError:
            pass
        return changed or before != (self.status_model, self.status_mode, self.status_stage,
                                     self.status_stage_index, self.status_stage_total)

    def _apply_status(self, line):
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except Exception:
            return
        self._restore_session_totals()
        stats = getattr(self, "session_stats", None)
        stage = ev.get("stage") or self.status_stage
        if stats is not None and stage:
            if ev.get("event") == "start":
                stats["active"].setdefault(stage, time.time())
            elif ev.get("event") == "usage":
                stats["live"][stage] = ev
        if ev.get("event") == "start":
            self.status_model = ev.get("model", "")
            self.status_effort = ev.get("effort", "")
            self.status_mode = ev.get("mode", "")
            self.status_stage = ev.get("stage", "")
            self.status_stage_index = int(ev.get("stage_index", 0) or 0)
            self.status_stage_total = int(ev.get("stage_total", 0) or 0)
        elif ev.get("event") == "usage":
            self.status_model = ev.get("model", self.status_model)
            self.status_mode = ev.get("mode", self.status_mode)

    # ---- running ----
    def start_workflow(self):
        fd, self.status_path = tempfile.mkstemp(prefix="uncle-status-", suffix=".jsonl")
        os.close(fd)
        env = dict(os.environ)
        env.update(self.stage_env())
        env["UNCLE_STATUS_FILE"] = self.status_path
        self.status_pos = 0
        self.panel_scroll = None
        self.proc_done = False
        metrics = os.path.join(_project_root(), ".uncle", "workspace", "metrics")
        self.session_stats = {"active": {}, "live": {}, "records": [], "tick": -1,
                              "seen": set(os.listdir(metrics)) if os.path.isdir(metrics) else set()}
        self._restore_session_totals()
        self.output = []
        self.partial = ""
        self.prompt_kind = ""
        self.prompt_text = ""
        self.prompt_buf = ""
        self.prompt_seen = 0
        self.status_model = ""
        self.status_effort = ""
        self.status_runner = ""
        self.status_stage = ""
        self.gate_file = ""
        # stdin is a pipe because the workflow asks questions: four human
        # gates, plus the odd retry or confirmation. Under curses the driver
        # cannot have the terminal, so the answers are typed into this screen
        # and written down the pipe.
        self.proc = subprocess.Popen(self.cmd_for(), cwd=_project_root(), env=env,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        """Read raw chunks, not lines.

        A question is written without a trailing newline — `[Y/N] ` and then a
        blocking read — so iterating by line would block on the very output
        that needs answering.
        """
        fd = self.proc.stdout.fileno()
        try:
            while True:
                # os.read returns as soon as anything is there; a buffered
                # read(n) would sit on a prompt waiting for n characters.
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                self.out_q.put(chunk.decode("utf-8", "replace"))
        finally:
            self.out_q.put(None)

    def drain_output(self):
        got = False
        before = (self.proc_done, self.prompt_kind)
        try:
            while True:
                chunk = self.out_q.get_nowait()
                if chunk is None:
                    self.proc_done = True
                    break
                got = True
                self.partial += chunk
                while "\n" in self.partial:
                    line, self.partial = self.partial.split("\n", 1)
                    self._absorb_line(line.rstrip("\r"))
        except queue.Empty:
            pass
        if got:
            self.prompt_seen = 0
        self._detect_prompt()
        return got or before != (self.proc_done, self.prompt_kind)

    def _absorb_line(self, line):
        self.output.append(line)
        if len(self.output) > 4000:
            del self.output[:500]
        self._read_banner(line)

    # The drivers announce each stage before running it. Parsing that is how
    # this screen knows what is running: only the cline shims report through
    # the status channel, so a kimi or codex stage would otherwise leave the
    # status bar showing whatever ran last — or, worse, cline's own last-used
    # model, which was never this stage's model at all.
    def _read_banner(self, line):
        text = line.strip()
        # A gate opens with this banner, then reads a bare newline before it
        # asks the real question. bash prints a `read -p` prompt only to a
        # terminal, so over a pipe that read is invisible: nothing appears and
        # the run looks hung. Answer it here — the decision is the [Y/N] that
        # follows, and that one gets a modal.
        if text.startswith("HUMAN REVIEW REQUIRED:"):
            self.gate_file = text.split(":", 1)[1].strip()
            self._send_raw("")
            return
        if text.startswith("Ready to approve") or text.startswith("Ready to acknowledge"):
            return
        for prefix, mode in (("Launching agent (", "act"),
                             ("Launching reviewer (", "review"),
                             ("Starting background reviewer (", "review")):
            if text.startswith(prefix):
                rest = text[len(prefix):]
                cmd, _, tail = rest.partition(")")
                self.status_runner = self._runner_name(cmd)
                stage = tail.split(":", 1)[1].strip() if ":" in tail else ""
                self.status_stage = stage.replace("stage: ", "").strip() or self.status_stage
                self.status_mode = mode
                self.status_model = ""
                self.status_effort = ""
                return
        if text.startswith("Model: "):
            model = text[len("Model: "):]
            for sep in ("  Effort:", " (effort:", "  Cap:"):
                model = model.split(sep, 1)[0]
            self.status_model = model.strip()

    @staticmethod
    def _runner_name(cmd):
        """`.../scripts/agent-kimi.sh` reads as `kimi`; a bare `codex` as itself."""
        name = os.path.basename(cmd.strip())
        if name.endswith(".sh"):
            name = name[:-3]
        for prefix in ("agent-", "reviewer-"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        return name

    # ---- viewing the document a gate is about ----
    #
    # The driver's advice is to open the file in another terminal. That works,
    # but a gate that cannot show you what you are approving is half a gate.
    #
    # A rendered markdown reader is worth handing the screen to, so glow and
    # bat are used when they are installed, in that order, in this window: the
    # screen is released, the reader runs as it normally would, and the TUI is
    # restored when it exits. Without either, the built-in pager below shows
    # the raw text rather than refusing.
    def _viewer_command(self, full):
        """glow, then bat, whichever is on PATH — installed anywhere.

        `less` is only used when it is there too: it is standard on macOS and
        Linux and present in Git Bash, but not in a bare Windows shell, and
        glow pages well enough on its own.
        """
        quoted = shlex.quote(full)
        if shutil.which("glow"):
            if shutil.which("less"):
                return "glow %s | less" % quoted
            return "glow -p %s" % quoted
        if shutil.which("bat"):
            return "bat %s" % quoted
        return ""

    def _open_viewer(self, path):
        full = path if os.path.isabs(path) else os.path.join(_project_root(), path)
        if not os.path.exists(full):
            self.view_lines = ["not found: %s" % full]
            self.view_title = path
            self.view_scroll = 0
            self.state = "viewer"
            return

        cmd = self._viewer_command(full)
        if cmd:
            self._run_in_terminal(cmd)
            return

        try:
            with open(full, errors="replace") as fh:
                self.view_lines = fh.read().splitlines() or ["(empty file)"]
        except Exception as exc:
            self.view_lines = ["could not read %s" % full, str(exc)]
        self.view_title = path
        self.view_scroll = 0
        self.state = "viewer"

    def _run_in_terminal(self, cmd):
        """Hand the terminal to an external reader, then take it back.

        def_prog_mode saves the curses screen state; endwin restores the
        terminal so the reader gets a normal tty. After it exits,
        reset_prog_mode and a full redraw put the TUI back as it was.
        """
        try:
            curses.def_prog_mode()
            curses.endwin()
        except curses.error:
            pass
        try:
            subprocess.call(cmd, shell=True)
        except Exception:
            pass
        try:
            curses.reset_prog_mode()
            self.stdscr.clearok(True)
            self.stdscr.refresh()
        except curses.error:
            pass

    def _draw_viewer(self, h, w):
        head = " %s  —  j/k or arrows scroll, q back " % self.view_title
        try:
            self.stdscr.attrset(self.color["sel"] | curses.A_REVERSE)
            self.stdscr.addnstr(0, 0, head.ljust(w)[: w - 1], w - 1)
            self.stdscr.attrset(0)
        except curses.error:
            self.stdscr.attrset(0)
        body = max(1, h - 2)
        self.view_scroll = max(0, min(self.view_scroll,
                                      max(0, len(self.view_lines) - body)))
        for i in range(body):
            idx = self.view_scroll + i
            if idx >= len(self.view_lines):
                break
            try:
                self.stdscr.addnstr(1 + i, 0, self.view_lines[idx], w - 1)
            except curses.error:
                pass
        pos = " %d-%d of %d " % (self.view_scroll + 1,
                                 min(len(self.view_lines), self.view_scroll + body),
                                 len(self.view_lines))
        try:
            self.stdscr.attrset(curses.A_REVERSE)
            self.stdscr.addnstr(h - 1, 0, pos.ljust(w)[: w - 1], w - 1)
            self.stdscr.attrset(0)
        except curses.error:
            self.stdscr.attrset(0)

    # ---- questions from the driver ----
    def _detect_prompt(self):
        """A stable, unterminated line means the driver is waiting on us.

        Everything the drivers print ends in a newline except a prompt, so the
        leftover partial line is the question. It has to be stable for a few
        ticks, so a chunk that arrives mid-line is not mistaken for one.
        """
        if self.prompt_kind:
            return
        text = self.partial.strip()
        if not text:
            return
        self.prompt_seen += 1
        if self.prompt_seen < 3:
            return
        plain = self._strip_ansi(text)
        upper = plain.upper()
        if "[Y/N]" in upper:
            self.prompt_kind = "confirm"
        elif "PRESS ENTER" in upper:
            self.prompt_kind = "enter"
        else:
            self.prompt_kind = "input"
        self.prompt_text = plain
        self.prompt_buf = ""

    @staticmethod
    def _strip_ansi(text):
        out = []
        i = 0
        while i < len(text):
            if text[i] == "\033":
                while i < len(text) and text[i] not in "m":
                    i += 1
                i += 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)

    def _send_raw(self, answer):
        """Write one line to the driver's stdin without touching modal state."""
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            self.proc.stdin.write((answer + "\n").encode())
            self.proc.stdin.flush()
        except Exception:
            pass

    def answer_prompt(self, answer):
        """Send one line down the driver's stdin and close the modal."""
        if not self.proc or self.proc.poll() is not None:
            self.prompt_kind = ""
            return
        try:
            self.proc.stdin.write((answer + "\n").encode())
            self.proc.stdin.flush()
        except Exception:
            pass
        # Keep the answer in the transcript, so the log reads like a session.
        self._absorb_line("%s%s" % (self.partial.rstrip(), answer))
        self.partial = ""
        self.prompt_kind = ""
        self.prompt_text = ""
        self.prompt_buf = ""
        self.prompt_seen = 0

    def stop_workflow(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.status_model = ""
        self.status_effort = ""
        self.status_mode = ""
        self.status_stage = ""
        self.status_stage_index = 0
        self.status_stage_total = 0

    # ---- drawing ----
    def draw(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()
        if self.state in ("running", "viewer"):
            panel = min(34, w // 3) if w >= 60 else 0
            self._draw_running(h, w - panel)
            if panel:
                self._draw_session_stats(h, w, panel)
        elif self.state == "notice":
            self._draw_notice(h, w)
        else:
            self._draw_prompt(h, w)
        self._draw_status(h, w)
        self.stdscr.refresh()

    def _draw_running(self, h, w):
        if self.state == "viewer":
            self._draw_viewer(h, w)
            return
        tail = list(self.output)
        if self.partial.strip() and not self.prompt_kind:
            tail.append(self.partial.rstrip())
        for i, line in enumerate(tail[-(h - 1):]):
            try:
                self.stdscr.addnstr(i, 0, line, w - 1)
            except curses.error:
                pass
        if self.prompt_kind:
            self._draw_modal(h, w)

    def _restore_session_totals(self):
        stats = getattr(self, "session_stats", None)
        if stats is None:
            return
        path = os.path.join(_project_root(), ".uncle", "workspace", "session-totals.json")
        try:
            with open(path) as fh:
                saved = json.load(fh)
            if not isinstance(saved.get("records"), list):
                return
        except (OSError, ValueError, AttributeError):
            return
        if stats.get("session_id") != saved.get("id"):
            stats["active"].clear()
            stats["live"].clear()
            stats.pop("stopped_at", None)
        previous_records = stats["records"] if stats.get("session_id") == saved.get("id") else []
        for row in saved["records"]:
            if row in previous_records:
                continue
            stage = row.get("stage")
            if stats["active"].get(stage, float("inf")) <= row.get("ended_at", 0) + 1:
                stats["active"].pop(stage, None)
                stats["live"].pop(stage, None)
        stats.update(session_id=saved.get("id"), records=saved["records"],
                     seen=set(saved.get("seen", [])))

    def poll_session_stats(self):
        stats = getattr(self, "session_stats", None)
        if self.state not in ("running", "viewer") or stats is None:
            return False
        tick = int(time.time())
        if stats["tick"] == tick:
            return False
        self._restore_session_totals()
        stats["tick"] = tick
        if getattr(self, "proc_done", False):
            stats.setdefault("stopped_at", time.time())
        directory = os.path.join(_project_root(), ".uncle", "workspace", "metrics")
        try:
            names = os.listdir(directory)
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".json") or name in stats["seen"]:
                continue
            try:
                with open(os.path.join(directory, name)) as fh:
                    row = json.load(fh)
            except (OSError, ValueError):
                continue
            stats["seen"].add(name)
            if row.get("kind") not in ("agent", "reviewer"):
                continue
            stats["records"].append(row)
            stage = row.get("stage")
            # A late completion must not clear a newer attempt of the same stage.
            if stats["active"].get(stage, 0) <= row.get("ended_at", 0) + 1:
                stats["active"].pop(stage, None)
                stats["live"].pop(stage, None)
        return True

    @staticmethod
    def _token_total(row):
        for key in ("total_tokens", "reported_total_tokens"):
            if isinstance(row.get(key), (int, float)):
                return row[key]
        fields = ["input_tokens", "output_tokens"]
        inclusive = row.get("input_includes_cache") or "cline" in row.get("runner", "")
        if not inclusive:
            fields += ["cache_read_tokens", "cache_write_tokens"]
        if all(isinstance(row.get(k), (int, float)) for k in fields):
            return sum(row[k] for k in fields)
        return None

    def _live_cost(self, event):
        if isinstance(event.get("total_cost_usd"), (int, float)):
            return event["total_cost_usd"]
        usage = event.get("usage") or {}
        row = dict(model=event.get("model", ""), reported_cost_usd=None,
                   input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                   cache_read_tokens=usage.get("cache_read_input_tokens"),
                   cache_write_tokens=usage.get("cache_creation_input_tokens"),
                   input_includes_cache=event.get("input_includes_cache", False))
        try:
            if not hasattr(self, "_estimate_cost"):
                spec = importlib.util.spec_from_file_location("uncle_usage_cost", os.path.join(ROOT, "scripts", "lib", "usage-cost.py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._estimate_cost = module.enrich
            return self._estimate_cost(row).get("estimated_cost_usd")
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _session_panel_lines(self):
        stats = getattr(self, "session_stats", None)
        if stats is None:
            return []
        def duration(value):
            value = int(value)
            return "%d:%02d:%02d" % (value // 3600, value // 60 % 60, value % 60)
        def count(value):
            return "Unavailable" if value is None else format(int(value), ",")
        def dollars(value):
            return "Unavailable" if value is None else "$%.4f" % value
        def subtotal(values, formatter):
            known = [v for v in values if isinstance(v, (int, float))]
            text = formatter(sum(known) if known else None)
            return text + (" (partial)" if known and len(known) < len(values) else "")
        groups = {}
        for row in sorted(stats["records"], key=lambda r: r.get("started_at", 0)):
            stage = row.get("stage", "")
            group = groups.setdefault(stage, {"seconds": 0, "tokens": [], "costs": [], "attempts": 0, "started": float("inf")})
            group["started"] = min(group["started"], row.get("started_at", row.get("ended_at", 0) - row.get("elapsed_seconds", 0)))
            group["seconds"] += row.get("elapsed_seconds", 0)
            group["tokens"].append(self._token_total(row))
            cost = row.get("reported_cost_usd")
            group["costs"].append(cost if cost is not None else row.get("estimated_cost_usd"))
            group["attempts"] += 1
            group["last_result"] = row
        for stage, started in stats["active"].items():
            group = groups.setdefault(stage, {"seconds": 0, "tokens": [], "costs": [], "attempts": 0, "started": float("inf")})
            group["started"] = min(group["started"], started)
            event = stats["live"].get(stage, {})
            group["seconds"] += max(0, stats.get("stopped_at", time.time()) - started)
            group["tokens"].append(event.get("total_tokens"))
            group["costs"].append(self._live_cost(event) if event else None)
            group["attempts"] += 1
        lines = ["EACH STAGE", "Cost of usage so far", ""]
        tokens, costs = [], []
        self._panel_stage_styles = {}
        for stage, group in sorted(groups.items(), key=lambda item: item[1]["started"]):
            active = stage in stats["active"]
            title = ("> " if active else "") + stage
            if group["attempts"] > 1:
                title += " (%d attempts)" % group["attempts"]
            result = group.get("last_result", {})
            failed = result.get("process_exit") not in (None, 0) or result.get("reported_error") in (True, "true")
            if active and "stopped_at" not in stats:
                style = "title"
            elif failed:
                title += " [failed]"
                style = "bad"
            elif not active and result.get("process_exit") == 0:
                style = "good"
            else:
                style = "warning"
            self._panel_stage_styles[title] = style
            lines += [title, "Time   " + duration(group["seconds"]),
                      "Tokens " + subtotal(group["tokens"], count),
                      "Cost   " + subtotal(group["costs"], dollars), ""]
            tokens.extend(group["tokens"])
            costs.extend(group["costs"])
        if not groups:
            lines += ["Waiting for stage…", ""]
        lines += ["SESSION TOTALS",
                  "Time   " + duration(sum(group["seconds"] for group in groups.values())),
                  "Tokens " + subtotal(tokens, count),
                  "Cost   " + subtotal(costs, dollars), "Reported + projected"]
        return lines

    def _session_panel_attr(self, line):
        palette = getattr(self, "color", {})
        stage_style = getattr(self, "_panel_stage_styles", {}).get(line)
        if stage_style:
            return palette.get(stage_style, 0)
        if line in ("EACH STAGE", "SESSION TOTALS"):
            return palette.get("title", 0) | curses.A_BOLD
        if "Unavailable" in line or "(partial)" in line or line.startswith("Waiting"):
            return palette.get("warning", 0)
        if line.startswith("Cost   "):
            return palette.get("accent", 0)
        if line in ("Cost of usage so far", "Reported + projected"):
            return palette.get("muted", curses.A_DIM)
        return 0

    def _draw_session_stats(self, h, w, panel):
        left = w - panel
        for y in range(h - 1):
            try:
                self.stdscr.addnstr(y, left, "│", 1, getattr(self, "color", {}).get("muted", curses.A_DIM))
            except curses.error:
                pass
        lines = self._session_panel_lines()
        body = max(0, h - 2)
        offset = getattr(self, "panel_scroll", None)
        if offset is None:
            # Follow the latest stages until the user explicitly scrolls.
            offset = max(0, len(lines) - body)
        offset = max(0, min(offset, max(0, len(lines) - body)))
        self.panel_visible_offset = offset
        for y, line in enumerate(lines[offset:offset + body]):
            try:
                self.stdscr.addnstr(y, left + 2, line, panel - 3, self._session_panel_attr(line))
            except curses.error:
                pass
        try:
            self.stdscr.addnstr(h - 2, left + 2, r"[ ] stages; \ follow", panel - 3, getattr(self, "color", {}).get("muted", curses.A_DIM))
        except curses.error:
            pass

    def _title(self):
        if self.state == "picker":
            if self.picker_kind == "effort":
                return "Pick an effort (type to filter, Enter select, Esc back)"
            if self.picker_kind == "runner":
                return "Pick a runner (type to filter, Enter select, Esc back)"
            return "Pick a model (type to filter, Enter select, Esc back)"
        if self.state == "config_edit":
            if getattr(self, "notice", ""):
                return self.notice
            return "%s %s (Enter save, Esc back)" % (self.picker_target, self.picker_kind)
        if self.state == "stage":
            if getattr(self, "notice", ""):
                return self.notice
            return "%s — Enter: change, d: default, q back" % self.stage_target
        title = {
            "menu": "The man from uncle",
            "issue_mode": "Seed as",
            "issue": "Issue number or URL",
            "config": "Configure — Enter opens a stage, q back",
            "notice": "Enter to continue to Configure",
            "running": "q stops the run",
        }.get(self.state, "")
        if self.state == "config" and getattr(self, "first_run", False):
            title = "Configure this project (first run) — %s" % title
        return title

    def _draw_logo(self, h, w):
        """Draw the mark in the upper-left; return the content column, or 0."""
        if h >= len(LOGO) + 1 and w >= LOGO_W + 22:
            for i, line in enumerate(LOGO):
                try:
                    self.stdscr.addnstr(i, 0, line, w - 1, self.color["title"])
                except curses.error:
                    pass
            return LOGO_W + 2
        return 0

    def _wrap(self, text, width):
        """Split `text` into lines that fit within `width` columns."""
        width = max(1, width)
        lines, cur = [], ""
        for token in text.split():
            nxt = (cur + " " + token).strip() if cur else token
            if cur and len(nxt) > width:
                lines.append(cur)
                cur = token
            else:
                cur = nxt
        if cur:
            lines.append(cur)
        return lines

    def _draw_config_desc(self, top, bottom, h, w, cx):
        """Show the full description of the highlighted option on the right."""
        if self.state == "stage":
            key = "%s %s" % (self.stage_target, self._stage_field())
        else:
            key = self._config_row()
        desc = self._config_desc()
        if not desc:
            return
        items = self.items()
        item_w = max((len(i) for i in items), default=0)

        # A panel to the right of the options list. If the terminal is too
        # narrow for a side panel, fall back to a strip below the list.
        avail = w - 1 - (cx + item_w + 2)
        pane_w = avail if avail < 40 else min(78, max(40, avail - 4))
        dcol = max(cx + item_w + 2, w - pane_w - 1)
        pane_w = w - dcol - 1
        if pane_w >= 18:
            height = max(1, h - top - 1)
            lines = [(" %s " % key)] + self._wrap(desc, pane_w)
            for i in range(height):
                text = lines[i] if i < len(lines) else ""
                if not text:
                    break
                attr = self.color["title"] if i == 0 else self.color["accent"]
                try:
                    self.stdscr.addnstr(top + i, dcol, text, pane_w, attr)
                except curses.error:
                    pass
            return

        # Narrow terminal: render the description just below the options.
        width = max(1, w - cx - 1)
        lines = self._wrap(("%s — " % key) + desc, width)
        for i, ln in enumerate(lines[: max(0, h - bottom - 1)]):
            try:
                self.stdscr.addnstr(bottom + i, cx, ln, width, self.color["accent"])
            except curses.error:
                pass

    def _draw_picker(self, h, w, cx, top):
        rows = self._picker_filtered()
        height = max(1, h - top - 1)
        if self.pick_sel < self.pick_scroll:
            self.pick_scroll = self.pick_sel
        if self.pick_sel >= self.pick_scroll + height:
            self.pick_scroll = self.pick_sel - height + 1
        for i in range(height):
            idx = self.pick_scroll + i
            if idx >= len(rows):
                break
            kind, text = rows[idx]
            selected = idx == self.pick_sel and kind != "header"
            if kind == "header":
                marker = "── " if selected else "   "
                attr = self.color["title"]
                disp = marker + text
            else:
                prefix = "> " if selected else "  "
                attr = self.color["sel"] if selected else self.color["accent"]
                cur = kind in ("model", "option") and \
                    text.lower() == (self._picker_current() or "").lower()
                marker = "  <current>" if cur else ""
                label = MODEL_LABELS.get(text, "") if kind == "model" else ""
                disp = prefix + text + ("  %s" % label if label else "") + marker
            try:
                self.stdscr.addnstr(top + i, cx, disp, w - 1 - cx, attr)
            except curses.error:
                pass
        if not rows:
            try:
                if self.pick_filter:
                    self.stdscr.addnstr(top, cx, "no match for %r" % self.pick_filter, w - 1 - cx, self.color["accent"])
                else:
                    self.stdscr.addnstr(top, cx, "no matches", w - 1 - cx, self.color["accent"])
            except curses.error:
                pass

    def _draw_prompt(self, h, w):
        cx = self._draw_logo(h, w)
        row = 0

        if cx == 0:
            # The mark does not fit: full-width header, content below it.
            try:
                self.stdscr.addnstr(0, 0, self._title(), w - 1, self.color["title"])
            except curses.error:
                pass
            row = 2
        elif self.state != "menu":
            # Mark on the left; a small title sits to its right.
            try:
                self.stdscr.addnstr(0, cx, self._title(), w - 1 - cx, self.color["title"])
            except curses.error:
                pass
            row = 1

        if self.state in ("menu", "issue_mode", "config", "stage"):
            if self.state == "config":
                sel_idx = self.config_sel
            elif self.state == "stage":
                sel_idx = self.stage_sel
            else:
                sel_idx = self.sel
            top = row
            if self.state == "config":
                items = self.items()
                vis = max(1, h - top - 1)
                if self.config_scroll > sel_idx:
                    self.config_scroll = sel_idx
                if sel_idx >= self.config_scroll + vis:
                    self.config_scroll = sel_idx - vis + 1
                window = items[self.config_scroll:self.config_scroll + vis]
                for i, item in enumerate(window):
                    idx = self.config_scroll + i
                    selected = idx == sel_idx
                    prefix = "> " if selected else "  "
                    attr = self.color["sel"] if selected else 0
                    try:
                        self.stdscr.addnstr(row, cx, prefix + item, w - 1 - cx, attr)
                    except curses.error:
                        pass
                    row += 1
            else:
                for i, item in enumerate(self.items()):
                    selected = i == sel_idx
                    prefix = "> " if selected else "  "
                    attr = self.color["sel"] if selected else 0
                    try:
                        self.stdscr.addnstr(row, cx, prefix + item, w - 1 - cx, attr)
                    except curses.error:
                        pass
                    row += 1
            if self.state in ("config", "stage"):
                self._draw_config_desc(top, row, h, w, cx)
        elif self.state == "picker":
            self._draw_picker(h, w, cx, row)
        else:
            try:
                self.stdscr.addnstr(row, cx, self.input_buf, w - 1 - cx)
            except curses.error:
                pass
            try:
                self.stdscr.addstr(row, cx + len(self.input_buf), "█", self.color["cursor"])
            except curses.error:
                pass

    def _draw_notice(self, h, w):
        """A centered box with one OK, shown before the first Configure."""
        body = list(self.notice_lines) + ["", "[ OK ]"]
        box_w = min(w - 4, max(len(l) for l in body) + 6)
        box_w = max(box_w, 34)
        box_h = len(body) + 4
        top = max(0, (h - box_h) // 2)
        left = max(0, (w - box_w) // 2)
        if self.prompt_text.startswith("Document budget exceeded:"):
            title = " document budget "
        if self.prompt_text.startswith("Repair limit reached:"):
            title = " repair limit "
        border = self.color["title"]
        try:
            self.stdscr.addnstr(top, left,
                                "\u250c" + " markdown reader ".center(box_w - 2, "\u2500") + "\u2510",
                                box_w, border)
            for i in range(box_h - 2):
                self.stdscr.addnstr(top + 1 + i, left,
                                    "\u2502" + " " * (box_w - 2) + "\u2502", box_w, border)
            self.stdscr.addnstr(top + box_h - 1, left,
                                "\u2514" + "\u2500" * (box_w - 2) + "\u2518", box_w, border)
        except curses.error:
            pass
        for i, line in enumerate(body):
            attr = self.color["sel"] if line == "[ OK ]" else self.color["accent"]
            col = left + (box_w - len(line)) // 2 if line == "[ OK ]" else left + 3
            try:
                self.stdscr.addnstr(top + 2 + i, col, line, box_w - 6, attr)
            except curses.error:
                pass

    def _draw_modal(self, h, w):
        """The driver's question, in the middle of the screen.

        A gate is the one moment the workflow is waiting on a person, so it
        gets the middle of the screen rather than one more line of scrollback.
        """
        lines = self._wrap(self.prompt_text, max(20, min(72, w - 12)))
        if self.prompt_kind == "confirm":
            footer = "[y] approve      [n] decline"
            if self.gate_file:
                footer = "[y] approve      [n] decline      [v] view file"
        elif self.prompt_kind == "enter":
            footer = "[Enter] continue      [Esc] decline"
        else:
            footer = "type an answer, [Enter] send, [Esc] cancel"
        body = list(lines)
        if self.prompt_kind == "input":
            body += ["", "> " + self.prompt_buf + "\u2588"]
        body += ["", footer]

        box_w = min(w - 4, max(len(l) for l in body + [footer]) + 6)
        box_w = max(box_w, 30)
        box_h = len(body) + 4
        top = max(0, (h - box_h) // 2)
        left = max(0, (w - box_w) // 2)
        title = {"confirm": " approve ", "enter": " review ", "input": " input "}.get(
            self.prompt_kind, " uncle ")

        border = self.color["title"]
        try:
            self.stdscr.addnstr(top, left, "\u250c" + title.center(box_w - 2, "\u2500") + "\u2510", box_w, border)
            for i in range(box_h - 2):
                self.stdscr.addnstr(top + 1 + i, left, "\u2502" + " " * (box_w - 2) + "\u2502", box_w, border)
            self.stdscr.addnstr(top + box_h - 1, left, "\u2514" + "\u2500" * (box_w - 2) + "\u2518", box_w, border)
        except curses.error:
            pass
        for i, line in enumerate(body):
            attr = self.color["accent"]
            if line is body[-1]:
                attr = self.color["sel"]
            elif self.prompt_kind == "input" and line.startswith("> "):
                attr = self.color["cursor"]
            try:
                self.stdscr.addnstr(top + 2 + i, left + 3, line, box_w - 6, attr)
            except curses.error:
                pass

    def _draw_status(self, h, w):
        if self.state == "viewer":
            return
        if self.state == "running":
            model = self.status_model or "—"
            if self.prompt_kind:
                mode = "Waiting for you"
                bar_attr = self.color["sel"]
            elif self.status_mode == "act":
                mode = "Act"
                bar_attr = self.color["good"]
            elif self.status_mode in ("plan", "review"):
                mode = "Review" if self.status_mode == "review" else "Plan"
                bar_attr = self.color["accent"]
            else:
                mode = "—"
                bar_attr = 0
            stage = "stage: %s" % (self.status_stage or "—")
            if self.status_stage_index and self.status_stage_total:
                stage = "stage: %s (%d/%d)" % (
                    self.status_stage, self.status_stage_index, self.status_stage_total)
        else:
            model = "—"
            mode = "—"
            bar_attr = 0
            stage = ""
        runner = self.status_runner or "—"
        effort = "—"
        if self.state == "running" and self.status_stage:
            effort = (getattr(self, "status_effort", "") or
                      getattr(self, "stage_efforts", {}).get(self.status_stage) or DEFAULT_EFFORT)
        parts = " runner: %s   model: %s   effort: %s   mode: %s " % (runner, model, effort, mode)
        if stage:
            parts += "  %s" % stage
        text = parts
        try:
            self.stdscr.attrset(bar_attr | curses.A_REVERSE)
            self.stdscr.addnstr(h - 1, 0, text.ljust(w)[: w - 1], w - 1)
            self.stdscr.attrset(0)
        except curses.error:
            self.stdscr.attrset(0)

    # ---- input ----
    def handle_key(self, k):
        if self.state in ("running", "viewer") and getattr(self, "prompt_kind", "") != "input":
            if k in (ord("["), ord("]"), ord("\\")):
                if k == ord("\\"):
                    self.panel_scroll = None
                else:
                    self.panel_scroll = max(0, getattr(self, "panel_visible_offset", 0) + (-5 if k == ord("[") else 5))
                return
        if k == 3:  # Ctrl-C
            self._quit()
            return
        if k == 27:  # Esc
            if self.state == "notice":
                self.state = "config"
                self.config_sel = 0
                return
            if self.state == "running" and self.prompt_kind:
                if self.prompt_kind == "confirm":
                    self.answer_prompt("n")     # anything but y declines
                elif self.prompt_kind == "input":
                    self.prompt_kind = ""       # leave the question standing
                    self.prompt_seen = 0
                return
            self._go_back()
            return

        if self.state == "notice":
            # Any key is OK; that is what an OK box is.
            self.state = "config"
            self.config_sel = 0
            return

        if self.state == "viewer":
            body = 20
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.view_scroll -= 1
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.view_scroll += 1
            elif k == curses.KEY_NPAGE or k == ord(" "):
                self.view_scroll += body
            elif k == curses.KEY_PPAGE:
                self.view_scroll -= body
            elif k in (ord("g"),):
                self.view_scroll = 0
            elif k in (ord("G"),):
                self.view_scroll = max(0, len(self.view_lines))
            elif k in (ord("q"), ord("Q"), 27, 10, 13):
                self.state = "running"
            self.view_scroll = max(0, self.view_scroll)
            return

        if self.state == "running":
            if self.prompt_kind == "confirm":
                if k in (ord("y"), ord("Y")):
                    self.answer_prompt("y")
                elif k in (ord("n"), ord("N")):
                    self.answer_prompt("n")
                elif k in (ord("v"), ord("V")) and self.gate_file:
                    self._open_viewer(self.gate_file)
                return
            if self.prompt_kind == "enter":
                if k in (10, 13):
                    self.answer_prompt("")
                elif k == 27:
                    self.stop_workflow()
                    self.state = "menu"
                    self.sel = 0
                return
            if self.prompt_kind == "input":
                if k in (10, 13):
                    self.answer_prompt(self.prompt_buf)
                elif k in (curses.KEY_BACKSPACE, 127, 8):
                    self.prompt_buf = self.prompt_buf[:-1]
                elif 32 <= k <= 126:
                    self.prompt_buf += chr(k)
                return
            if k in (ord("q"), ord("Q")):
                self.stop_workflow()
                self.state = "menu"
                self.sel = 0
            return

        if self.state == "config":
            nrows = len(CONFIG_STAGES)
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.config_sel = (self.config_sel - 1) % nrows
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.config_sel = (self.config_sel + 1) % nrows
            elif k in (10, 13):
                self._open_stage(self._config_row())
            elif k in (ord("q"), ord("Q")):
                self.state = "menu"
                self.sel = 0
            return

        if self.state == "stage":
            fields = self.stage_fields(self.stage_target)
            nrows = len(fields)
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.stage_sel = (self.stage_sel - 1) % nrows
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.stage_sel = (self.stage_sel + 1) % nrows
            elif k in (10, 13):
                self._open_picker(self._stage_field(), self.stage_target)
            elif k in (ord("d"), ord("D")):
                self._set_field(self.stage_target, self._stage_field(), "")
                self.stage_sel = min(self.stage_sel,
                                     len(self.stage_fields(self.stage_target)) - 1)
            elif k in (ord("q"), ord("Q")):
                self.state = "config"
            return

        if self.state in ("menu", "issue_mode"):
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.sel = (self.sel - 1) % len(self.items())
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.sel = (self.sel + 1) % len(self.items())
            elif k in (10, 13):
                self._confirm()
            elif self.state == "menu" and k in (ord("1"), ord("2"), ord("3"), ord("4")):
                self.sel = k - ord("1")
                self._confirm()
            elif self.state == "menu" and k in (ord("q"), ord("Q")):
                self._quit()
            return

        if self.state == "picker":
            rows = self._picker_filtered()
            n = len(rows)
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self._picker_move(-1)
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self._picker_move(1)
            elif k in (10, 13):
                self._picker_confirm()
            elif k == curses.KEY_BACKSPACE:
                self.pick_filter = self.pick_filter[:-1]
                self._reset_pick_sel()
            elif 32 <= k <= 126:
                self.pick_filter += chr(k)
                self._reset_pick_sel()
            return

        if self.state in ("issue", "config_edit"):
            if k in (10, 13):
                self._confirm_text()
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                self.input_buf = self.input_buf[:-1]
            elif 32 <= k <= 126:
                self.input_buf += chr(k)
            return

    def _go_back(self):
        if self.state == "issue":
            self.state = "menu"
        elif self.state == "issue_mode":
            self.state = "issue"
        elif self.state == "config":
            self.state = "menu"
        elif self.state == "stage":
            self.state = "config"
        elif self.state == "config_edit":
            self.state = "stage"
        elif self.state == "picker":
            self.state = "stage"
        self.sel = 0

    def _confirm(self):
        if self.state == "menu":
            if self.sel == len(WORKFLOWS) + 1:
                self._quit()
                return
            if self.sel == len(WORKFLOWS):
                self.state = "config"
                self.config_sel = 0
                self.sel = 0
                return
            self.workflow_idx = self.sel
            if self.workflow_idx == 1:
                self.state = "issue"
                self.sel = 0
                self.input_buf = ""
            else:
                self._run()
        elif self.state == "issue_mode":
            self.issue_mode = ISSUE_MODES[self.sel][1]
            self._run()

    def _confirm_text(self):
        if self.state == "issue":
            self.issue = self.input_buf.strip()
            if not self.issue:
                return
            self.input_buf = ""
            self.state = "issue_mode"
            self.sel = 0
        elif self.state == "config_edit":
            val = self.input_buf.strip()
            if self.picker_kind == "model" and not valid_model_id(val):
                # Storing it would only surface as a failed stage later.
                self.notice = "not a cline model id: %s (expected modelType/model)" % val
                return
            self.notice = ""
            self._set_field(self.picker_target, self.picker_kind, val)
            self.input_buf = ""
            self.stage_sel = min(self.stage_sel,
                                 len(self.stage_fields(self.picker_target)) - 1)
            self.state = "stage"

    def _run(self):
        # The run reads the file, so make sure we are not about to launch on
        # top of an edit we have not seen.
        self.maybe_reload()
        self.state = "running"
        self.start_workflow()

    def _quit(self):
        self.state = "quit"

    # ---- main loop ----
    def run(self):
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.stdscr.timeout(80)
        self._setup_colors()
        dirty = True
        size = None
        while self.state != "quit":
            dirty = self.poll_status() or dirty
            dirty = self.poll_session_stats() or dirty
            if self.state == "running":
                dirty = self.drain_output() or dirty
            else:
                # ~1s: often enough that an edit in another window shows up
                # while you are looking at the screen, cheap enough to ignore.
                self._reload_tick += 1
                if self._reload_tick >= 12:
                    self._reload_tick = 0
                    dirty = self.maybe_reload() or dirty
            k = self.stdscr.getch()
            if k != -1:
                self.handle_key(k)
                dirty = True
            current_size = self.stdscr.getmaxyx()
            if self.state != "quit" and (dirty or current_size != size):
                self.draw()
                dirty = False
                size = current_size
        self.stop_workflow()


def main(stdscr):
    UncleTUI(stdscr).run()


if __name__ == "__main__":
    curses.wrapper(main)

