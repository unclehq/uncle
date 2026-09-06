#!/usr/bin/env python3
"""Full-screen terminal UI for uncle.

A curses interface: pick a workflow, then run the chosen driver while streaming
its output. The cline model, reasoning effort, and per-stage overrides are set
in the Configure screen (persisted to `.uncle.config`). A fixed status bar shows
the current model, cumulative tokens used, and Act/Plan mode for the running
stage.
"""
import curses
import json
import os
import queue
import subprocess
import tempfile
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
CLINE_CONFIG = os.environ.get("CLINE_CONFIG", os.path.expanduser("~/.cline/data/settings/providers.json"))

WORKFLOWS = [
    ("New application", [os.path.join(ROOT, "scripts", "stagegate.sh")]),
    ("From GitHub issue", [os.path.join(ROOT, "scripts", "from-issue.sh")]),
    ("Change request", [os.path.join(ROOT, "scripts", "change-workflow.sh")]),
]
EFFORTS = ["high", "medium", "low"]
ISSUE_MODES = [("auto", ""), ("change request", "--change"), ("new application", "--new")]
CONFIG_PATH = os.environ.get("UNCLE_CONFIG", os.path.join(ROOT, ".uncle.config"))
CONFIG_STAGES = [
    "requirements", "project-plan", "updated-plan", "implementation",
    "execute-checklist", "baseline", "change-spec", "change-plan",
    "updated-change-plan", "reviewer",
]
RUNNERS = ["cline", "claude", "kimi", "codex"]

# Models offered in the Configure → model picker, grouped by plan.
MODEL_CATALOG = [
    ("Subscribed (ClinePass)", [
        "cline-pass/qwen3.8-max",
        "GLM-5.2",
        "DeepSeek V4 Pro",
        "GLM-5.3-Flash",
        "Kimi K3",
        "GLM-5.3",
        "Kimi K2.7 Code",
        "DeepSeek V4 Flash",
        "Kimi K2.6",
        "Qwen3.7 Plus",
        "Qwen3.7 Max",
        "MiniMax-M3",
        "MiMo-V2.5-Pro",
        "MiMo-V2.5",
    ]),
    ("Free", [
        "DeepSeek V4 Flash",
        "GLM-5.3-Flash",
        "LongCat 2.0",
        "Laguna S 2.1",
    ]),
]

