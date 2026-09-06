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


def stage_env_var(stage):
    return "WORKFLOW_MODEL_" + "".join(c if c.isalnum() else "_" for c in stage.upper())


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
        self.runner = "cline"
        self.config_sel = 0
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

    def _config_stage_name(self):
        if self.config_sel == 0:
            return "runner"
        if self.config_sel == 1:
            return "model"
        if self.config_sel == 2:
            return "effort"
        idx = self.config_sel - 3
        if 0 <= idx < len(CONFIG_STAGES):
            return CONFIG_STAGES[idx]
        return ""

    def _config_items(self):
        def fmt(key, value):
            return "%s: %s" % (key.ljust(20), value)

        rows = [
            fmt("runner", self.runner),
            fmt("model", self.model or "(cline default)"),
            fmt("effort", self.effort),
        ]
        rows += [fmt(s, self.config.get(s) or "(default)") for s in CONFIG_STAGES]
        return rows

    def _config_desc(self):
        """Full description for the currently highlighted Configure row."""
        return CONFIG_DESC.get(self._config_stage_name(), "")

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
        self.runner = "cline"
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
                        else:
                            self.config[key] = val
        except Exception:
            pass

    def save_config(self):
        header = ("# Uncle per-stage model config.\n"
                  "# Format: STAGE VALUE  (STAGE = a stage log name, `reviewer`, `runner`,\n"
                  "#   `model`, or `effort`; VALUE = cline model id, a runner name, or an effort).\n")
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
        return {
            "menu": "The man from uncle",
            "issue_mode": "Seed as",
            "issue": "Issue number or URL",
            "config": "Configure — Enter: cycle runner/effort or edit, d reset, q back",
            "config_edit": "Value for %s (Enter save, Esc back)" % self._config_stage_name(),
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
        key = self._config_stage_name()
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
            nrows = len(CONFIG_STAGES) + 3
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.config_sel = (self.config_sel - 1) % nrows
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.config_sel = (self.config_sel + 1) % nrows
            elif k in (10, 13):
                sel = self.config_sel
                if sel == 0:
                    self.runner = RUNNERS[(RUNNERS.index(self.runner) + 1) % len(RUNNERS)]
                    self.save_config()
                elif sel == 1:
                    self.state = "config_edit"
                    self.input_buf = self.model
                elif sel == 2:
                    if self.effort in EFFORTS:
                        self.effort = EFFORTS[(EFFORTS.index(self.effort) + 1) % len(EFFORTS)]
                    else:
                        self.effort = "medium"
                    self.save_config()
                else:
                    self.state = "config_edit"
                    self.input_buf = self.config.get(self._config_stage_name(), "")
            elif k in (ord("d"), ord("D")):
                sel = self.config_sel
                if sel == 0:
                    self.runner = "cline"
                    self.save_config()
                elif sel == 1:
                    self.model = ""
                    self.save_config()
                elif sel == 2:
                    self.effort = "medium"
                    self.save_config()
                else:
                    self.config.pop(self._config_stage_name(), None)
                    self.save_config()
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
            stage = self._config_stage_name()
            val = self.input_buf.strip()
            if stage == "model":
                self.model = val
            elif stage == "effort":
                self.effort = val or "medium"
            else:
                if val:
                    self.config[stage] = val
                else:
                    self.config.pop(stage, None)
            self.save_config()
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