# Full description for each Configure item. Only the description of the row
# currently under the cursor is shown, in a panel to the right of the options.
CONFIG_DESC = {
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


def runner_commands(runner):
    if runner == "claude":
        return ("claude", os.path.join(ROOT, "scripts", "reviewer-claude.sh"))
    if runner == "kimi":
        return (os.path.join(ROOT, "scripts", "agent-kimi.sh"), "codex")
    if runner == "codex":
        return ("claude", "codex")
    return (os.path.join(ROOT, "scripts", "agent-cline.sh"),
            os.path.join(ROOT, "scripts", "reviewer-cline.sh"))


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
        self.model = ""
        self.effort = "medium"
        self.state = "menu"
        self.sel = 0
        self.workflow_idx = None
        self.issue = ""
        self.issue_mode = ""
        self.input_buf = ""
        self.output = []
        self.proc = None
        self.out_q = queue.Queue()
        self.status_path = None
        self.status_pos = 0
        self.status_model = ""
        self.status_mode = ""
        self.completed_tokens = 0
        self.current_tokens = 0
        self.config = {}
        self.stage_efforts = {}
        self.runner = "cline"
        self.config_sel = 0
        self.config_scroll = 0
        self.pick_sel = 0
        self.pick_scroll = 0
        self.pick_filter = ""
        self.picker_kind = "model"
        self.picker_target = None
        self.load_config()

    # ---- colors (cline's CLI palette) ----
    def _setup_colors(self):
        self.color = {"title": 0, "accent": 0, "good": 0, "sel": 0, "cursor": 0}
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
        return []

    # ---- config rows ----
    # Each row is a (kind, target) pair. kind is one of runner/model/effort;
    # target is None (runner) or GLOBAL (global model/effort) or a stage name.
    def _config_row_defs(self):
        rows = [("runner", None), ("model", GLOBAL), ("effort", GLOBAL)]
        for s in CONFIG_STAGES:
            rows.append(("model", s))
            rows.append(("effort", s))
        return rows

    def _config_row(self):
        defs = self._config_row_defs()
        if 0 <= self.config_sel < len(defs):
            return defs[self.config_sel]
        return ("", None)

    def _row_value(self, kind, target):
        if kind == "runner":
            return self.runner
        if kind == "model":
            return self.model if target is GLOBAL else self.config.get(target, "")
        if kind == "effort":
            return self.effort if target is GLOBAL else self.stage_efforts.get(target, "")
        return ""

    def _row_label(self, kind, target):
        if kind == "runner":
            return "runner"
        if kind == "model":
            return "model" if target is GLOBAL else target
        if kind == "effort":
            return "effort" if target is GLOBAL else "%s effort" % target
        return ""

    def _row_display(self, kind, target):
        val = self._row_value(kind, target)
        if kind == "model":
            if not val:
                return "(cline default)" if target is GLOBAL else "(default)"
            return val
        if kind == "effort":
            if not val:
                return self.effort if target is GLOBAL else "(default)"
            return val
        return val

    def _set_row_value(self, kind, target, value):
        value = (value or "").strip()
        if kind == "runner":
            self.runner = value or "cline"
        elif kind == "model":
            if target is GLOBAL:
                self.model = value
            elif value:
                self.config[target] = value
            else:
                self.config.pop(target, None)
        elif kind == "effort":
            if target is GLOBAL:
                self.effort = value or self.effort or "medium"
            elif value:
                self.stage_efforts[target] = value
            else:
                self.stage_efforts.pop(target, None)
        self.save_config()

    def _clear_row(self):
        kind, target = self._config_row()
        self._set_row_value(kind, target, "")

    def _config_items(self):
        defs = self._config_row_defs()
        rows = []
        for kind, target in defs:
            rows.append("%s: %s" % (self._row_label(kind, target).ljust(20),
                                    self._row_display(kind, target)))
        return rows

    def _config_desc(self):
        """Full description for the currently highlighted Configure row."""
        kind, target = self._config_row()
        if kind == "runner":
            return CONFIG_DESC["runner"]
        if kind == "model":
            if target is GLOBAL:
                return CONFIG_DESC["model"]
            return CONFIG_DESC.get(target, "")
        if kind == "effort":
            base = CONFIG_DESC["effort"]
            if target is not GLOBAL:
                base += (" Set a value here to give the %s stage its own reasoning "
                         "effort instead of inheriting the global effort above. "
                         "Leave it at (default) to use %s.") % (target, self.effort)
            return base
        return ""

    # ---- generic picker (model / effort / runner) ----
    def _picker_rows(self):
        """Rows for the active picker: (kind, text), kind in header/option/model/custom."""
        if self.picker_kind == "effort":
            return [("option", e) for e in EFFORTS] + [("custom", "Custom… (type an effort)")]
        if self.picker_kind == "runner":
            return [("option", r) for r in RUNNERS] + [("custom", "Custom… (type a runner)")]
        rows = [("header", "Subscribed (ClinePass)")]
        for m in MODEL_CATALOG[0][1]:
            rows.append(("model", m))
        rows.append(("header", "Free"))
        for m in MODEL_CATALOG[1][1]:
            rows.append(("model", m))
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
            if kind == "custom" or flt in text.lower():
                out.append((kind, text))
        return out

    def _picker_current(self):
        """The value the active picker is choosing on behalf of."""
        if self.picker_kind == "runner":
            return self.runner
        return self._row_value(self.picker_kind, self.picker_target)

    def _open_picker(self, kind, target):
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
            self.input_buf = self.pick_filter.strip() or self._picker_current()
            return
        self._set_row_value(self.picker_kind, self.picker_target, text)
        self.state = "config"

    def cmd_for(self):
        if self.workflow_idx == 1:
            cmd = list(WORKFLOWS[1][1]) + [self.issue]
            if self.issue_mode:
                cmd.append(self.issue_mode)
            return cmd
        return list(WORKFLOWS[self.workflow_idx][1])

    # ---- config ----
    def load_config(self):
        self.config = {}
        self.stage_efforts = {}
        self.runner = "cline"
        self.model = ""
        self.effort = "medium"
        try:
            with open(CONFIG_PATH) as fh:
                for line in fh:
                    line = line.split("#", 1)[0].strip()
                    if not line:
                        continue
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        key, val = parts[0].strip(), parts[1].strip()
                        if key == "runner":
                            self.runner = val
                        elif key == "model":
                            self.model = val
                        elif key == "effort":
                            self.effort = val
                        elif key.endswith(".effort"):
                            self.stage_efforts[key[:-len(".effort")]] = val
                        else:
                            self.config[key] = val
        except Exception:
            pass

    def save_config(self):
        header = ("# Uncle per-stage model/effort config.\n"
                  "# Format: STAGE VALUE  (STAGE = a stage log name, `reviewer`, `runner`,\n"
                  "#   `model`, `effort`, or `STAGE.effort`; VALUE = a cline model id, a\n"
                  "#   runner name, or a reasoning effort).\n")
        try:
            with open(CONFIG_PATH, "w") as fh:
                fh.write(header)
                fh.write("runner %s\n" % self.runner)
                if self.model:
                    fh.write("model %s\n" % self.model)
                fh.write("effort %s\n" % self.effort)
                for stage in CONFIG_STAGES:
                    if self.config.get(stage):
                        fh.write("%s %s\n" % (stage, self.config[stage]))
                    if self.stage_efforts.get(stage):
                        fh.write("%s.effort %s\n" % (stage, self.stage_efforts[stage]))
        except Exception:
            pass

    # ---- status channel ----
    def poll_status(self):
        if not self.status_path:
            return
        try:
            with open(self.status_path) as fh:
                fh.seek(self.status_pos)
                for line in fh:
                    self._apply_status(line)
                self.status_pos = fh.tell()
        except Exception:
            pass

    def _apply_status(self, line):
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except Exception:
            return
        if ev.get("event") == "start":
            self.completed_tokens += self.current_tokens
            self.current_tokens = 0
            self.status_model = ev.get("model", "")
            self.status_mode = ev.get("mode", "")
        elif ev.get("event") == "usage":
            self.current_tokens = int(ev.get("total_tokens", 0) or 0)
            self.status_model = ev.get("model", self.status_model)
            self.status_mode = ev.get("mode", self.status_mode)

    # ---- running ----
    def start_workflow(self):
        fd, self.status_path = tempfile.mkstemp(prefix="uncle-status-", suffix=".jsonl")
        os.close(fd)
        env = dict(os.environ)
        agent_cmd, reviewer_cmd = runner_commands(self.runner)
        env["WORKFLOW_AGENT_CMD"] = agent_cmd
        env["WORKFLOW_REVIEWER_CMD"] = reviewer_cmd
        for stage, model in self.config.items():
            if stage == "reviewer":
                env["UNCLE_CLINE_REVIEWER_MODEL"] = model
            else:
                env[stage_env_var(stage)] = model
        for stage, effort in self.stage_efforts.items():
            env[stage_effort_var(stage)] = effort
        env["UNCLE_CLINE_MODEL"] = self.model
        env["UNCLE_CLINE_EFFORT"] = self.effort
        env["UNCLE_STATUS_FILE"] = self.status_path
        self.output = []
        self.proc = subprocess.Popen(self.cmd_for(), cwd=ROOT, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                self.out_q.put(line)
        finally:
            self.out_q.put(None)

    def drain_output(self):
        try:
            while True:
                line = self.out_q.get_nowait()
                if line is None:
                    return
                self.output.append(line.rstrip("\n"))
                if len(self.output) > 4000:
                    del self.output[:500]
        except queue.Empty:
            pass

    def stop_workflow(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.completed_tokens = 0
        self.current_tokens = 0
        self.status_model = ""
        self.status_mode = ""

    # ---- drawing ----
    def draw(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()
        if self.state == "running":
            self._draw_running(h, w)
        else:
            self._draw_prompt(h, w)
        self._draw_status(h, w)
        self.stdscr.refresh()

    def _draw_running(self, h, w):
        for i, line in enumerate(self.output[-(h - 1):]):
            try:
                self.stdscr.addnstr(i, 0, line, w - 1)
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
            kind, target = self._config_row()
            return "Value for %s (Enter save, Esc back)" % (self._row_label(kind, target) or "?")
        return {
            "menu": "The man from uncle",
            "issue_mode": "Seed as",
            "issue": "Issue number or URL",
            "config": "Configure — Enter: pick model/effort/runner, d reset, q back",
        }.get(self.state, "")

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
        kind, target = self._config_row()
        key = self._row_label(kind, target) or ""
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
                disp = prefix + text + marker
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

        if self.state in ("menu", "issue_mode", "config"):
            sel_idx = self.config_sel if self.state == "config" else self.sel
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
            if self.state == "config":
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

    def _draw_status(self, h, w):
        if self.state == "running":
            model = self.status_model or self.default_model or "default"
            tokens = self.completed_tokens + self.current_tokens
            if self.status_mode == "act":
                mode = "Act"
                bar_attr = self.color["good"]
            elif self.status_mode == "plan":
                mode = "Plan"
                bar_attr = self.color["accent"]
            else:
                mode = "—"
                bar_attr = 0
        else:
            model = self.model or self.default_model or "default"
            tokens = 0
            mode = "—"
            bar_attr = 0
        text = " model: %s   tokens: %d   mode: %s " % (model, tokens, mode)
        try:
            self.stdscr.attrset(bar_attr | curses.A_REVERSE)
            self.stdscr.addnstr(h - 1, 0, text.ljust(w)[: w - 1], w - 1)
            self.stdscr.attrset(0)
        except curses.error:
            self.stdscr.attrset(0)

    # ---- input ----
    def handle_key(self, k):
        if k == 3:  # Ctrl-C
            self._quit()
            return
        if k == 27:  # Esc
            self._go_back()
            return

        if self.state == "running":
            if k in (ord("q"), ord("Q")):
                self.stop_workflow()
                self.state = "menu"
                self.sel = 0
            return

        if self.state == "config":
            nrows = len(self._config_row_defs())
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.config_sel = (self.config_sel - 1) % nrows
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.config_sel = (self.config_sel + 1) % nrows
            elif k in (10, 13):
                kind, target = self._config_row()
                if kind == "runner":
                    self._open_picker("runner", None)
                elif kind == "model":
                    self._open_picker("model", target)
                elif kind == "effort":
                    self._open_picker("effort", target)
            elif k in (ord("d"), ord("D")):
                self._clear_row()
            elif k in (ord("q"), ord("Q")):
                self.state = "menu"
                self.sel = 0
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
        elif self.state == "config_edit":
            self.state = "config"
        elif self.state == "picker":
            self.state = "config"
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
            self._set_row_value(self.picker_kind, self.picker_target, val)
            self.input_buf = ""
            self.state = "config"

    def _run(self):
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
        while self.state != "quit":
            self.poll_status()
            if self.state == "running":
                self.drain_output()
            k = self.stdscr.getch()
            if k != -1:
                self.handle_key(k)
            self.draw()
        self.stop_workflow()


def main(stdscr):
    UncleTUI(stdscr).run()


if __name__ == "__main__":
    curses.wrapper(main)



