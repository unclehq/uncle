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
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import importlib.util
import webbrowser
import textwrap
import uuid

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
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from completion_preview import CompletionPreview, STAR_URL
from chat import Conversation, sanitize
from home_chat import HomeRequest, IssueSeedRequest
from home_actions import prompt as home_action_prompt, parse_reply as parse_home_action
from triage_chat import (TriageRequest, parse_reply as parse_triage_reply, compose_prompt as triage_prompt,
                         runner_flags as triage_runner_flags, scrub_env as triage_scrub_env,
                         DIAGNOSIS_TOOLS, EXECUTE_TOOLS)
from github_issues import IssuePicker, references as issue_references, issue_context
from self_hosted import settings as home_settings
from self_hosted import key_file, read_keys, save_keys, connection_settings, refresh_models, local_model
import supervisor as supervision_lib
from supervisor_runner import SupervisorRequest, build_command as supervisor_command

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


def _direct_origin_issue():
    try:
        with open(os.path.join(_project_root(), ".uncle", "workflow", "origin"),
                  encoding="utf-8") as origin:
            fields = origin.readline().rstrip("\n").split("\t")
    except (OSError, UnicodeError):
        return ""
    if (len(fields) >= 2 and fields[0] and fields[1]
            and all("0" <= char <= "9" for char in fields[1])):
        return fields[1]
    return ""


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
    ("derive-brief", AGENT),
    ("requirements", AGENT),
    ("baseline", AGENT),
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
    # The triage master: opened by the TUI after a stage failure or on
    # request at a stop. An agent-side runner, because an executed proposal
    # writes into a sandbox; unset means the runner's own defaults.
    ("triage", AGENT),
]
# Exit statuses that are not failures: a declined gate, a cancel, a kill.
TRIAGE_CLEAN_EXITS = (0, 130, 143, 137, -9)
STAGE_SIDE = dict(STAGES)
CONFIG_STAGES = [name for name, _ in STAGES]
BUILD_CONFIG_STAGES = [name for name in CONFIG_STAGES if name != "triage"]

# Runners are offered per side, because the two sides are not interchangeable:
# an agent stage writes code and needs an agent CLI running with write access,
# a reviewer stage must be read-only. Each side has its own shim per runner —
# scripts/agent-*.sh and scripts/reviewer-*.sh — and the shim is what enforces
# that difference. codex, for instance, runs `--sandbox workspace-write` as an
# agent and `--sandbox read-only` as a reviewer.
AGENT_RUNNERS = ["cline", "claude", "kimi", "codex", "self-hosted"]
REVIEWER_RUNNERS = ["cline", "codex", "claude", "kimi", "self-hosted"]

# Applied to any stage the operator has not configured.
DEFAULT_RUNNER = ""
DEFAULT_EFFORT = "low"

def default_stage_effort(stage):
    if stage.startswith("implementation-step-"):
        stage = "implementation"
    if stage == "plan-executability":
        stage = "adversarial-review"
    return "medium" if stage in ("adversarial-review", "project-plan", "implementation") else DEFAULT_EFFORT

DEFAULT_CLINE_MODEL = "cline-pass/deepseek-v4-pro"

STAGE_FIELDS = ("runner", "effort", "model", "network", "billing", "base_url", "api_key")
# Only codex sandboxes a stage, so only a codex stage has a network to open.
NETWORK_CHOICES = ["false", "true"]

# Models offered in the Configure → model picker, grouped by plan.
#
# Each entry is (label, id). The id is what gets written to .uncle/config and
# passed to `cline -m`, and cline requires it in `modelType/model` form; the
# label is display only. A bare display name is rejected by cline with
# "invalid model format", so the picker must never store one.
MODEL_CATALOG_CLINEPASS = [
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
]

# Usage-based billing is a different catalogue, not a different flag: within
# cline's default provider the modelType prefix is what selects how the run is
# paid for, so `cline-pass/kimi-k3` and a vendor-prefixed `kimi-k3` are two
# different purchases of the same model. Keeping the paid lists apart is what
# stops a stage from being configured to spend the wrong one.
#
# The two catalogues share a slug and differ in the prefix, the way
# `cline-pass/glm-5.3-flash` and `z-ai/glm-5.3-flash` do. Every id below was
# checked against cline's installed catalogue rather than inferred -- see
# cline-model-ids-test.sh, which fails if one of these stops existing.
#
# Being in the catalogue is necessary and not sufficient. `meituan/longcat-2.0`
# is an exact catalogue key with a full entry, and the gateway answers it with
# 404 model_not_found; the id that serves is `meituan/longcat-2.0-free`. The
# catalogue is a list of models cline can describe, not of models this account
# can call, so an id belongs here only once something has actually run on it.
#
# This list is shorter than cline's own Recommended group on purpose. cline
# fetches that group from its server at runtime
# (@cline/llms fetchClineRecommendedModelsPayload), so it carries models the
# installed build has never heard of -- "GPT-6 Astra" appears in the picker
# and nowhere in the package or the hub binary. Those cannot be verified here,
# and an id cline rejects is worse than an absent one, so new arrivals go in
# through the picker's Custom row until they exist locally.
MODEL_CATALOG_USAGE_PAID = [
    ("Recommended", [
        ("Kimi K3", "moonshot-ai/kimi-k3"),
        ("Claude Opus 5", "anthropic/claude-opus-5"),
        ("Grok 4.5", "x-ai/grok-4.5"),
    ]),
]

# Free models cost nothing under either billing, so they belong to both lists
# and are never swapped out when the billing changes.
MODEL_CATALOG_FREE = [
    ("Free", [
        ("DeepSeek V4 Flash", "deepseek/deepseek-v4-flash"),
        ("GLM-5.3-Flash", "z-ai/glm-5.3-flash"),
        ("LongCat 2.0", "meituan/longcat-2.0-free"),
        ("Laguna S 2.1", "poolside/laguna-s-2.1"),
    ]),
]

FREE_MODEL_IDS = frozenset(mid for _, entries in MODEL_CATALOG_FREE
                           for _label, mid in entries)

CLINEPASS, CLINE_USAGE = "clinepass", "cline-usage"
BILLING_CHOICES = [CLINEPASS, CLINE_USAGE]
DEFAULT_BILLING = CLINEPASS
# The model a stage falls back to under each billing choice.
DEFAULT_MODEL_FOR_BILLING = {
    CLINEPASS: "cline-pass/deepseek-v4-pro",
    CLINE_USAGE: "deepseek/deepseek-v4-flash",
}


def model_catalog(billing):
    """The picker's groups for one billing choice, free models included."""
    paid = MODEL_CATALOG_USAGE_PAID if billing == CLINE_USAGE else MODEL_CATALOG_CLINEPASS
    return paid + MODEL_CATALOG_FREE


def billing_of_model(model):
    """Which billing a model id spends, read from the id itself.

    Mechanical rather than table-driven on purpose: a custom id the catalogue
    has never heard of still has to land on the right side of this. A free
    model spends neither, and returns "" -- see model_suits_billing.
    """
    if str(model) in FREE_MODEL_IDS:
        return ""
    return CLINEPASS if str(model).startswith("cline-pass/") else CLINE_USAGE


def model_suits_billing(model, billing):
    """Whether this model can be run under this billing.

    A free model suits both, so switching billing must not throw it away.
    """
    spends = billing_of_model(model)
    return not spends or spends == billing


MODEL_CATALOG = MODEL_CATALOG_CLINEPASS + MODEL_CATALOG_USAGE_PAID + MODEL_CATALOG_FREE

# id -> label, for the picker's display column and its filter.
MODEL_LABELS = {mid: label for _, entries in MODEL_CATALOG for label, mid in entries}


def valid_model_id(value):
    """cline model ids are `modelType/model`; an empty value means its default."""
    return not value or "/" in value

# Full description for each Configure item. Only the description of the row
# currently under the cursor is shown, in a panel to the right of the options.
CONFIG_DESC = {
    "derive-brief": (
        "Takes the input document and makes an AI ready REQUIREMENTS.md"
        " CHANGE_REQUEST.md."
    ),
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
    "field:network": (
        "Whether this stage's sandbox may reach the network. Shown only when "
        "the runner is codex, because it is the only runner that sandboxes a "
        "stage. Off by default, and worth leaving off: an agent that writes "
        "code and can also open a socket is a different proposition from one "
        "that cannot. Turn it on for a stage that has to serve the product it "
        "verifies — codex's workspace-write sandbox denies even a loopback "
        "bind, so without it a checklist row that needs the running site "
        "records BLOCKED, and no repair attempt can grant it a port."
    ),
    "field:billing": (
        "How this cline stage is paid for: `clinepass` spends the ClinePass "
        "subscription, `cline-usage` spends usage-based billing. It is not a "
        "flag passed to cline -- within cline's default provider the model id "
        "itself decides, so `cline-pass/kimi-k3` and a vendor-prefixed "
        "`kimi-k3` are two different purchases of the same model. Choosing "
        "here is choosing which model list the row below offers, and a model "
        "from the other list is dropped rather than carried across."
    ),
    "field:base_url": "The OpenAI-compatible API root OpenCode should use, for example http://localhost:8000/v1.",
    "field:api_key": "Endpoint credential, hidden while editing and stored separately in .uncle/self-hosted-keys.json. Use a placeholder for a server without authentication.",
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
        "workflow. Choose cline, claude, kimi, codex, or Self hosted (OpenCode). The runner "
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
    "derive-brief": (
        "Fills in a brief seeded from a GitHub issue, reading the issue text and "
        "any files frozen into reference/. What the issue does not settle becomes "
        "a TODO rather than an invented requirement. Skipped for a hand-written "
        "brief."
    ),
    "requirements": (
        "The stage that interprets the brief and turns it into a concrete, "
        "testable set of requirements. It runs after derive-brief in the New "
        "application and From GitHub issue workflows. Give it a model ID to use a "
        "dedicated model for this stage, or leave it at (default) to use the "
        "global model."
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
        "Drafts the change specification and ordered implementation plan in "
        "one session, using this model for both documents. "
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
            "self-hosted": shim("reviewer-self-hosted.sh"),
            "cline": shim("reviewer-cline.sh"),
            "codex": "codex",
            "claude": shim("reviewer-claude.sh"),
            "kimi": shim("reviewer-kimi.sh"),
        }
        return table.get(runner, table["cline"])
    table = {
        "self-hosted": shim("agent-self-hosted.sh"),
        "cline": shim("agent-cline.sh"),
        "claude": "claude",
        "kimi": shim("agent-kimi.sh"),
        "codex": shim("agent-codex.sh"),
    }
    return table.get(runner, table["cline"])


def runners_for(side):
    installed = []
    for binary in ("claude", "codex", "kimi", "cline", "opencode"):
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            directory = directory or "."
            path = os.path.join(directory, binary)
            try:
                if os.path.isdir(directory) and not os.access(directory, os.R_OK | os.X_OK):
                    raise PermissionError(directory)
                if not os.path.isfile(path):
                    continue
                if not os.access(path, os.X_OK):
                    sys.stderr.write("uncle: not executable: %s\n" % path)
                    continue
            except PermissionError:
                sys.stderr.write("uncle: cannot search PATH directory: %s\n" % directory)
                continue
            installed.append("self-hosted" if binary == "opencode" else binary)
            break
    return installed


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


SUPERVISION_MARKER_RE = re.compile(r'\s*' + re.escape(supervision_lib.MARKER_PREFIX) + r'[0-9a-f]{8}\s*')

SUPERVISION_DESC = {
    "enabled": "Opt in to event-triggered diagnosis (true/false). Off, nothing else here is read and no supervisor process ever starts; turning it off mid-run cancels the pending diagnosis and keeps the counters.",
    "runner": "The CLI that answers a diagnosis. Only claude is supported; anything else reports unavailable, never falls back. Corrections are fixed templates; the model's wording never reaches a stage.",
    "model": "Model id passed to the supervisor runner (default sonnet).",
    "effort": "Reasoning effort for the supervisor: low, medium or high.",
    "max_interventions": "Corrections applied per stage per run (default 2; 0 disables corrections). The next trigger asks you instead of calling a model.",
    "steering_timeout_seconds": "Seconds an accepted steering message may go unanswered during active stage time before a diagnosis (default 120). Only runners that confirm answers (claude, OpenCode) are timed.",
    "stage_time_seconds": "Active seconds a stage may run before a diagnosis, excluding gate waits (default 1800; 0 disables).",
    "stage_tokens": "Reported tokens a stage may use before a diagnosis (default 0 = off; unknown usage never triggers).",
    "call_timeout_seconds": "Deadline for one supervisor call; the worker tree is killed at the deadline (default 300).",
    "max_calls_per_run": "Supervisor calls allowed per workflow run, counted before each spawn (default 8).",
    "call_max_cost_usd": "Dollar cap passed to each supervisor call (default 0.50).",
}


class TuiSupervisionHost:
    """The controller's view of this screen: clocks, transcript, delivery, retry."""

    def __init__(self, tui, config):
        self.tui = tui
        self.config = config
        state_dir = os.path.join(_project_root(), '.uncle', 'workflow')
        contract_path = os.path.join(ROOT, 'prompts', 'supervise.md')
        with open(contract_path, encoding='utf-8') as fh:
            contract = fh.read()
        new_workflow = not os.path.exists(os.path.join(state_dir, 'state'))
        # Ownership (D-10) and live configuration reload (D-17) both live in the controller.
        self.controller = supervision_lib.Controller(state_dir, config, self, contract, new_workflow=new_workflow,
                                                     config_path=CONFIG_PATH)
        tui._ensure_chat()
        if self.controller.status:
            tui.home_history.append(('supervisor', sanitize(self.controller.status)))
        else:
            tui.home_history.append(('supervisor', 'Supervision enabled: %s/%s, %d interventions per stage, %d calls per run.'
                                     % (config.runner, config.model, config.max_interventions, config.max_calls_per_run)))

    def now(self):
        return time.monotonic()

    def transcript(self, text):
        self.tui._ensure_chat()
        self.tui.home_history.append(('supervisor', sanitize(text)))

    def ask(self, text):
        self.tui._ensure_chat()
        self.tui.home_history.append(('supervisor', sanitize(text)))
        self.tui.chat_error = sanitize(text)[:200]

    def roots(self):
        return [ROOT]

    def recent_output(self):
        return [line for line in list(getattr(self.tui, 'output', []))[-20:]]

    def workflow_state(self):
        try:
            with open(os.path.join(_project_root(), '.uncle', 'workflow', 'state'), encoding='utf-8') as fh:
                raw = fh.readline().strip()
        except OSError:
            return ''
        return raw.split(':', 1)[1] if re.match(r'^[0-9]+:', raw) else raw

    def driver_running(self):
        proc = getattr(self.tui, 'proc', None)
        return bool(proc) and proc.poll() is None

    def driver_stopped_by_human(self):
        if getattr(self.tui, 'state', '') == 'quit' or getattr(self.tui, 'workflow_exit_code', 0) in (130, 143):
            return True
        try:
            with open(os.path.join(_project_root(), '.uncle', 'workflow', 'stop-reason'), encoding='utf-8') as fh:
                return fh.readline().strip() == 'human'
        except OSError:
            return False

    def busy(self):
        return getattr(self.tui, 'triage_request', None) is not None

    def retry(self):
        self.tui._supervision_retry()

    def deliver(self, stage, channel, text, message_id):
        if self.tui.steering_channels.get(stage) != channel:
            return False
        if supervision_lib.deliver_steering(channel, text, message_id):
            self.tui.home_history.append(('supervisor', 'Steering correction queued for ' + stage))
            return True
        return False

    def close(self):
        self.controller.close()

    def start_worker(self, prompt, meta):
        command, env, home = supervisor_command(self.controller.config, ROOT)
        log = os.path.join(_project_root(), '.uncle', 'workflow', 'logs', 'supervisor-%d.jsonl' % meta['number'])
        return SupervisorRequest(command, prompt, env, home, log, meta)


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
        self._message_snapshot = ([], [])
        self._message_stream = []
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
        self.notice_destination = "config"
        self.notice_title = "markdown reader"
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
        self.misc = {}
        self.stage_runners = {}
        self.stage_models = {}
        self.stage_efforts = {}
        self.stage_networks = {}
        self.stage_billings = {}
        self.stage_base_urls = {}
        self.stage_api_keys = read_keys(CONFIG_PATH)
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
        # Bind the homepage composer before the first frame or key event.
        self._ensure_chat()
        self.chat_focus = 'chat'
        self.home_menu_open = False
        self.sel = 0
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
        return [w[0] for w in WORKFLOWS] + ["Configure", "Quit"]

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
        section = getattr(self, "config_section", "")
        if not section:
            return self._config_items()[self.config_sel]
        if section == "opencode":
            return "@connection"
        if section == "misc":
            return "!misc"
        if section == "supervision":
            return "!supervision"
        if 0 <= self.config_sel < len(CONFIG_STAGES):
            return CONFIG_STAGES[self.config_sel]
        return self._profile_targets()[self.config_sel - len(CONFIG_STAGES)]

    def _profile_targets(self):
        return ["@new"] + ["@" + name for name in sorted(self.stage_api_keys.get("__opencode_models__", {}))]

    # ---- effective values ----
    def stage_runner(self, stage):
        runner = self.stage_runners.get(stage, "")
        if runner in ("opencode", "aider"):
            return "self-hosted"
        if runner:
            return runner
        # An explicit default wins over discovery; it is "" in normal use,
        # so the installed-agent scan below is what actually decides.
        if DEFAULT_RUNNER:
            return DEFAULT_RUNNER
        installed = runners_for(STAGE_SIDE.get(stage, AGENT))
        return installed[0] if installed else ""

    def stage_effort(self, stage):
        return self.stage_efforts.get(stage, "") or default_stage_effort(stage)

    def stage_network(self, stage):
        """Whether this stage's sandbox may reach the network. Default off."""
        return self.stage_networks.get(stage, "") or "false"

    def stage_billing(self, stage):
        """How a cline stage is paid for: a ClinePass subscription or usage."""
        billing = self.stage_billings.get(stage, "")
        if billing in BILLING_CHOICES:
            return billing
        # An explicit model settles it on its own: a stage carrying a
        # `cline-pass/` id is spending the subscription whatever else is set.
        # A free model spends neither and settles nothing, so it falls through.
        model = self.stage_models.get(stage, "")
        if model:
            spends = billing_of_model(model)
            if spends:
                return spends
        return DEFAULT_BILLING

    def stage_model(self, stage):
        """The model for a stage, or "" when its runner takes none."""
        if self.stage_runner(stage) == "self-hosted":
            return self.stage_models.get(stage, "")
        if self.stage_runner(stage) != "cline":
            return ""
        model = self.stage_models.get(stage, "")
        if model:
            return model
        return DEFAULT_MODEL_FOR_BILLING.get(self.stage_billing(stage),
                                             DEFAULT_CLINE_MODEL)

    def stage_fields(self, stage):
        """The fields this stage's popup shows.

        Billing belongs to cline alone -- it is the only runner whose model
        list is bought two ways. Network belongs to codex alone: it is the
        only runner that sandboxes a stage, and so the only one where the
        setting changes anything. Every runner takes an effort: claude, kimi,
        cline, and codex as a reasoning level, self-hosted as the OpenCode
        model's reasoningEffort option.
        """
        if stage.startswith("@"):
            return ["base_url", "api_key"]
        runner = self.stage_runner(stage)
        if runner == "self-hosted":
            return ["runner", "effort", "model"]
        if runner == "cline":
            # Billing sits above model because it decides which models exist.
            return ["runner", "effort", "billing", "model"]
        if runner == "codex":
            return ["runner", "effort", "network"]
        return ["runner", "effort"]

    def _field_value(self, stage, field):
        """The stored value, empty when the stage inherits the default."""
        if stage == "!misc":
            return getattr(self, "misc", {}).get(field, "")
        if stage == "!supervision":
            return getattr(self, "supervision", {}).get(field, "")
        if stage == "@connection":
            return connection_settings(self.stage_api_keys).get(field, "")
        if stage.startswith("@"):
            name = stage[1:]
            if field == "name":
                return name
            return self.stage_api_keys.get("__opencode_models__", {}).get(name, {}).get(field, "")
        if field == "base_url":
            return self.stage_base_urls.get(stage, "")
        if field == "api_key":
            return self.stage_api_keys.get(stage, "")
        if field == "runner":
            return self.stage_runners.get(stage, "")
        if field == "effort":
            return self.stage_efforts.get(stage, "")
        if field == "model":
            return self.stage_models.get(stage, "")
        if field == "network":
            return self.stage_networks.get(stage, "")
        if field == "billing":
            return self.stage_billings.get(stage, "")
        return ""

    def _field_display(self, stage, field):
        stored = self._field_value(stage, field)
        if field == "api_key":
            return "********" if stored else "not set"
        if field == "base_url" or (field == "model" and self.stage_runner(stage) == "self-hosted"):
            return stored or "not set"
        if field == "runner" and stored == "self-hosted":
            return "OpenCode (Self hosted)"
        if stored:
            if field == "model":
                label = MODEL_LABELS.get(stored, "")
                return "%s  %s" % (stored, label) if label else stored
            return stored
        if field == "runner":
            return "%s  (default)" % (self.stage_runner(stage) or "No agents installed")
        if field == "effort":
            return "%s  (default)" % default_stage_effort(stage)
        if field == "network":
            return "false  (default)"
        if field == "billing":
            return "%s  (default)" % DEFAULT_BILLING
        fallback = DEFAULT_MODEL_FOR_BILLING.get(self.stage_billing(stage),
                                                 DEFAULT_CLINE_MODEL)
        label = MODEL_LABELS.get(fallback, "")
        return "%s  (default)%s" % (fallback, "  " + label if label else "")

    def _set_field(self, stage, field, value):
        value = (value or "").strip()
        self.maybe_reload()
        if stage == "!misc":
            self.misc[field] = value
            self.save_config()
            return
        if stage == "!supervision":
            if value:
                try:
                    value = supervision_lib.format_value(field, supervision_lib.parse_value(field, value))
                except ValueError as exc:
                    self.notice = str(exc)
                    return
                self.supervision[field] = value
            else:
                self.supervision.pop(field, None)
            self.save_config()
            return
        if stage == "@connection":
            connection = connection_settings(self.stage_api_keys)
            connection[field] = value
            if connection.get('base_url') and connection.get('api_key'):
                self.notice = "Discovering supported OpenCode models…"
                try:
                    refresh_models(self.stage_api_keys, connection['base_url'], connection['api_key'])
                except ValueError as exc:
                    self.notice = str(exc)
                    return
                self.notice = ""
            else:
                self.stage_api_keys['__opencode_connection__'] = connection
            self.save_config()
            return
        if field == "runner" and value != self.stage_runner(stage):
            self.stage_models.pop(stage, None)
        store = {"runner": self.stage_runners,
                 "effort": self.stage_efforts,
                 "model": self.stage_models,
                 "network": self.stage_networks,
                 "billing": self.stage_billings,
                 "base_url": self.stage_base_urls, "api_key": self.stage_api_keys}.get(field)
        if store is None:
            return
        if value:
            store[stage] = value
        else:
            store.pop(stage, None)
        self.save_config()

    def _apply_opencode_to_all_stages(self):
        """Use the selected stage's OpenCode connection throughout the workflow."""
        self.maybe_reload()
        source = self.stage_target
        if self.stage_runner(source) != "self-hosted":
            self.notice = "Select Self hosted and configure its connection first."
            return
        for store in (self.stage_models, self.stage_base_urls, self.stage_api_keys):
            value = store.get(source, "")
            for stage in CONFIG_STAGES:
                if value:
                    store[stage] = value
                else:
                    store.pop(stage, None)
        for stage in CONFIG_STAGES:
            self.stage_runners[stage] = "self-hosted"
        self.save_config()
        self.notice = "OpenCode and this LLM connection selected for all stages."

    def _config_items(self):
        section = getattr(self, "config_section", "")
        if not section:
            return ["1. Configure stages", "2. Configure OpenCode / self hosting", "3. Miscellaneous", "4. Supervision"]
        if section == "supervision":
            return self._supervision_items()
        if section == "opencode":
            return ["OpenCode connection — Base URL and API key", "Refresh supported models (%d loaded)" % len(self.stage_api_keys.get("__opencode_models__", {}))]
        if section == "misc":
            return ["Auto mode: " + ("on" if getattr(self, "misc", {}).get("auto_mode") == "true" else "off"),
                    "Name for approvals: " + getattr(self, "misc", {}).get("approval_name", "not set")]
        """One row per stage: the stage, its runner, and what that runner uses."""
        width = max(len(s) for s in BUILD_CONFIG_STAGES)
        rows = []
        for stage in BUILD_CONFIG_STAGES:
            parts = ["Self hosted (OpenCode)" if self.stage_runner(stage) == "self-hosted" else self.stage_runner(stage)]
            model = self.stage_model(stage)
            if model:
                parts.append(MODEL_LABELS.get(model, model))
            if "effort" in self.stage_fields(stage):
                parts.append(self.stage_effort(stage))
            # Named on the row, not just inside the popup: which stage can
            # open a socket is the one setting here worth seeing at a glance.
            if "network" in self.stage_fields(stage) and self.stage_network(stage) == "true":
                parts.append("network")
            rows.append("%s  %s" % (stage.ljust(width), " · ".join(parts)))
        return rows

    def _stage_items(self):
        """Rows of the open stage's popup."""
        stage = self.stage_target
        rows = []
        for field in self.stage_fields(stage):
            rows.append("%s  %s" % ({"base_url": "Base URL", "api_key": "API key"}.get(field, field).ljust(8), self._field_display(stage, field)))
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
            if field == "model" and self.stage_runner(self.stage_target) == "self-hosted":
                return "Choose one of your configured OpenCode self-hosted models. Set the Base URL and API key to discover models in Configure → Configure OpenCode / self hosting."
            if field == "runner":
                side = STAGE_SIDE.get(self.stage_target, AGENT)
                desc += " This is a %s stage, so its choices are %s." % (
                    side, ", ".join(runners_for(side)))
            return desc
        if getattr(self, "config_section", "") == "misc":
            return "Auto mode runs unattended: human gates are recorded as waived; failing tests still stop the run. The approval name identifies your manual approvals."
        if getattr(self, "config_section", "") == "supervision":
            return self._supervision_desc()
        if not getattr(self, "config_section", ""):
            return "Choose a configuration section."
        return CONFIG_DESC.get(self._config_row(), "")

    # ---- generic picker (model / effort / runner) ----
    def _picker_rows(self):
        """Rows for the active picker: (kind, text), kind in header/option/model/custom."""
        if self.picker_kind == "effort":
            return [("option", e) for e in EFFORTS] + [("custom", "Custom… (type an effort)")]
        if self.picker_kind == "runner":
            side = STAGE_SIDE.get(self.picker_target, AGENT)
            return [("option", r) for r in runners_for(side)]
        if self.picker_kind == "billing":
            # Two purchases, no custom row: a typed value would not be one.
            return [("option", b) for b in BILLING_CHOICES]
        if self.picker_kind == "network":
            # Two states and no custom row: the sandbox is either open or it
            # is not, and a typed value here would read as a setting while
            # meaning nothing to the flag it becomes.
            return [("option", v) for v in NETWORK_CHOICES]
        if self.picker_kind == "model" and self.stage_runner(self.picker_target) == "self-hosted":
            return ([("option", name) for name in sorted(self.stage_api_keys.get("__opencode_models__", {}))]
                    + [("custom", "Custom… (type a model id)")])
        rows = []
        for group, entries in model_catalog(self.stage_billing(self.picker_target)):
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
        if self.picker_kind == "network":
            return self.stage_network(stage)
        if self.picker_kind == "billing":
            return self.stage_billing(stage)
        return self.stage_model(stage)

    def _open_picker(self, kind, target):
        self.notice = ""
        self.picker_kind = kind
        self.picker_target = target
        if kind == "runner" and not runners_for(STAGE_SIDE.get(target, AGENT)):
            self.notice = "No agents installed. Install claude, codex, kimi, cline, or opencode and add its executable to PATH."
            return
        if kind in ("name", "base_url", "api_key", "approval_name") or target == "!supervision":
            self.input_buf = self._field_value(target, kind)
            self.state = "config_edit"
            return
        if kind == "model" and self.stage_runner(target) == "self-hosted" and not self.stage_api_keys.get("__opencode_models__"):
            self.notice = "Set up your endpoint in Configure → Configure OpenCode / self hosting to discover models first."
            return
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
        if self.picker_kind == "billing":
            # The stored model belongs to one billing or the other. Carrying a
            # `cline-pass/` id into usage billing would quietly spend the wrong
            # thing, so a model from the other list is dropped and the new
            # billing's default applies until something is picked.
            current = self.stage_models.get(self.picker_target, "")
            if current and not model_suits_billing(current, text):
                self._set_field(self.picker_target, "model", "")
        self._set_field(self.picker_target, self.picker_kind, text)
        # Choosing a non-cline runner drops the model row out of the popup.
        self.stage_sel = min(self.stage_sel,
                             len(self.stage_fields(self.picker_target)) - 1)
        self.state = "stage"

    @staticmethod
    def _valid_issue(value):
        return bool(re.fullmatch(r'[1-9][0-9]*|https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*/?', value))

    def cmd_for(self):
        auto = ["--unattended"] if getattr(self, "misc", {}).get("auto_mode") == "true" else []
        if self.workflow_idx == 1:
            if not self._valid_issue(self.issue):
                raise ValueError('Enter a GitHub issue number or https://github.com/owner/repo/issues/123')
            cmd = list(WORKFLOWS[1][1]) + [self.issue]
            if self.issue_mode:
                cmd.append(self.issue_mode)
            return cmd + auto
        return list(WORKFLOWS[self.workflow_idx][1]) + auto

    # ---- config ----
    #
    # Grammar, one setting per line:
    #
    #   <stage>.runner  cline | claude | kimi | codex
    #   <stage>.effort  high | medium | low
    #   <stage>.model   a cline model id, and only for a cline stage
    #   <stage>.network true | false, and only for a codex stage — whether
    #                   its workspace-write sandbox may reach the network,
    #                   which includes binding a loopback port
    #
    # Older files carried global `runner` / `model` / `effort` / `billing` lines, a bare
    # `<stage> <model>` line, and a `reviewer <model>` line. Those are still
    # read — as the seed for stages the file does not configure explicitly —
    # and are never written back, so the first save migrates the file.
    LEGACY_REVIEWER_KEY = "reviewer"

    def load_config(self):
        exists = os.path.exists(CONFIG_PATH)
        self.misc = {}
        self.supervision = {}
        self.stage_runners = {}
        self.stage_models = {}
        self.stage_efforts = {}
        self.stage_networks = {}
        self.stage_billings = {}
        self.stage_base_urls = {}
        self.stage_api_keys = read_keys(CONFIG_PATH)
        if not exists:
            # Track missing configuration without redirecting away from home.
            self.first_run = True
            self._config_stamp = None
            return self.first_run
        self.first_run = False
        legacy = {"runner": "", "model": "", "effort": "", "billing": "", "reviewer": ""}
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
                    if key in ("misc.auto_mode", "misc.approval_name"):
                        self.misc[key.split(".", 1)[1]] = val
                    elif key.startswith("supervision."):
                        # Kept verbatim, valid or not: the typed parser reports
                        # an invalid value on the Supervision screen and the
                        # driver side fails closed; a rewrite must not lose it.
                        self.supervision.setdefault(key.split(".", 1)[1], val)
                    elif key in legacy:
                        legacy[key] = val
                    elif "." in key:
                        stage, field = key.rsplit(".", 1)
                        if stage in STAGE_SIDE and field in STAGE_FIELDS and field != "api_key":
                            self._store_for(field)[stage] = val
                    elif key in STAGE_SIDE:
                        # Legacy bare "<stage> <model>".
                        self.stage_models[key] = val
        except Exception:
            pass
        self._seed_from_legacy(legacy)
        # Preserve selections from the old prefixed model catalog.
        profiles = self.stage_api_keys.get('__opencode_models__', {})
        for stage, name in list(self.stage_models.items()):
            if self.stage_runner(stage) == 'self-hosted':
                self.stage_models[stage] = local_model(name)
        # Preserve existing per-stage connections as reusable named models.
        for stage in CONFIG_STAGES:
            name = self.stage_models.get(stage, "")
            if self.stage_runner(stage) != "self-hosted" or not name or not self.stage_base_urls.get(stage):
                continue
            profiles = self.stage_api_keys.setdefault("__opencode_models__", {})
            profile = dict(base_url=self.stage_base_urls[stage], api_key=self.stage_api_keys.get(stage, ""), model=name.removeprefix("local/"))
            selected = name
            if selected in profiles and profiles[selected] != profile:
                selected = name + "-" + stage
                profile['model'] = name
            profiles.setdefault(selected, profile)
            self.stage_models[stage] = selected
            self.stage_base_urls.pop(stage, None)
            self.stage_api_keys.pop(stage, None)
        self._config_stamp = self._stamp()
        return self.first_run

    def _stamp(self):
        """Cheap identity of the config file, to notice edits from outside."""
        try:
            st = os.stat(CONFIG_PATH)
            try:
                secret = key_file(CONFIG_PATH).stat()
                secret_stamp = (secret.st_mtime_ns, secret.st_size)
            except OSError:
                secret_stamp = None
            return (st.st_mtime_ns, st.st_size, secret_stamp)
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
                                     len(self._config_items()) - 1))
        if getattr(self, "stage_target", "") not in STAGE_SIDE and not getattr(self, "stage_target", "").startswith("@"):
            self.stage_target = CONFIG_STAGES[0]
        fields = self.stage_fields(self.stage_target)
        self.stage_sel = max(0, min(getattr(self, "stage_sel", 0), len(fields) - 1))

    def _store_for(self, field):
        return {"runner": self.stage_runners,
                "effort": self.stage_efforts,
                "model": self.stage_models,
                "network": self.stage_networks,
                "billing": self.stage_billings,
                 "base_url": self.stage_base_urls, "api_key": self.stage_api_keys}[field]

    def _seed_from_legacy(self, legacy):
        """Turn old global settings into per-stage ones, without overwriting."""
        for stage in CONFIG_STAGES:
            if legacy["runner"] and stage not in self.stage_runners:
                self.stage_runners[stage] = legacy["runner"]
            if legacy["effort"] and stage not in self.stage_efforts:
                self.stage_efforts[stage] = legacy["effort"]
            if legacy["billing"] and stage not in self.stage_billings:
                self.stage_billings[stage] = legacy["billing"]
            model = legacy["model"]
            if STAGE_SIDE.get(stage) == REVIEWER and legacy["reviewer"]:
                model = legacy["reviewer"]
            if model and stage not in self.stage_models:
                self.stage_models[stage] = model

    def save_config(self):
        header = (
            "# Uncle per-stage config: every stage picks its own runner,\n"
            "# reasoning effort, and model where supported.\n"
            "# Format: <stage>.runner | <stage>.effort | <stage>.model |\n"
            "#         <stage>.network VALUE\n"
            "#   (VALUE = runner, effort, model, or true/false for network).\n"
            "# OpenCode connections and credentials are stored separately.\n"
            "# Edit from `uncle` ->\n"
            "#   Configure, or by hand.\n"
        )
        try:
            with open(CONFIG_PATH, "w") as fh:
                fh.write(header)
                for key, value in getattr(self, "misc", {}).items():
                    fh.write("misc.%s %s\n" % (key, value))
                for key, value in getattr(self, "supervision", {}).items():
                    fh.write("supervision.%s %s\n" % (key, value))
                for stage in CONFIG_STAGES:
                    lines = []
                    runner = self.stage_runners.get(stage, "")
                    if runner:
                        lines.append("%s.runner %s\n" % (stage, runner))
                    if self.stage_efforts.get(stage):
                        lines.append("%s.effort %s\n" % (stage, self.stage_efforts[stage]))
                        
                    # Keep dormant selections for a later runner switch;
                    # stage_model controls whether the current runner reads it.
                    if self.stage_models.get(stage):
                        lines.append("%s.model %s\n" % (stage, self.stage_models[stage]))
                    # Likewise network, which only a codex stage sandboxes. It
                    # is written whenever it is set so that a hand-edited line
                    # survives this rewrite instead of being silently dropped.
                    if self.stage_networks.get(stage):
                        lines.append("%s.network %s\n" % (stage, self.stage_networks[stage]))
                    # Billing, like model, is a cline-only setting; written
                    # whenever set so a hand-edited line survives the rewrite.
                    if self.stage_billings.get(stage):
                        lines.append("%s.billing %s\n" % (stage, self.stage_billings[stage]))
                    if self.stage_base_urls.get(stage):
                        lines.append("%s.base_url %s\n" % (stage, self.stage_base_urls[stage]))
                    if lines:
                        fh.write("\n")
                        for line in lines:
                            fh.write(line)
        except Exception:
            pass
        save_keys(CONFIG_PATH, self.stage_api_keys)
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
        return dict({"UNCLE_CONFIG": CONFIG_PATH}, **({"UNCLE_APPROVAL_NAME": self.misc["approval_name"]} if getattr(self, "misc", {}).get("approval_name") else {}))

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
        kind = ev.get('event', '')
        host = getattr(self, 'supervision_host', None)
        if host is not None:
            try:
                host.controller.observe(ev)
            except (OSError, ValueError) as exc:
                self._ensure_chat()
                self.home_history.append(('supervisor', 'Supervision error: ' + sanitize(str(exc))))
        if kind.startswith('steering_') or kind == 'chat_output':
            if getattr(self, 'workflow_exit_reported', False):
                return  # Late buffered events cannot reconnect a stopped build.
            self._ensure_chat()
            channels = getattr(self, 'steering_channels', {})
            self.steering_channels = channels
            stage = ev.get('stage', '')
            if kind == 'steering_ready':
                channels[stage] = ev.get('channel', '')
            elif kind == 'steering_closed':
                if channels.get(stage) == ev.get('channel'):
                    channels.pop(stage, None)
            elif kind == 'chat_output':
                text = SUPERVISION_MARKER_RE.sub('', sanitize(ev.get('text', '')))
                role = 'assistant (' + stage + ')'
                if self.home_history and self.home_history[-1][0] == role:
                    self.home_history[-1] = (role, (self.home_history[-1][1] + text)[-1024*1024:])
                else:
                    self.home_history.append((role, text))
            elif kind in ('steering_accepted', 'steering_rejected'):
                text = ('Steering accepted by ' + stage if kind == 'steering_accepted' else
                        'Steering was not delivered: ' + sanitize(ev.get('detail', 'Stage ended')))
                self.home_history.append(('system', text))
                if kind == 'steering_rejected': self.chat_error = text
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
            self.status_runner = ev.get("runner", getattr(self, "status_runner", ""))
            self.status_model = ev.get("model", "")
            self.status_effort = ev.get("effort", "")
            self.status_mode = ev.get("mode", "")
            self.status_stage = ev.get("stage", "")
            self.status_stage_index = int(ev.get("stage_index", 0) or 0)
            self.status_stage_total = int(ev.get("stage_total", 0) or 0)
        elif ev.get("event") == "usage" and stage == self.status_stage:
            self.status_model = ev.get("model", self.status_model)
            self.status_mode = ev.get("mode", self.status_mode)

    # ---- running ----
    def _title_issue(self, env):
        workflow_idx = getattr(self, "workflow_idx", None)
        if workflow_idx == 1:
            match = re.match(r"^https?://github\.com/[^/]+/[^/]+/issues/([0-9]+)", self.issue)
            issue = match.group(1) if match else self.issue
        elif workflow_idx == 2:
            try:
                with open(os.path.join(_project_root(), ".uncle", "workflow", "origin"),
                          encoding="utf-8") as origin:
                    fields = origin.readline().rstrip("\n").split("\t")
            except (OSError, UnicodeError):
                fields = []
            repo = env.get("STAGEGATE_ORIGIN_REPO") or (fields[0] if fields else "")
            issue = env.get("STAGEGATE_ORIGIN_ISSUE") or (fields[1] if len(fields) > 1 else "")
            if not repo:
                return ""
        else:
            return ""
        return issue if re.fullmatch(r"[0-9]+", issue) else ""

    def _write_title(self, title):
        try:
            if (sys.stdout.isatty() and sys.stderr.isatty()
                    and os.environ.get("TERM") not in (None, "", "dumb")):
                sys.stdout.write("\033]2;" + title + "\007")
                sys.stdout.flush()
                return True
        except (OSError, ValueError):
            pass
        return False

    def _begin_title(self, env):
        self._end_title()
        issue = self._title_issue(env)
        if issue and not env.get("UNCLE_TITLE_OWNER"):
            self.title_active = self._write_title("uncle issue #" + issue)
            if self.title_active:
                env["UNCLE_TITLE_OWNER"] = str(os.getpid())

    def _end_title(self):
        if getattr(self, "title_active", False):
            self.title_active = False
            self._write_title("uncle")

    def _poll_workflow(self):
        if getattr(self, "proc", None) and self.proc.poll() is not None:
            self._end_title()
            if not getattr(self, 'workflow_exit_reported', False):
                self.workflow_exit_reported = True
                self.workflow_exit_code = self.proc.returncode
                self.steering_channels = {}
                # EOF handling can open the completion dialog just before
                # this poll observes process exit. Keep that dialog focused.
                if getattr(self, 'prompt_kind', '') not in ('support', 'finished'):
                    self.prompt_kind = ''
                    self.chat_focus = 'chat'
                self._ensure_chat()
                reason = 'Workflow was killed (SIGKILL, exit code 137)' if self.workflow_exit_code in (137, -9) else 'Workflow stopped (exit code %s)' % self.workflow_exit_code
                message = reason + '. Stage chat disconnected. Press Esc to return to the menu.'
                self.home_history.append(('system', message))
                self.chat_error = message
                host = getattr(self, 'supervision_host', None)
                if host is not None:
                    # Triage owns a failure exit; an in-flight diagnosis is
                    # cancelled (and charged) and queued triggers wait for it.
                    host.controller.cancel('interrupted')
                    host.controller.driver_exited(self.workflow_exit_code)
                self._maybe_auto_triage()

    def start_workflow(self):
        fd, self.status_path = tempfile.mkstemp(prefix="uncle-status-", suffix=".jsonl")
        os.close(fd)
        env = dict(os.environ)
        env.update(self.stage_env())
        env.pop("UNCLE_NEW_WORKFLOW", None)
        if getattr(self, "new_workflow_pending", False):
            env["UNCLE_NEW_WORKFLOW"] = "1"
        env["UNCLE_STATUS_FILE"] = self.status_path
        env["UNCLE_STEERING"] = "1"
        self.steering_channels = {}
        self._supervision_start(env)
        env["UNCLE_SIGNING_JSON"] = "1"
        self.status_pos = 0
        self.panel_scroll = None
        self.proc_done = False
        self.workflow_completed = False
        self.workflow_exit_reported = False
        self.support_checked = False
        self.completion_preview = None
        metrics = os.path.join(_project_root(), ".uncle", "workflow", "metrics")
        self.session_stats = {"active": {}, "live": {}, "records": [], "tick": -1,
                              "seen": set(os.listdir(metrics)) if os.path.isdir(metrics) else set()}
        self._restore_session_totals()
        self.output = []
        self._message_snapshot = ([], [])
        self._message_stream = []
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
        self.workflow_launch_time = time.time()
        # stdin is a pipe because the workflow asks questions: four human
        # gates, plus the odd retry or confirmation. Under curses the driver
        # cannot have the terminal, so the answers are typed into this screen
        # and written down the pipe.
        self._begin_title(env)
        try:
            self.proc = subprocess.Popen(self.cmd_for(), cwd=_project_root(), env=env,
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         bufsize=0)
        except BaseException:
            self._end_title()
            raise
        self.new_workflow_pending = False
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
        self._poll_workflow()
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
        if self.proc_done:
            self._offer_support()
        else:
            self._detect_prompt()
        preview_changed = self._poll_completion_preview()
        return got or preview_changed or before != (self.proc_done, self.prompt_kind)

    def _offer_support(self):
        """Offer once per local user, only after this workflow finishes."""
        if getattr(self, "support_checked", False) or not self.proc:
            return
        code = self.proc.poll()
        if code is None:
            return
        self.support_checked = True
        self.prompt_kind = ""
        if code != 0 or not getattr(self, "workflow_completed", False):
            return
        self.completion_preview = CompletionPreview(_project_root())
        self.chat_focus = "chat"

    def _poll_completion_preview(self):
        preview = getattr(self, 'completion_preview', None)
        if preview is None:
            return False
        changed = False
        try:
            while True:
                kind, value = preview.events.get_nowait()
                changed = True
                if kind == 'output':
                    self._ensure_chat()
                    self.home_history.append(('application', sanitize(value)))
                elif kind == 'done':
                    self._completion_dialog(value)
                elif kind == 'terminal':
                    try:
                        self._run_in_terminal(value, cwd=preview.root)
                    finally:
                        preview.terminal_done.set()
        except queue.Empty:
            pass
        return changed

    def _completion_dialog(self, starred):
        base = os.environ.get('XDG_STATE_HOME')
        if not base or not os.path.isabs(base):
            base = os.path.join(os.path.expanduser('~'), '.local', 'state')
        marker = os.path.join(base, 'uncle', 'star-prompt-shown')
        offer = not starred
        if offer:
            try:
                os.makedirs(os.path.dirname(marker), exist_ok=True)
                with open(marker, 'x') as stream:
                    stream.write('shown\n')
            except OSError:
                offer = False
        self.prompt_kind = 'support' if offer else 'finished'
        self.chat_focus = 'gate'
        self.prompt_text = ('Finished. Support Uncle by adding a star on GitHub: '
                            + STAR_URL + " This popup won't bother you again.") if offer else 'Finished'

    def _absorb_line(self, line):
        # Native chat text is assembled through status events; retain its raw
        # JSON in driver logs without displaying a second copy here.
        try:
            event = json.loads(line)
            if isinstance(event, dict) and event.get('uncle_chat_output') is True:
                return
        except ValueError:
            pass
        if self.state == 'running':
            self._build_messages()
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
        if text in ("Workflow complete.", "Change workflow complete."):
            self.workflow_completed = True
        # A gate opens with this banner, then reads a bare newline before it
        # asks the real question. bash prints a `read -p` prompt only to a
        # terminal, so over a pipe that read is invisible: nothing appears and
        # the run looks hung. Answer it here — the decision is the [Y/N] that
        # follows, and that one gets a modal.
        if text.startswith("AUDIT REVIEW REQUIRED:"):
            # Audit findings ask for a decision immediately, with no initial
            # press-Enter gate. Never send a synthetic answer here.
            self.gate_file = text.split(":", 1)[1].strip()
            return
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

    def _run_in_terminal(self, cmd, cwd=None):
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
            viewer = subprocess.Popen(cmd, shell=isinstance(cmd, str), cwd=cwd)
            while viewer.poll() is None:
                self.poll_home_chat()
                self._poll_workflow()
                time.sleep(.1)
            self.poll_home_chat()
            self._poll_workflow()
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
        if ("PR title [default: ".startswith(plain)
                or plain.startswith("PR title [default:") and not plain.endswith("]:")):
            return
        signing_prefix = next((prefix for prefix in ("Commit signing needs your help. ", "Commit needs your help. ")
                               if prefix.startswith(plain) or plain.startswith(prefix)),
                              "Commit signing needs your help. ")
        signing_suffix = " Return here and press ENTER (OK) when finished:"
        if signing_prefix.startswith(plain) or plain.startswith(signing_prefix):
            if not plain.endswith("press ENTER (OK) when finished:"):
                return
            self.signing_command = ""
            payload = plain[len(signing_prefix):]
            if payload.startswith('"'):
                try:
                    command, end = json.JSONDecoder().raw_decode(payload)
                except ValueError:
                    return
                if not isinstance(command, str) or payload[end:] != signing_suffix:
                    return
                self.signing_command = command
                self.signing_copy_status = ""
                self.prompt_kind = "enter"
                self.chat_focus = "gate"
                self.prompt_text = signing_prefix + "Run in another terminal:\n" + command
                self.prompt_buf = ""
                self.prompt_scroll = 0
                return
        upper = plain.upper()
        if plain.startswith("PR title [default: "):
            self.prompt_kind = "input"
        elif plain.startswith("Audit finding ") and "[s] Skip" in plain:
            self.prompt_kind = "audit"
        elif "[Y/N]" in upper:
            self.prompt_kind = "confirm"
        elif "PRESS ENTER" in upper:
            self.prompt_kind = "enter"
        else:
            self.prompt_kind = "input"
        self.chat_focus = "gate"
        self.prompt_text = plain
        self.prompt_buf = ""
        if plain.startswith("PR title [default: ") and plain.endswith("]:"):
            self.prompt_buf = plain[len("PR title [default: "):-2]
        self.prompt_scroll = 0

    def _copy_signing_command(self):
        if sys.platform == "darwin":
            candidates = [["pbcopy"]]
        elif os.environ.get("WAYLAND_DISPLAY"):
            candidates = [["wl-copy"]]
        elif os.environ.get("DISPLAY"):
            candidates = [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
        else:
            candidates = []
        try:
            for argv in candidates:
                executable = shutil.which(argv[0])
                if executable:
                    subprocess.run([executable] + argv[1:], input=self.signing_command.encode("utf-8"),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=2, check=True)
                    self.signing_copy_status = "Copied command"
                    return
            raise OSError("no clipboard helper available")
        except (OSError, subprocess.SubprocessError) as error:
            self.signing_copy_status = "Copy failed: " + str(error)

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

    def _triage_blocks_stdin(self):
        """A gate answer during a triage turn would race the guard's apply."""
        if getattr(self, 'triage_request', None) is None:
            return False
        self.chat_error = 'A triage turn is running. Finish it or press Esc in triage before answering the gate.'
        return True

    def _send_raw(self, answer):
        """Write one line to the driver's stdin without touching modal state."""
        if not self.proc or self.proc.poll() is not None or self._triage_blocks_stdin():
            return
        try:
            self.proc.stdin.write((answer + "\n").encode())
            self.proc.stdin.flush()
        except Exception:
            pass

    def answer_prompt(self, answer):
        """Send one line down the driver's stdin and close the modal."""
        if self._triage_blocks_stdin():
            return
        self.chat_focus = "chat"
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
        if getattr(self, "completion_preview", None):
            self.completion_preview.close()
            self.completion_preview = None
        if self.proc and self.proc.poll() is None:
            subprocess.run(["bash", os.path.join(ROOT, "scripts", "lib", "terminal-title.sh"),
                            "--stop-tree", str(self.proc.pid), "include-root"], check=True)
            self.proc.wait()
        self._end_title()
        self.proc = None
        self.status_model = ""
        self.status_effort = ""
        self.status_mode = ""
        self.status_stage = ""
        self.status_stage_index = 0
        self.status_stage_total = 0

    def _ensure_chat(self):
        if not hasattr(self, 'chat'):
            self.chat = Conversation(_project_root())
            self.chat.refs.allow_parent = True
            self.chat_composer = ''
            self.chat_error = ''
            self.chat_choices = []
            self.chat_pick = 0
            self.chat_picker = False
            self.chat_picker_kind = 'file'
            self.chat_edit = False
            self.chat_focus = 'chat'
            self.home_menu_open = False
            self.home_request = None
            self.home_history = []
            self.home_issue_context = ''
        self.chat_open = True

    def open_chat(self):
        self._ensure_chat()
        self.chat_focus = 'chat'
        self.state = 'running' if self.proc and self.proc.poll() is None else 'chat'

    def homepage_model(self):
        """Use the first stage shown in Configure for homepage inference."""
        stage = CONFIG_STAGES[0]
        return stage, self.stage_runner(stage), self.stage_model(stage), self.stage_effort(stage)

    def chat_model(self):
        """Follow the live stage for workflow chat; use the first stage at home."""
        if getattr(self, 'recovery_active', False):
            return ('triage',) + self._triage_runner()
        if self.state != 'running':
            return self.homepage_model()
        stage = getattr(self, 'status_stage', '')
        if not stage:
            return '', '', '', ''
        if stage.startswith('implementation-step-'):
            stage = 'implementation'
        elif stage in ('manual-checklist-base', 'manual-checklist-delta'):
            stage = 'manual-checklist'
        runner = getattr(self, 'status_runner', '') or self.stage_runner(stage)
        if runner in ('opencode', 'aider'):
            runner = 'self-hosted'
        model = getattr(self, 'status_model', '') or self.stage_model(stage)
        effort = getattr(self, 'status_effort', '') or self.stage_effort(stage)
        return stage, runner, model, effort

    def steer_stage(self, message):
        if getattr(self, 'workflow_exit_reported', False):
            raise ValueError('The workflow has stopped. Press Esc to return to chat; your draft is kept.')
        stage = getattr(self, 'status_stage', '')
        channel = getattr(self, 'steering_channels', {}).get(stage)
        if not channel or not self.proc or self.proc.poll() is not None:
            raise ValueError('The active stage is not accepting steering yet. Your draft has been kept.')
        if not message.strip():
            return
        payload = self.chat.refs.expand(sanitize(message))
        if len(payload.encode('utf-8')) > 60000:
            raise ValueError('Steering context exceeds 60 KB; use smaller attachments.')
        id = str(uuid.uuid4())
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=channel)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'id':id, 'text':payload}, stream)
            self.chat.send(message)
            try:
                os.replace(temporary, os.path.join(channel, str(time.time_ns()) + '-' + id + '.json'))
            except OSError:
                self.chat.messages.pop()
                raise
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        self.home_history.append(('user', sanitize(message)))
        self.home_history.append(('system', 'Steering queued for ' + stage))
        host = getattr(self, 'supervision_host', None)
        if host is not None:
            host.controller.steering_queued(stage, id, payload)

    def send_home_chat(self, message):
        preview = getattr(self, 'completion_preview', None)
        if preview and preview.kind == 'command' and preview.process and preview.process.poll() is None:
            preview.send(message)
            return
        if getattr(self, 'recovery_active', False):
            self._triage_turn('diagnosis', followup=message)
            return
        gate_question = (self.state == 'running' and bool(getattr(self, 'prompt_kind', ''))
                         and self.proc is not None and self.proc.poll() is None)
        # A channel can outlive its runner while the driver waits for approval.
        # Gate questions must get a reply, not enter that unconsumed queue.
        if self.state == 'running' and not gate_question:
            return self.steer_stage(message)
        if self.home_request is not None:
            raise ValueError('A reply is still running. Wait or use /clear to cancel.')
        if not message.strip():
            return
        issue_request = re.fullmatch(
            r'(?:please\s+)?(?:build|implement|start|run|work on)\s+'
            r'(?:(?P<change>change\s+request)\s+)?'
            r'(?:(?:from\s+)?(?:github\s+)?issue\s+|from\s+|this\s+)'
            r'(?P<issue>https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*/?|#?[1-9][0-9]*)[.!]?',
            message.strip(), re.IGNORECASE)
        if issue_request and not gate_question:
            self.home_history.append(('user', sanitize(message)))
            # Asked to implement an issue now: select auto mode so the run
            # answers its own gates and the build page goes straight to work.
            self._set_field("!misc", "auto_mode", "true")
            self._home_action({'uncle_action': 'github_issue',
                               'issue': issue_request['issue'].removeprefix('#'),
                               'start': True,
                               'issue_mode': '--change' if issue_request['change'] else ''})
            return
        stage, runner, model, effort = self.chat_model()
        if self.state == 'running' and not stage:
            raise ValueError('Waiting for the current stage model. Retry when the stage starts.')
        if not runner:
            raise ValueError('Choose a runner in Configure first')
        user_text = self.chat.refs.expand(sanitize(message))
        history = self.home_history + [('user', user_text)]
        if gate_question:
            prompt = ('Answer questions about the pending stage decision. The workflow is paused. '
                      'Do not approve, reject, run commands, edit files, or emit homepage actions. '
                      'Only the user can answer the pending dialog. Explain proposed changes; '
                      'do not claim to have applied them. This is a separate question session '
                      'using the stage model, not a continuation of the completed runner.\n'
                      + 'Stage: ' + stage + '\nPending dialog: ' + self.prompt_text + '\n')
            root = Path(_project_root())
            candidates = [getattr(self, 'gate_file', ''), 'MANUAL_CHECKLIST.md',
                          'IMPLEMENTATION_NOTES.md', 'VERIFICATION_REPORT.md', 'FINAL_AUDIT.md',
                          'CHANGE_PLAN.md', 'UPDATED_PROJECT_PLAN.md']
            remaining = 55000
            seen = set()
            for name in candidates:
                if not name or name in seen:
                    continue
                seen.add(name)
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    continue
                with path.open('rb') as source:
                    content = source.read(min(12000, remaining))
                remaining -= len(content)
                prompt += '\nDocument excerpt (' + name + '):\n' + content.decode('utf-8', 'replace') + '\n'
                if remaining <= 0:
                    break
            prompt += '\nConversation:\n' + '\n'.join(role + ': ' + text for role, text in history[-12:])
        else:
            prompt = home_action_prompt(history, _project_root())
        if not issue_references(message):
            prompt += getattr(self, 'home_issue_context', '')
        if len(prompt.encode('utf-8')) > 100000:
            raise ValueError('Chat context is too large for this runner. Use /clear or smaller attachments.')
        command = [runner_command(runner, REVIEWER), 'exec', '--ephemeral',
                   '--skip-git-repo-check', '--sandbox', 'read-only',
                   '-c', 'model_reasoning_effort=' + effort]
        if model:
            command += ['--model', model]
        env = os.environ.copy()
        for name in ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_STEERING', 'STAGEGATE_RUN_ID',
                     'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE'):
            env.pop(name, None)
        env['UNCLE_CONFIG'] = str(CONFIG_PATH)
        env['UNCLE_STATUS_STAGE'] = stage
        if runner == 'self-hosted':
            values = home_settings(CONFIG_PATH, stage)
            if self.state == 'running' and getattr(self, 'status_model', ''):
                values['model'] = model.removeprefix('openai/').removeprefix('local/')
            for field in ('model', 'base_url', 'api_key'):
                env['UNCLE_SELF_HOSTED_' + field.upper()] = values[field]
        if runner == 'cline':
            env['UNCLE_CLINE_EFFORT'] = effort
            if model:
                env['UNCLE_CLINE_MODEL'] = env['UNCLE_CLINE_REVIEWER_MODEL'] = model
        self.chat.send(message)
        self.home_history = history
        if issue_references(message) and not gate_question:
            root = _project_root()
            self.home_request = HomeRequest(command, prompt, env,
                                            issue_lookup=lambda: issue_context(root, message), cwd=root)
        else:
            self.home_request = HomeRequest(command, prompt, env, cwd=_project_root())
        self.home_request.gate_question = gate_question

    def poll_home_chat(self):
        request = getattr(self, 'home_request', None)
        if request is None:
            return False
        try:
            kind, value = request.events.get_nowait()
        except queue.Empty:
            return False
        self.home_request = None
        if kind == 'reply':
            context = getattr(request, 'issue_context', '')
            if isinstance(context, str) and context:
                self.home_issue_context = context
            try:
                action = None if getattr(request, 'gate_question', False) is True else parse_home_action(value)
                if action is None:
                    self.home_history.append(('assistant', sanitize(value)))
                    self.chat_error = ''
                else:
                    self._home_action(action)
            except (OSError, ValueError) as exc:
                self.chat_error = sanitize(str(exc))
                self.home_history.append(('system', self.chat_error))
        elif kind == 'issue_seeded':
            self.home_history.append(('system', sanitize(value)))
            self.chat_error = ''
        else:
            self.chat_error = sanitize(value)
        return True

    def _home_action(self, action):
        if self.state == 'running' or (getattr(self, 'proc', None) and self.proc.poll() is None):
            raise ValueError('A workflow is already active; the homepage action was not executed.')
        root = _project_root()
        name = action['uncle_action']
        if name == 'github_issue':
            if action['start']:
                self.workflow_idx = 1
                self.issue_mode = action.get('issue_mode', '')
                self.state = 'issue'
                self.input_buf = action['issue']
                self.issue = action['issue']
                self.sel = 0
                self.notice = ''
                self._run()
            else:
                if os.path.lexists(os.path.join(root, 'CHANGE_REQUEST.md')):
                    raise ValueError('CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.')
                env = os.environ.copy()
                env['UNCLE_PROJECT_ROOT'] = root
                self.home_request = IssueSeedRequest(
                    ['bash', os.path.join(ROOT, 'scripts', 'from-issue.sh'), action['issue'], '--change', '--seed-only'],
                    root, env)
                self.home_history.append(('system', 'Importing the GitHub issue into CHANGE_REQUEST.md…'))
        else:
            kind = 'app' if name.endswith('_app') else 'change'
            filename = 'REQUIREMENTS.md' if kind == 'app' else 'CHANGE_REQUEST.md'
            if name.startswith('create_'):
                if os.path.lexists(os.path.join(root, filename)):
                    raise ValueError(filename + ' already exists. Run it or choose a new project; it was not overwritten.')
                draft = Conversation(root)
                draft.kind = kind
                draft.preview = sanitize(action['document'])
                draft.commit()
                self.new_workflow_pending = True
                self.chat.kind, self.chat.preview, self.chat.seed = kind, draft.preview, draft.seed
                self.home_history.append(('system', 'Created ' + filename + ' from this conversation.'))
                start = action['start']
            else:
                # Use the same restricted regular-file reader as explicit attachments.
                if not self.chat.refs.read(filename).strip():
                    raise ValueError(filename + ' is empty.')
                start = True
            if start:
                self.workflow_idx = 0 if kind == 'app' else 2
                self._run()
                self.home_history.append(('system', 'Started the ' + kind + ' workflow using ' + filename + '.'))
        self.chat_error = ''

    # ---- supervision ----
    def _supervision_items(self):
        config = supervision_lib.load_config(CONFIG_PATH)
        rows = []
        for key, _kind, default in supervision_lib.CONTROLS:
            stored = self.supervision.get(key, "")
            shown = stored if stored else "%s  (default)" % supervision_lib.format_value(key, default)
            rows.append("%s  %s" % (key.ljust(26), shown))
        if config.errors:
            rows.append("! " + config.disabled_reason)
        return rows

    def _supervision_desc(self):
        keys = [key for key, _, _ in supervision_lib.CONTROLS]
        if 0 <= self.config_sel < len(keys):
            return SUPERVISION_DESC.get(keys[self.config_sel], "") + " Enter edits; an empty value restores the default."
        return "Fix the invalid value in .uncle/config; corrections stay disabled until every supervision key parses."

    def _supervision_enter(self):
        keys = [key for key, _, _ in supervision_lib.CONTROLS]
        if not 0 <= self.config_sel < len(keys):
            return
        key = keys[self.config_sel]
        if supervision_lib.KINDS[key] == "bool":
            current = self.supervision.get(key, supervision_lib.format_value(key, supervision_lib.DEFAULTS[key]))
            self._set_field("!supervision", key, "false" if current == "true" else "true")
            return
        self._open_picker(key, "!supervision")

    def _supervision_start(self, env):
        """Host the controller for this run; nothing is created when supervision is off."""
        previous = getattr(self, "supervision_host", None)
        if previous is not None:
            previous.close()
        self.supervision_host = None
        config = supervision_lib.load_config(CONFIG_PATH)
        if not config.enabled:
            return
        env["UNCLE_SUPERVISION_HOST"] = "tui"
        try:
            self.supervision_host = TuiSupervisionHost(self, config)
        except (OSError, ValueError) as exc:
            self._ensure_chat()
            self.home_history.append(("supervisor", "Supervision unavailable: " + sanitize(str(exc))))

    def poll_supervision(self):
        host = getattr(self, "supervision_host", None)
        if host is None:
            return False
        host.controller.gate(bool(self.prompt_kind))
        try:
            changed = host.controller.tick()
        except (OSError, ValueError) as exc:
            self.home_history.append(("supervisor", "Supervision error: " + sanitize(str(exc))))
            return True
        if getattr(self, "supervision_retry_pending", False):
            # Deferred out of the controller's call stack: the old owner
            # finishes its records and releases before the relaunch constructs
            # the next one over the same journal.
            self.supervision_retry_pending = False
            if not (self.proc and self.proc.poll() is None) and getattr(self, "triage_request", None) is None:
                self.home_history.append(("supervisor", "Relaunching the workflow to apply the retained correction."))
                self._run()
            return True
        return changed

    def _supervision_retry(self):
        """A permitted retry is the ordinary start: the driver re-verifies every approval itself."""
        if self.proc and self.proc.poll() is None:
            return
        if getattr(self, "triage_request", None) is not None:
            return
        self.supervision_retry_pending = True

    # ---- triage ----
    #
    # A stage failure writes .uncle/workflow/TRIAGE.md (the driver's EXIT hook)
    # and the TUI opens a chat with the triage master seeded with it. At any
    # other stop the same chat opens on request. The master runs in a sandbox
    # mirror of the project; the guard around each turn is what decides what
    # reaches the live tree, and only a proposal the operator selected with
    # /do N can reach it at all. Resume is the ordinary driver launch.
    def _triage_init(self):
        if not hasattr(self, 'triage_history'):
            self.triage_history = []
            self.triage_request = None
            self.triage_pending = None
            self.triage_turn = 0
            self.triage_tainted = ''
            self.triage_proposals = []
            self.triage_classification = ''
            self.triage_offer_resume = False
            self.triage_composer = ''
            self.triage_error = ''
            self.triage_return = 'chat'
            self.triage_scroll = 0

    def _workflow_dir(self):
        return os.path.join(_project_root(), '.uncle', 'workflow')

    def _maybe_auto_triage(self):
        """Open triage on a failure exit; never on a decline, cancel, or human stop."""
        code = getattr(self, 'workflow_exit_code', 0)
        if code in TRIAGE_CLEAN_EXITS or getattr(self, 'state', '') == 'quit':
            return
        wf = self._workflow_dir()
        try:
            with open(os.path.join(wf, 'stop-reason'), encoding='utf-8') as fh:
                if fh.readline().strip() == 'human':
                    return
        except OSError:
            pass
        try:
            written = os.path.getmtime(os.path.join(wf, 'TRIAGE.md'))
        except OSError:
            return
        if written < int(getattr(self, 'workflow_launch_time', 0)):
            return
        self.open_triage(auto=True)

    def open_triage(self, auto=False):
        self._triage_init()
        if self.state != 'triage':
            self.triage_return = self.state if self.state in ('running', 'chat', 'menu') else 'chat'
        self._ensure_chat()
        self.recovery_active = True
        self.chat_focus = 'chat'
        self.home_menu_open = False
        self.home_history.append(('system', 'Recovery: ask about the failure, /do N to apply a proposal, or /resume to continue.'))
        self.triage_error = ''
        # The first open, and every failure exit after a resume, gets one
        # diagnosis turn on the bundle the driver just wrote. An open on
        # request with a transcript already there shows the transcript.
        if self.triage_request is None and (auto or not self.triage_history):
            try:
                self._triage_turn('diagnosis')
            except (OSError, ValueError) as exc:
                self.triage_error = sanitize(str(exc))
                self.chat_error = self.triage_error

    def _triage_runner(self):
        return self.stage_runner('triage'), self.stage_model('triage'), self.stage_effort('triage')

    def _triage_guard(self, *args):
        result = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'lib', 'triage_guard.py')] + list(args),
                                cwd=_project_root(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise ValueError('Triage guard failed: ' + sanitize(result.stderr.strip()[-400:] or 'status %d' % result.returncode))
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise ValueError('Triage guard returned no summary.')

    def _triage_turn(self, mode, proposal=None, followup=''):
        self._triage_init()
        if self.triage_request is not None:
            raise ValueError('A triage turn is still running. Wait for it or use /clear to cancel.')
        if self.triage_tainted:
            raise ValueError(self.triage_tainted)
        runner, model, effort = self._triage_runner()
        if not runner:
            raise ValueError('Choose a runner in Configure first')
        root = _project_root()
        wf = self._workflow_dir()
        bundle_path = os.path.join(wf, 'TRIAGE.md')
        if not self.triage_history:
            # The first turn rebuilds the bundle from the tree: on request at a
            # gate there may be none yet, and a stale one describes another stop.
            env = dict(os.environ, UNCLE_STATUS_STAGE=getattr(self, 'status_stage', '') or '')
            subprocess.run(['bash', os.path.join(ROOT, 'scripts', 'lib', 'triage.sh'), '--write', '--state-dir', wf],
                           cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with open(bundle_path, encoding='utf-8', errors='replace') as fh:
                bundle = fh.read()
        except OSError:
            bundle = 'MISSING: ' + bundle_path
        template_path = os.path.join(root, 'prompts', 'triage.md')
        if not os.path.isfile(template_path):
            template_path = os.path.join(ROOT, 'prompts', 'triage.md')
        with open(template_path, encoding='utf-8') as fh:
            template = fh.read()
        turn = self.triage_turn + 1
        info = self._triage_guard('begin', '--state-dir', wf, '--project', root, '--root', ROOT,
                                  '--turn', str(turn), '--mode', mode)
        tail = '\n'.join(list(getattr(self, 'output', []))[-80:] + ([self.prompt_text] if self.prompt_kind else []))
        prompt = triage_prompt(template, bundle, self.triage_history, mode, proposal, followup, tail[-16384:])
        tools = EXECUTE_TOOLS if mode == 'execute' else DIAGNOSIS_TOOLS
        command = [runner_command(runner, AGENT)] + triage_runner_flags(effort, model, tools)
        env = triage_scrub_env(os.environ)
        env['UNCLE_CONFIG'] = str(CONFIG_PATH)
        if runner == 'self-hosted':
            values = home_settings(CONFIG_PATH, 'triage')
            for field in ('model', 'base_url', 'api_key'):
                env['UNCLE_SELF_HOSTED_' + field.upper()] = values[field]
        if runner == 'cline':
            env['UNCLE_CLINE_EFFORT'] = effort
            if model:
                env['UNCLE_CLINE_MODEL'] = model
        if followup:
            self.triage_history.append(('operator', sanitize(followup)))
        elif mode == 'execute':
            self.triage_history.append(('operator', '/do %d — %s' % (proposal[0], sanitize(proposal[1]))))
        self.triage_turn = turn
        self.triage_proposals = []
        self.triage_pending = {'mode': mode, 'proposal': proposal, 'digest': info['digest'], 'turn': turn}
        self.triage_request = TriageRequest(command, prompt, env, info['sandbox'],
                                            os.path.join(wf, 'logs', 'triage-%d.jsonl' % turn))

    def _triage_do(self, number):
        try:
            number = int(str(number).strip())
        except ValueError:
            raise ValueError('Usage: /do N, where N is a proposal number.')
        chosen = [p for p in self.triage_proposals if p[0] == number]
        if not chosen:
            raise ValueError('No proposal %d is selectable. Open triage and read the current reply.' % number)
        self._triage_turn('execute', proposal=chosen[0])

    def poll_triage(self):
        request = getattr(self, 'triage_request', None)
        if request is None:
            return False
        try:
            kind, value = request.events.get_nowait()
        except queue.Empty:
            return False
        self.triage_request = None
        pending = self.triage_pending or {}
        self.triage_pending = None
        # The guard runs whatever the turn's outcome: a runner that crashed
        # may still have written into the sandbox or reached the live tree.
        try:
            summary = self._triage_guard('end', '--state-dir', self._workflow_dir(), '--project', _project_root(),
                                         '--root', ROOT, '--turn', str(pending.get('turn', self.triage_turn)),
                                         '--mode', pending.get('mode', 'diagnosis'), '--digest', pending.get('digest', ''),
                                         '--proposal', ('Proposal %d: %s' % pending['proposal']) if pending.get('proposal') else '')
        except (OSError, ValueError) as exc:
            summary = {'applied': [], 'refused': [], 'failed': [], 'no_edit': False, 'tainted': True,
                       'messages': [str(exc)]}
        if kind == 'reply':
            text = sanitize(value)
            self.triage_history.append(('master', text))
            self.triage_error = ''
            if pending.get('mode') == 'execute':
                self.triage_offer_resume = True
            else:
                parsed = parse_triage_reply(text)
                if parsed is None:
                    self.triage_proposals = []
                    self.triage_history.append(('system', 'The reply does not follow the triage contract '
                                                          '(Classification: and Proposal N: lines); nothing is selectable.'))
                else:
                    self.triage_classification = parsed['classification']
                    self.triage_proposals = parsed['proposals']
                    self.triage_offer_resume = parsed['offer_resume']
        else:
            self.triage_proposals = []
            self.triage_error = sanitize(str(value))
            self.triage_history.append(('system', self.triage_error))
        notes = []
        if summary.get('applied'):
            notes.append('Applied: ' + ', '.join(summary['applied']))
        if summary.get('refused'):
            notes.append('Refused and reverted: ' + ', '.join(summary['refused']))
        if summary.get('failed'):
            notes.append('Not applied: ' + ', '.join(summary['failed']))
        if summary.get('no_edit') and pending.get('mode') == 'execute':
            notes.append('No files changed.')
        notes.extend(summary.get('messages', []))
        if summary.get('tainted'):
            self.triage_tainted = 'Resume refused: ' + ' '.join(summary.get('messages') or ['the guard could not verify the tree.'])
        if notes:
            self.triage_history.append(('system', sanitize(' '.join(notes))))
        if getattr(self, 'recovery_active', False):
            self.chat_error = self.triage_error
        return True

    def triage_resume(self):
        """Relaunch the driver from its recorded state: the ordinary start, no shortcut."""
        self._triage_init()
        if self.triage_request is not None:
            raise ValueError('A triage turn is still running. Wait for it before resuming.')
        if self.proc and self.proc.poll() is None:
            raise ValueError('The workflow is still running; answer its prompt.')
        if self.triage_tainted:
            raise ValueError(self.triage_tainted)
        if getattr(self, 'workflow_idx', None) is None:
            raise ValueError('No workflow has run in this session; start one from the menu.')
        self.triage_history.append(('system', 'Resuming the workflow from its recorded state.'))
        self._run()
        if self.state != 'running':
            raise ValueError(self.chat_error or 'The workflow did not start.')

    def _triage_command(self, text):
        if not text:
            return
        try:
            if text.startswith('/'):
                parts = text.split(maxsplit=1)
                command = parts[0].lower()
                argument = parts[1].strip() if len(parts) > 1 else ''
                if command == '/do':
                    self._triage_do(argument)
                elif command in ('/resume', '/r'):
                    self.triage_resume()
                elif command == '/clear':
                    if self.triage_request is not None:
                        self.triage_request.cancel()
                    self.triage_error = ''
                elif command == '/quit':
                    self._quit()
                elif command == '/triage':
                    pass
                else:
                    raise ValueError('Commands: /do N  /resume  /clear  /quit')
            else:
                self._triage_turn('diagnosis', followup=text)
            if self.state == 'triage':
                self.triage_error = ''
        except (OSError, ValueError) as exc:
            self.triage_error = sanitize(str(exc))

    def _triage_key(self, k):
        self._triage_init()
        if k == 3:
            self._quit()
            return
        if k == 27:
            if self.triage_composer:
                self.triage_composer = ''
                return
            # Esc leaves the turn running if one is; the gate stays blocked
            # until it ends. The pending prompt is untouched either way.
            self.state = self.triage_return
            if self.state == 'running' and not self.proc:
                self.state = 'chat'
            if self.state == 'running':
                self.chat_focus = 'gate' if self.prompt_kind else 'chat'
            elif self.state in ('chat', 'menu'):
                self._ensure_chat()
                self.chat_focus = 'chat' if self.state == 'chat' else 'menu'
            return
        if k in (curses.KEY_UP, curses.KEY_DOWN):
            self.triage_scroll = max(0, self.triage_scroll + (1 if k == curses.KEY_UP else -1))
            return
        # Bare keys select only what is on offer; otherwise they are text, so
        # a follow-up question can start with "r" or a digit. /do N and
        # /resume always work from the composer.
        if not self.triage_composer:
            if k in (ord('1'), ord('2'), ord('3')) and any(n == k - ord('0') for n, _ in self.triage_proposals):
                self._triage_command('/do %d' % (k - ord('0')))
                return
            if k in (ord('r'), ord('R')) and self.triage_offer_resume:
                self._triage_command('/resume')
                return
        if k in (10, 13):
            text = self.triage_composer.strip()
            self.triage_composer = ''
            self._triage_command(text)
            return
        if k in (curses.KEY_BACKSPACE, 127, 8):
            self.triage_composer = self.triage_composer[:-1]
        elif 32 <= k <= 0x10ffff and k < curses.KEY_MIN:
            if len(self.triage_composer.encode('utf-8')) < 60000:
                self.triage_composer += chr(k)

    def _draw_triage(self):
        self._triage_init()
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()

        def put(y, x, value, width, attr=curses.A_NORMAL):
            if 0 <= y < h and 0 <= x < w and width > 0:
                try:
                    self.stdscr.addnstr(y, x, value, min(width, w - x - 1), attr)
                except curses.error:
                    pass

        runner, _, _ = self._triage_runner()
        status = 'triage | %s | turn %d' % (runner or 'no runner', self.triage_turn)
        if self.triage_request is not None:
            status += ' | running…'
        if self.triage_tainted:
            status += ' | TAINTED'
        put(0, 0, 'Triage | ' + status, w, curses.A_BOLD)
        put(1, 0, 'Classification: ' + (self.triage_classification or '—'), w)
        lines = []
        for role, text in self.triage_history:
            for i, line in enumerate(str(text).splitlines() or ['']):
                lines.extend(textwrap.wrap(('%s: ' % role if i == 0 else '') + line, max(1, w - 2)) or [''])
            lines.append('')
        bottom = h - 5
        rows = max(0, bottom - 3)
        end = max(0, len(lines) - self.triage_scroll)
        for i, line in enumerate(lines[max(0, end - rows):end]):
            put(3 + i, 0, line, w)
        if self.triage_proposals:
            offer = 'Select: ' + '  '.join('[%d] %s' % (n, body[:max(1, w // 3)]) for n, body in self.triage_proposals)
        else:
            offer = 'No proposal is selectable.'
        if self.triage_offer_resume:
            offer += '  [r] resume'
        put(h - 4, 0, offer, w)
        put(h - 3, 0, self.triage_error, w)
        put(h - 2, 0, 'Triage> ' + self.triage_composer[-max(1, w - 10):], w)
        put(h - 1, 0, '1-3 select proposal | r resume | Esc back | /do N /resume /clear | text = follow-up question', w)
        self.stdscr.refresh()

    def chat_display(self):
        recovery = getattr(self, 'triage_history', [])
        seen = getattr(self, '_recovery_displayed', 0)
        for role, text in recovery[seen:]:
            self.home_history.append(('Recovery' if role == 'master' else 'User' if role == 'operator' else 'System', text))
        self._recovery_displayed = len(recovery)
        history = getattr(self, 'home_history', [])
        return [str(role).capitalize() + ': ' + text for role, text in history] if history else list(self.chat.messages)

    def start_chat_workflow(self):
        if self.state == 'running' or (self.proc and self.proc.poll() is None):
            self.chat_error = 'A workflow is already active'
            return
        try:
            self.chat.commit()
            self.workflow_idx = 0 if self.chat.kind == 'app' else 2
            self._run()
            self.chat_error = ''
        except (OSError, ValueError) as exc:
            self.state = 'chat'
            self.chat_error = sanitize(str(exc))
            # start_workflow allocated this channel before a failed Popen.
            path = getattr(self, 'status_path', None)
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                self.status_path = None

    def _issue_suggestions(self, query):
        self.issue_matches = self.issue_picker.matches(query)
        self.chat_choices = [f"#{item['number']} {item['title']}" for item in self.issue_matches]
        self.chat_pick = 0

    def poll_issue_picker(self):
        picker = getattr(self, 'issue_picker', None)
        if picker is None or not picker.poll():
            return False
        if self.chat_picker and getattr(self, 'chat_picker_kind', 'file') == 'issue':
            self._issue_suggestions(self.chat_composer[self.chat_ref_start + 1:])
        return True

    def _chat_suggestions(self):
        match = re.search(r'@(?:"([^"]*)|([^@\s"]*))$', self.chat_composer)
        issue = re.search(r'(?<!\S)#([^\s#]*)$', self.chat_composer) if match is None else None
        if issue:
            refresh = not self.chat_picker or getattr(self, 'chat_picker_kind', 'file') != 'issue'
            self.chat_picker = True
            self.chat_picker_kind = 'issue'
            self.chat_ref_start = issue.start()
            if not hasattr(self, 'issue_picker'):
                self.issue_picker = IssuePicker(_project_root())
            self.issue_picker.load(refresh=refresh)
            self._issue_suggestions(issue[1])
            return
        self.chat_picker_kind = 'file'
        self.chat_picker = bool(match)
        self.chat_ref_start = match.start() if match else len(self.chat_composer)
        self.chat_choices = self.chat.refs.browse(match.group(1) if match.group(1) is not None else match.group(2)) if match else []
        self.chat_pick = 0

    def _complete_chat_file(self):
        if getattr(self, 'chat_picker_kind', 'file') == 'issue':
            if not self.chat_choices:
                self.chat_error = self.issue_picker.message or 'No matching open issues.'
                return
            item = self.issue_matches[self.chat_pick]
            self.chat_composer = self.chat_composer[:self.chat_ref_start] + '#' + str(item['number']) + ' '
            self.chat_choices = []
            self.chat_picker = False
            self.chat_error = ''
            return
        if not self.chat_choices:
            self.chat_error = 'No matching files. Keep typing or press Esc to close.'
            return
        name = self.chat_choices[self.chat_pick]
        if name.endswith('/'):
            choices = self.chat.refs.browse(name)
            reference = '@"' + name if any(c.isspace() for c in name) else '@' + name
            self.chat_composer = self.chat_composer[:self.chat_ref_start] + reference
            self.chat_choices = choices
            self.chat_pick = 0
        else:
            reference = self.chat.refs.reference(name)
            self.chat_composer = self.chat_composer[:self.chat_ref_start] + reference + ' '
            self.chat_choices = []
            self.chat_picker = False
        self.chat_error = ''

    def _chat_key(self, k):
        if k == 27 and getattr(self, 'recovery_active', False):
            self.recovery_active = False
            self.chat_focus = 'gate' if self.state == 'running' and self.prompt_kind else 'chat'
            self.chat_error = ''
            return True
        if k == 27 and self.state == 'running' and getattr(self, 'workflow_exit_reported', False):
            self.state = 'menu'
            self.recovery_active = False
            self.chat_focus = 'chat'
            self.chat_error = ''
            return True
        if self.state == 'running' and self.chat_focus == 'menu':
            self.chat_focus = 'gate'
        if k == 3:
            self._quit()
            return True
        if k == 9:
            other = 'menu' if self.state == 'menu' else 'gate'
            self.chat_focus = other if self.chat_focus == 'chat' else 'chat'
            return True
        if self.state == 'menu' and self.chat_focus == 'menu':
            return False
        if self.chat_focus == 'gate' and self.state == 'running':
            if k in (curses.KEY_UP, curses.KEY_DOWN):
                self.prompt_scroll = max(0, getattr(self, 'prompt_scroll', 0) +
                                         (1 if k == curses.KEY_DOWN else -1))
                return True
            return False  # Gate keys use the same approval handler as /approve.
        if not self.chat_edit and not (self.chat_picker and getattr(self, 'chat_picker_kind', 'file') == 'issue') and self._chat_command(k):
            return True
        try:
            if k == 27:
                if self.chat_picker or self.chat_choices:
                    self.chat_picker = False
                    self.chat_choices = []
                elif self.chat_edit:
                    self.chat.preview = sanitize(self.chat_composer)
                    self.chat_composer = ''
                    self.chat_edit = False
                elif self.state in ('chat', 'menu'):
                    self.state = 'menu'
                    self.chat_focus = 'menu'
                    self.sel = 0
                return True
            if k == 16 and not self.chat_edit:  # Ctrl-P
                self.chat_picker = True
                self.chat_ref_start = len(self.chat_composer)
                self.chat_picker_kind = 'file'
                self.chat_choices = self.chat.refs.browse('')
                self.chat_pick = 0
                return True
            if self.chat_choices and k in (curses.KEY_UP, curses.KEY_DOWN):
                self.chat_pick = (self.chat_pick + (1 if k == curses.KEY_DOWN else -1)) % len(self.chat_choices)
                return True
            if k in (10, 13):
                if self.chat_choices:
                    self._complete_chat_file()
                elif self.chat_picker:
                    self.chat_error = (self.issue_picker.message or 'No matching open issues.') if getattr(self, 'chat_picker_kind', 'file') == 'issue' else 'No matching files. Keep typing or press Esc to close.'
                elif self.chat_edit:
                    self.chat_composer += '\n'
                else:
                    self.send_home_chat(self.chat_composer)
                    self.chat_composer = ''
                    self.chat_error = ''
                return True
            if k == curses.KEY_F2:
                if self.chat.seed is not None:
                    raise ValueError('The committed seed fixes the workflow type')
                self.chat.kind = 'change' if self.chat.kind == 'app' else 'app'
                return True
            if k == curses.KEY_F3:
                self.chat.payload()
                raise ValueError('Generate brief unavailable: native tool isolation is not verified; Configure/retry')
            if k == curses.KEY_F4:
                if self.chat.seed is not None:
                    raise ValueError('Committed seed cannot be edited here')
                self.chat_edit = True
                self.chat_composer = self.chat.preview
                return True
            if k == curses.KEY_F5:
                if self.chat_edit:
                    self.chat.preview = sanitize(self.chat_composer)
                    self.chat_edit = False
                    self.chat_composer = ''
                self.start_chat_workflow()
                return True
            if k in (curses.KEY_F6, curses.KEY_F7):
                raise ValueError('No resolved active model; Query/Fork unavailable')
            if k == curses.KEY_F8 and self.state in ('chat', 'menu'):
                self.state = 'config'
                self.config_sel = 0
                return True
            if k in (curses.KEY_BACKSPACE, 127, 8):
                self.chat_composer = self.chat_composer[:-1]
            elif 32 <= k <= 0x10ffff and k < curses.KEY_MIN:
                if len(self.chat_composer.encode('utf-8')) >= 1024 * 1024:
                    raise ValueError('Transcript exceeds 1 MiB limit')
                self.chat_composer += chr(k)
            if not self.chat_edit:
                if self.chat_picker and getattr(self, 'chat_picker_kind', 'file') == 'file' and not self.chat_composer[self.chat_ref_start:].startswith('@'):
                    self.chat_choices = self.chat.refs.browse(self.chat_composer[self.chat_ref_start:])
                    self.chat_pick = 0
                else:
                    self._chat_suggestions()
        except (OSError, ValueError) as exc:
            self.chat_error = sanitize(str(exc))
        return True

    def _draw_file_picker(self, composer_row, left, width, top=0):
        """Show a scrolling file list immediately above the message composer."""
        slash = self._slash_choices() if not self.chat_edit else []
        if (not self.chat_picker and not slash) or self.chat_focus != 'chat':
            return
        h, w = self.stdscr.getmaxyx()
        width = min(width, w - left - 1)
        room = min(8, composer_row - top)
        if room < 2 or width < 4:
            return
        choices = slash or self.chat_choices
        pick = getattr(self, 'slash_pick', 0) % len(slash) if slash else self.chat_pick
        slots = room - 1
        start = max(0, pick - slots + 1)
        entries = choices[start:start + slots]
        is_issue = getattr(self, 'chat_picker_kind', 'file') == 'issue'
        rows = ['Commands  ↑↓ select · Enter run' if slash else 'Open issues  ↑↓ select · Tab/Enter insert · Esc close' if is_issue else 'Files  ↑↓ select · Tab complete · Enter attach · Esc close']
        rows += [('› ' if start + i == pick else '  ') + name
                 for i, name in enumerate(entries)] if entries else [(self.issue_picker.message or 'No matching open issues.') if is_issue else 'No matching files']
        y = composer_row - len(rows)
        for i, line in enumerate(rows):
            attr = curses.A_REVERSE if i > 0 and entries and start + i - 1 == pick else curses.A_NORMAL
            try:
                if 0 <= y + i < h:
                    self.stdscr.addnstr(y + i, left, line[:width].ljust(width), width, attr)
            except curses.error:
                pass

    def _draw_chat(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()

        def put(y, x, value, width):
            if 0 <= y < h and 0 <= x < w and width > 0:
                try:
                    self.stdscr.addnstr(y, x, value, min(width, w - x - 1))
                except curses.error:
                    pass

        put(0, 0, ('Uncle | Chat' if self.state == 'menu' else 'Chat') + ' | %s | focus: %s' % (self.chat.kind, self.chat_focus), w)
        put(1, 0, 'F2 Type F3 Brief F4 Edit F5 Start', w)
        put(2, 0, 'F6 Query F7 Fork F8 Config ^P Files', w)
        bottom = h - 4
        left = w // 2 if w >= 100 and self.state == 'running' else 0
        top = 3
        if self.state == 'menu':
            items = self.menu_items()
            menu_width = min(36, w // 3) if w >= 80 else w
            for i, label in enumerate(items):
                marker = '> ' if i == self.sel and self.chat_focus == 'menu' else '  '
                put(top + i, 0, marker + label, menu_width)
            if w >= 80:
                left = menu_width + 2
            else:
                top += len(items) + 1
        if self.state == 'running':
            rows = max(1, bottom - top) if left else max(1, (bottom - top) // 2)
            tail = self.output[-rows:]
            if getattr(self, 'partial', '').strip():
                tail = (tail + [self.partial.rstrip()])[-rows:]
            for i, line in enumerate(tail):
                put(top + i, 0, line, left or w)
            if not left:
                top += rows
        content = self.chat_display()
        if self.chat.preview:
            content += ['Preview:', self.chat.preview]
        if self.chat_choices:
            content += ['Files: ' + self.chat_choices[self.chat_pick]]
        wrapped = []
        # Bound viewport wrapping; Conversation retains the complete transcript.
        visible = '\n'.join(content)[-max(1, h * w * 2):]
        for line in visible.splitlines():
            wrapped.extend(textwrap.wrap(line, max(1, w - left - 2)) or [''])
        rows = max(0, bottom - top)
        for i, line in enumerate(wrapped[-rows:] if rows else []):
            put(top + i, left, line, w - left)
        put(h - 4, 0, self.chat_error, w)
        composer = sanitize(self.chat_composer).replace('\n', ' / ')
        put(h - 3, 0, ('Edit> ' if self.chat_edit else 'Message> ') + composer[-max(1, w - 12):], w)
        gate_lines = []
        for line in self.prompt_text.splitlines():
            gate_lines.extend(textwrap.wrap(line, max(1, w - 1)) or [''])
        offset = min(getattr(self, 'prompt_scroll', 0), max(0, len(gate_lines) - 1))
        gate = gate_lines[offset] if self.prompt_kind and gate_lines else 'No gate pending'
        if self.chat_focus == 'gate' and self.prompt_kind == 'input':
            gate = 'Answer> ' + sanitize(self.prompt_buf)[-max(1, w - 10):]
        put(h - 2, 0, gate, w)
        controls = {'confirm': 'y/n/v', 'audit': 's/r/n/v', 'enter': 'Enter',
                    'input': 'type, Enter', 'support': 's/Enter'}
        put(h - 1, 0, ('Tab menu/chat | Enter select/send' if self.state == 'menu' else 'Tab chat/gate | ' + controls.get(self.prompt_kind, 'Enter send | Esc back')), w)
        self._draw_file_picker(h - 3, 0, w)
        self.stdscr.refresh()

    # ---- drawing ----
    def draw(self):
        if self.state == 'triage':
            self._draw_triage()
            return
        if self.state == 'running':
            self._ensure_chat()
        if self.state == 'menu':
            self._ensure_chat()
            h, w = self.stdscr.getmaxyx()
            self.stdscr.erase()
            self._draw_homepage(h, w)
            self.stdscr.refresh()
            return
        if getattr(self, 'chat_open', False) and self.state == 'chat':
            self._draw_chat()
            return
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()
        if self.state in ("running", "viewer"):
            panel = min(34, w // 3) if w >= 60 else 0
            chat_height = 0
            chat_width = 0
            if self.state == 'running' and getattr(self, 'chat_open', False):
                # Left-justified, as wide as the output, and a row taller per
                # wrap — every row it takes comes from the build output.
                chat_width = w - panel
                text = sanitize(self.chat_composer).replace('\n', ' / ').expandtabs(4).lstrip()
                extra = min(len(self._wrap_input(text, max(8, chat_width - 2))), 6) - 1 if text else 0
                chat_height = min(6 + extra, max(0, h - 3))
            # The chat panel sits at the very bottom, in the row the old
            # status bar used; the output takes everything above it.
            self._draw_running(h - chat_height, w - panel)
            if chat_height:
                self._draw_chat_panel(h - chat_height, h, 0, chat_width)
            if panel:
                self._draw_session_stats(h, w, panel)
        elif self.state == "notice":
            self._draw_notice(h, w)
        else:
            self._draw_prompt(h, w)
            if self.state == 'menu':
                logo_fits = h >= len(LOGO) + 1 and w >= LOGO_W + 22
                left = LOGO_W + 2 if logo_fits else 0
                top = len(self.menu_items()) + (1 if logo_fits else 3)
                self._draw_chat_panel(top, h - 1, left, w - left)
        self.stdscr.refresh()
        self._paint_support_link()

    def _homepage_key(self, k):
        if k == 16:  # Ctrl-P: the homepage command menu.
            self.home_menu_open = not getattr(self, 'home_menu_open', False)
            self.chat_focus = 'menu' if self.home_menu_open else 'chat'
            self.sel = 0
            return True
        if k == 9:
            self.home_menu_open = self.chat_focus == 'chat'
            self.chat_focus = 'menu' if self.home_menu_open else 'chat'
            return True
        if k == 27 and getattr(self, 'home_menu_open', False):
            self.home_menu_open = False
            self.chat_focus = 'chat'
            return True
        if getattr(self, 'home_menu_open', False):
            if k in (10, 13):
                self.home_menu_open = False
                self._confirm()
                self.chat_focus = 'chat'
                return True
            return False
        return False

    def _slash_choices(self):
        commands = ['/configure', '/settings', '/file', '/quit', '/issue', '/requirements', '/change', '/approve', '/clear', '/triage', '/do', '/resume']
        text = self.chat_composer.lower()
        return [command for command in commands if command.startswith(text)] if text.startswith('/') and ' ' not in text else []

    def _chat_command(self, k):
        choices = self._slash_choices()
        if choices and k in (curses.KEY_UP, curses.KEY_DOWN):
            self.slash_pick = (getattr(self, 'slash_pick', 0) + (1 if k == curses.KEY_DOWN else -1)) % len(choices)
            return True
        if choices and k in (10, 13) and self.chat_composer.lower() not in choices:
            self.chat_composer = choices[getattr(self, 'slash_pick', 0) % len(choices)]
            if self.chat_composer == '/issue':
                self.chat_composer += ' '
                return True
        if k not in (10, 13):
            self.slash_pick = 0
        if k in (10, 13) and self.chat_composer.startswith('/'):
            parts = self.chat_composer.strip().split(maxsplit=1)
            command = parts[0].lower()
            argument = parts[1].strip() if len(parts) > 1 else ''
            commands = {'/new': 0, '/requirements': 0, '/issue': 1,
                        '/change': 2, '/configure': 3, '/settings': 3, '/quit': 4}
            if command in ('/new', '/requirements', '/change', '/issue') and (
                    self.state == 'running' or (self.proc and self.proc.poll() is None)):
                self.chat_error = 'A workflow is already active. Finish or stop it before starting another.'
                return True
            if argument and command not in ('/issue', '/do'):
                self.chat_error = command + ' does not take arguments'
                return True
            if command in ('/triage', '/do', '/resume'):
                self.chat_composer = ''
                self.chat_picker = False
                self.chat_choices = []
                self.chat_error = ''
                try:
                    if command == '/triage':
                        self.open_triage()
                    elif command == '/resume':
                        self.triage_resume()
                    else:
                        self._triage_init()
                        self._triage_do(argument)
                except (OSError, ValueError) as exc:
                    self.chat_error = sanitize(str(exc))
                return True
            if command == '/issue' and argument:
                if not self._valid_issue(argument.removeprefix('#')):
                    self.chat_error = 'Usage: /issue 123, #123, or https://github.com/owner/repo/issues/123'
                    return True
                self.issue = argument.lstrip('#')
                self.issue_mode = ''  # Existing automatic issue classification.
                self.workflow_idx = 1
                self.chat_composer = ''
                self.chat_error = ''
                self.chat_picker = False
                self.chat_choices = []
                self._run()
            elif command == '/approve':
                pending = (self.state == 'running'
                           and getattr(self, 'prompt_kind', '') == 'confirm'
                           and getattr(self, 'prompt_text', '').strip().lower().startswith(
                               ('ready to approve ', 'ready to acknowledge '))
                           and self.proc is not None and self.proc.poll() is None)
                if not pending:
                    self.chat_error = 'No stage approval is waiting. /approve works when an approval gate is ready.'
                    return True
                self.answer_prompt('y')
                self.chat_composer = ''
                self.chat_error = ''
                self.chat_picker = False
                self.chat_choices = []
            elif command in commands:
                self.chat_error = ''
                self.chat_picker = False
                self.chat_choices = []
                self.chat_composer = ''
                self.sel = commands[command]
                self.state = 'menu'
                self._confirm()
            elif command in ('/file', '/files'):
                self.chat_composer = ''
                self.chat_picker = True
                self.chat_ref_start = 0
                self.chat_picker_kind = 'file'
                self.chat_choices = self.chat.refs.browse('')
                self.chat_pick = 0
            elif command == '/clear':
                if getattr(self, 'triage_request', None):
                    self.triage_request.cancel()
                self.recovery_active = False
                self._recovery_displayed = len(getattr(self, 'triage_history', []))
                if self.home_request:
                    self.home_request.cancel()
                    self.home_request = None
                self.chat_picker = False
                self.home_history.clear()
                self.home_issue_context = ''
                self.chat.messages.clear()
                self.chat_composer = ''
                self.chat_error = ''
                self.chat_choices = []
            else:
                self.chat_error = 'Commands: /configure /settings /file /quit /issue # /requirements /change /approve /clear /triage /do N /resume'
            return True
        return False

    def _draw_homepage(self, h, w):
        """Centered, prompt-first landing screen; workflow rendering is separate."""
        color = getattr(self, 'color', {})
        items = self.menu_items()
        history = self.chat_display()
        if self.chat.preview:
            history += ['Preview: ', self.chat.preview]
        width = max(1, min(76, w - 4))
        left = max(0, (w - width) // 2)
        compact = h < len(LOGO) + 12
        footer_rows = 8 if compact else 12
        # The menu is a bar along the very top; Ctrl-P/Tab only change focus.
        focused = self.chat_focus == 'menu'
        bar = []
        x = 0
        bar_y = 0
        for i, label in enumerate(items):
            selected = focused and i == self.sel
            text = ('› ' if selected else '') + label
            if x:
                if x + 3 + len(text) > w - 1:
                    bar_y += 1
                    x = 0
                else:
                    text = '   ' + text
            bar.append((bar_y, x, text, selected))
            x += len(text)
        # The decorative logo yields its rows to the bar before the prompt does.
        logo_fits = w >= LOGO_W + 4 and h >= len(LOGO) + footer_rows + bar_y + 1
        logo = LOGO if logo_fits and not history else []
        body_rows = len(LOGO) if logo_fits else 0
        if h < 18:
            body_rows = 0
        top = max(bar_y + 1, (h - body_rows - footer_rows) // 2)
        logo_left = left + max(0, (width - LOGO_W) // 2)
        if logo:
            for i, line in enumerate(logo):
                try:
                    self.stdscr.addnstr(top + i, logo_left, line, LOGO_W, color.get('title', 0))
                except curses.error:
                    pass
        def put(y, text, attr=0, centered=False):
            if not 0 <= y < h:
                return
            text = text[:width]
            x = left + max(0, (width - len(text)) // 2) if centered else left
            try:
                self.stdscr.addnstr(y, x, text, min(width, max(0, w - x - 1)), attr)
            except curses.error:
                pass
        if history:
            lines = []
            for line in '\n'.join(history)[-max(1, width * body_rows * 2):].splitlines():
                lines.extend(textwrap.wrap(line, width) or [''])
            room = max(0, body_rows - 1)
            for i, line in enumerate(lines[-room:] if room else []):
                put(top + 1 + i, line, color.get('accent', 0))
        row = top + body_rows
        self._draw_chat_composer(row, h, w, left, width, compact)
        for y, x, text, selected in bar:
            try:
                self.stdscr.addnstr(y, x, text, min(len(text), max(0, w - x - 1)),
                                    color.get('sel', curses.A_REVERSE) if selected else color.get('accent', 0))
            except curses.error:
                pass


    @staticmethod
    def _wrap_input(text, width):
        # Wrap on words but keep every typed space: the cursor position is
        # derived from the wrapped text, so dropping whitespace stalls it.
        chunks, current = [], ''
        for word in text.split(' '):
            candidate = word if not current else current + ' ' + word
            while len(candidate) > width:
                if current:
                    chunks.append(current)
                    current, candidate = '', word
                else:
                    chunks.append(candidate[:width])
                    candidate = candidate[width:]
            current = candidate
        if text:
            chunks.append(current)
        return chunks

    def _draw_chat_composer(self, row, h, w, left, width, compact=True):
        """Shared homepage and build chat appearance."""
        first_row = row
        build = self.state == 'running'
        if build and compact:
            # No greeting on the build page; the build output gets the row.
            row -= 1
            greeting = False
        else:
            greeting = True
            if compact and h - row < 8:
                row -= 1  # Hide the greeting first on short terminals.
                greeting = False
        color = getattr(self, 'color', {})
        def put(y, text, attr=0, centered=False, right=False):
            if not first_row <= y < h:
                return
            text = text[:width]
            x = left + max(0, width - len(text)) if right else left + max(0, (width - len(text)) // 2) if centered else left
            try:
                self.stdscr.addnstr(y, x, text, min(width, max(0, w - x - 1)), attr)
            except curses.error:
                pass
        if greeting:
            put(row + (0 if compact else 1), 'What can uncle do for you?', color.get('title', 0) | curses.A_BOLD, True)
        put(row + (1 if compact else 3), ('/ commands   @ files   # issues   Ctrl-P menu  Tab to chat' if width >= 60 else '/ cmds  @ files  # issues  Ctrl-P menu  Tab chat' if width >= 52 else '/ cmds @ files Ctrl-P menu Tab chat' if width >= 34 else '@ files  Ctrl-P menu Tab chat' if width >= 28 else 'Ctrl-P menu'), color.get('muted', curses.A_DIM), not build)
        put(row + (2 if compact else 5), '─' * width, color.get('muted', curses.A_DIM))
        text = sanitize(self.chat_composer).replace('\n', ' / ').expandtabs(4).lstrip()
        placeholder = 'Ask about the failure · /do N · /resume' if getattr(self, 'recovery_active', False) else 'Talk to uncle while he builds' if self.state == 'running' else 'Describe an app or a change…'
        if self.state == 'running' and getattr(self, 'prompt_kind', '') and self.chat_focus == 'chat':
            placeholder = 'Ask a question · Tab returns to the pending dialog'
        composer_row = row + (3 if compact else 6)
        wrap_width = max(8, width - 2)
        # The composer grows as the input wraps; long pastes scroll to the tail.
        chunks = self._wrap_input(text, wrap_width)
        chunks = chunks[-max(1, min(6, h - composer_row - 3)):]
        extra = len(chunks) - 1 if text else 0
        if text:
            for i, chunk in enumerate(chunks):
                put(composer_row + i, ('› ' if i == 0 else '  ') + chunk, color.get('accent', 0))
        else:
            put(composer_row, '› ' + placeholder, color.get('muted', curses.A_DIM))
        put(composer_row, '›', color.get('warning', curses.A_BOLD))
        if self.chat_focus == 'chat' and (self.state != 'menu' or not getattr(self, 'home_menu_open', False)):
            cursor_y = composer_row + extra
            cursor_x = left + 2 + (len(chunks[-1]) if chunks else 0)
            if cursor_y < h and cursor_x < w - 1:
                try:
                    self.stdscr.addnstr(cursor_y, min(cursor_x, left + width - 1), ' ' if text else placeholder[0], 1,
                                       color.get('warning', 0) | curses.A_REVERSE)
                except curses.error:
                    pass
        put(composer_row + 1 + extra, '─' * width, color.get('muted', curses.A_DIM))
        model_label = 'Configure a model'
        if hasattr(self, 'stage_runners'):
            _, runner, model, effort = self.chat_model()
            model_label = (model or runner or model_label) + ' (' + effort + ')'
        stage_status = ''
        if build and getattr(self, 'status_stage', ''):
            stage_status = self.status_stage
            if getattr(self, 'status_stage_index', 0) and getattr(self, 'status_stage_total', 0):
                stage_status += ' (%d/%d)' % (self.status_stage_index, self.status_stage_total)
            stage_status += '  ·  '
        model_status = stage_status + model_label + ('  ·  Recovering…' if getattr(self, 'triage_request', None) else '  ·  Recovery ready' if getattr(self, 'recovery_active', False) else '  ·  Workflow stopped' if self.state == 'running' and getattr(self, 'workflow_exit_reported', False) else '  ·  Thinking…' if getattr(self, 'home_request', None) else '  ·  Chat ready')
        project = os.path.basename(_project_root()) or _project_root()
        try:
            with open(os.path.join(_project_root(), '.git', 'HEAD')) as source:
                head = source.read(256).strip()
            project += ' (' + (head.removeprefix('ref: refs/heads/') if head.startswith('ref: refs/heads/') else 'detached') + ')'
        except OSError:
            pass
        auto = getattr(self, 'misc', {}).get('auto_mode') == 'true'
        project_status = project + '  ·  ' + ('Auto mode on' if auto else 'Manual approvals')
        status_row = composer_row + extra + (2 if build or compact else 3)
        right_width = min(len(project_status), max(1, width - 18))
        put(status_row, model_status[:max(0, width - right_width - 2)], color.get('muted', curses.A_DIM))
        put(status_row, project_status[:right_width], color.get('good', 0) if auto else color.get('accent', 0), right=True)
        feedback_row = status_row + 1
        if self.chat_error:
            put(feedback_row, self.chat_error, color.get('warning', curses.A_BOLD))
        elif self.chat_choices:
            put(feedback_row, 'File: ' + self.chat_choices[self.chat_pick], color.get('accent', 0))
        elif self.chat_composer.startswith('/'):
            put(feedback_row, '/configure /settings /file /quit /issue # /requirements /change /approve /clear', color.get('muted', curses.A_DIM))

        self._draw_file_picker(composer_row, left, width)
    def _draw_chat_panel(self, top, bottom, left, width):
        """The chat composer below the content area, positioned by the caller."""
        if bottom - top < 2 or width < 4:
            return
        _, screen_width = self.stdscr.getmaxyx()
        self._draw_chat_composer(top, bottom, screen_width, left, width)

    def _build_messages(self):
        """Collect build output and chat in one chronological viewport."""
        output = list(self.output)
        chat = self.chat_display()
        previous_output, previous_chat = getattr(self, '_message_snapshot', ([], []))
        messages = getattr(self, '_message_stream', [])
        for kind, current, previous in (('build', output, previous_output), ('chat', chat, previous_chat)):
            common = 0
            for old, new in zip(previous, current):
                if old != new:
                    break
                common += 1
            if kind == 'chat' and common < len(previous):
                messages = [item for item in messages if not (item[0] == 'chat' and item[1] >= common)]
            if kind == 'build' and common < min(len(previous), len(current)):
                # The bounded output buffer drops its oldest lines periodically.
                overlap = min(len(previous), len(current))
                while overlap and previous[-overlap:] != current[:overlap]:
                    overlap -= 1
                common = overlap
            messages.extend((kind, i, line) for i, line in enumerate(current[common:], common))
        self._message_snapshot = (output, chat)
        self._message_stream = messages[-4000:]
        return [item[2] for item in self._message_stream]

    def _draw_running(self, h, w):
        if self.state == "viewer":
            self._draw_viewer(h, w)
            return
        tail = self._build_messages()
        if self.partial.strip() and not self.prompt_kind:
            tail.append(self.partial.rstrip())
        # The transcript uses every column before the sidebar, independently
        # of the centered composer's narrower width.
        screen_width = self.stdscr.getmaxyx()[1]
        message_width = max(1, min(w, screen_width - 1))
        wrapped = []
        for message in tail[-max(1, h * 2):]:
            for line in message.splitlines() or ['']:
                wrapped.extend(textwrap.wrap(line, message_width) or [''])
        for i, line in enumerate(wrapped[-max(0, h - 1):] if h > 1 else []):
            try:
                self.stdscr.addnstr(i, 0, line, message_width)
            except curses.error:
                pass
        if self.prompt_kind:
            self._draw_modal(h, w)

    def _restore_session_totals(self):
        stats = getattr(self, "session_stats", None)
        if stats is None:
            return
        path = os.path.join(_project_root(), ".uncle", "workflow", "session-totals.json")
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
        directory = os.path.join(_project_root(), ".uncle", "workflow", "metrics")
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
        # (value, estimated): reported dollars are authoritative; a token-price
        # estimate only fills the gap and stays labeled as one.
        if isinstance(event.get("total_cost_usd"), (int, float)):
            return event["total_cost_usd"], False
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
            estimate = self._estimate_cost(row).get("estimated_cost_usd")
        except (OSError, ValueError, TypeError, KeyError):
            estimate = None
        return (estimate, True) if estimate is not None else (None, False)

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
        def cost_subtotal(entries):
            # (value, estimated) pairs: a line that includes any estimate is
            # labeled "est" so reported dollars never blend invisibly with
            # projections.
            known = [value for value, _ in entries if isinstance(value, (int, float))]
            if not known:
                return dollars(None)
            text = dollars(sum(known))
            if any(estimated for value, estimated in entries if isinstance(value, (int, float))):
                text += " est"
            return text + (" (partial)" if len(known) < len(entries) else "")
        groups = {}
        for row in sorted(stats["records"], key=lambda r: r.get("started_at", 0)):
            stage = row.get("stage", "")
            group = groups.setdefault(stage, {"seconds": 0, "tokens": [], "costs": [], "attempts": 0, "started": float("inf")})
            group["started"] = min(group["started"], row.get("started_at", row.get("ended_at", 0) - row.get("elapsed_seconds", 0)))
            group["seconds"] += row.get("elapsed_seconds", 0)
            group["tokens"].append(self._token_total(row))
            cost = row.get("reported_cost_usd")
            # A runner that consumed tokens did not usually do it for nothing:
            # a reported zero is normally a runner that declined to say, and
            # rendering it as $0.0000 understates the session total with a
            # number that reads like a fact.
            #
            # A free model is the exception, and it is not a rare one -- it is
            # what a stage runs on once a subscription is exhausted. There the
            # zero is the fact, and calling it unknown hides a real total
            # behind "Unavailable" on every row.
            if cost == 0 and self._token_total(row) \
                    and (row.get("model") or "") not in FREE_MODEL_IDS:
                cost = None
            if cost is not None:
                group["costs"].append((cost, False))
            elif isinstance(row.get("estimated_cost_usd"), (int, float)):
                group["costs"].append((row["estimated_cost_usd"], True))
            else:
                group["costs"].append((None, False))
            group["attempts"] += 1
            group["last_result"] = row
        for stage, started in stats["active"].items():
            group = groups.setdefault(stage, {"seconds": 0, "tokens": [], "costs": [], "attempts": 0, "started": float("inf")})
            group["started"] = min(group["started"], started)
            event = stats["live"].get(stage, {})
            group["seconds"] += max(0, stats.get("stopped_at", time.time()) - started)
            group["tokens"].append(event.get("total_tokens"))
            group["costs"].append(self._live_cost(event) if event else (None, False))
            group["attempts"] += 1
        lines = ["STAGE", "Cost of usage so far", ""]
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
                      "Cost   " + cost_subtotal(group["costs"]), ""]
            tokens.extend(group["tokens"])
            costs.extend(group["costs"])
        if not groups:
            lines += ["Waiting for stage…", ""]
        lines += ["TOTALS",
                  "Time   " + duration(sum(group["seconds"] for group in groups.values())),
                  "Tokens " + subtotal(tokens, count),
                  "Cost   " + cost_subtotal(costs), "Reported + projected"]
        return lines

    def _session_panel_attr(self, line):
        palette = getattr(self, "color", {})
        stage_style = getattr(self, "_panel_stage_styles", {}).get(line)
        if stage_style:
            return palette.get(stage_style, 0)
        if line in ("STAGE", "TOTALS"):
            return palette.get("title", 0) | curses.A_BOLD
        if "Unavailable" in line or "(partial)" in line or line.startswith("Waiting"):
            return palette.get("warning", 0)
        if line.startswith("Cost   ") and " est" in line:
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

    def _title(self):
        if self.state == "picker":
            if self.picker_kind == "effort":
                return "Pick an effort (type to filter, Enter select, Esc back)"
            if self.picker_kind == "runner":
                return "Pick a runner (type to filter, Enter select, Esc back)"
            if self.picker_kind == "network":
                return "Network access in the sandbox (Enter select, Esc back)"
            if self.picker_kind == "billing":
                return "How this cline stage is paid for (Enter select, Esc back)"
            return "Pick a model (type to filter, Enter select, Esc back)"
        if self.state == "config_edit":
            if getattr(self, "notice", ""):
                return self.notice
            return "%s %s (Enter save, Esc back)" % (self.picker_target, self.picker_kind)
        if self.state == "stage":
            if getattr(self, "notice", ""):
                return self.notice
            if self.stage_target == "triage":
                return "Recovery model — Enter: change, d: default, q back"
            if self.stage_target.startswith("@"):
                return "OpenCode connection — Enter: edit, q back"
            return "%s — Enter: change, a: use OpenCode for all stages, d: default, q back" % self.stage_target
        title = {
            "menu": "The man from uncle",
            "issue_mode": "Seed as",
            "issue": "Issue number or URL",
            "config": "Configure — Enter opens a section or setting, q back",
            "notice": "Enter to continue to " + (
                "menu" if getattr(self, "notice_destination", "config") == "menu"
                else "Configure"),
            "running": "q stops the run",
        }.get(self.state, "")
        if self.state == "config" and getattr(self, "notice", ""):
            return self.notice
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
            try:
                self.stdscr.addnstr(len(LOGO), (LOGO_W - len("uncle")) // 2, "uncle", 5, self.color["title"])
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
                display_text = "OpenCode (Self hosted)" if self.picker_kind == "runner" and text == "self-hosted" else text
                disp = prefix + display_text + ("  %s" % label if label else "") + marker
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
            if self.state == "config" and getattr(self, "config_section", "") == "stages":
                self._draw_config_desc(top, row, h, w, cx)
        elif self.state == "picker":
            self._draw_picker(h, w, cx, row)
        else:
            try:
                shown_input = "*" * len(self.input_buf) if self.state == "config_edit" and self.picker_kind == "api_key" else self.input_buf
                self.stdscr.addnstr(row, cx, shown_input, w - 1 - cx)
            except curses.error:
                pass
            try:
                self.stdscr.addstr(row, cx + len(self.input_buf), "█", self.color["cursor"])
            except curses.error:
                pass

    def _draw_notice(self, h, w):
        """A centered dismissible notice with one OK."""
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
        title = " " + getattr(self, "notice_title", "markdown reader") + " "
        try:
            self.stdscr.addnstr(top, left,
                                "\u250c" + title.center(box_w - 2, "\u2500") + "\u2510",
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
        support_url = ""
        if self.prompt_kind == "support":
            # The URL gets its own line so one OSC 8 span covers all of it and
            # the narrow-terminal padding below can keep every character visible.
            words = self.prompt_text.split()
            support_url = next((t for t in words if t.startswith("https://")), "")
            if support_url:
                at = words.index(support_url)
                width = max(20, min(72, w - 12))
                lines = (self._wrap(" ".join(words[:at]), width) + [support_url]
                         + self._wrap(" ".join(words[at + 1:]), width))
        if self.prompt_kind == "confirm":
            footer = "[y] approve      [n] decline"
            if self.gate_file:
                footer = "[y] approve      [n] decline      [v] view file"
            if self.prompt_text.startswith("Audit finding "):
                footer = "[y] Ignore  [n] Keep blocking  [v] audit  [↑↓] scroll"
        elif self.prompt_kind == "audit":
            footer = "[s] Skip  [r] Human reviewed — OK  [n] Keep blocking"
        elif self.prompt_kind == "finished":
            footer = "[Enter/Esc] dismiss"
        elif self.prompt_kind == "support":
            footer = "[s] open GitHub to star      [Enter/Esc] dismiss"
        elif self.prompt_kind == "enter":
            footer = "[Enter] continue      [Esc] decline"
            if self.prompt_text.startswith(("Commit signing needs your help.", "Commit needs your help.")):
                footer = "[c] Copy command  [Enter] resume  [Esc] cancel"
        else:
            footer = "type an answer, [Enter] send, [Esc] cancel"
        footer += ('   Chat focused · [Tab] return to dialog'
                   if getattr(self, 'chat_focus', 'gate') == 'chat'
                   else '   [Tab] ask in chat')
        body = list(lines)
        if self.prompt_text.startswith("Audit finding "):
            visible = max(1, h - 10)
            self.prompt_scroll = max(0, min(getattr(self, "prompt_scroll", 0), len(lines) - visible))
            body = lines[self.prompt_scroll:self.prompt_scroll + visible]
        if self.prompt_kind == "input":
            body += ["", "> " + self.prompt_buf + "\u2588"]
        if self.prompt_text.startswith(("Commit signing needs your help.", "Commit needs your help.")):
            width = max(1, w - 10)
            import textwrap
            lines = [line for paragraph in self.prompt_text.splitlines()
                     for line in (textwrap.wrap(paragraph, width=width) or [""])]
            footer_lines = self._wrap(footer, width)
            status = self._wrap(getattr(self, "signing_copy_status", ""), width)
            visible = max(1, h - 6 - len(footer_lines) - len(status))
            self.prompt_scroll = max(0, min(getattr(self, "prompt_scroll", 0), max(0, len(lines) - visible)))
            body = lines[self.prompt_scroll:self.prompt_scroll + visible] + status + [""] + footer_lines
        else:
            body += ["", footer]

        box_w = min(w - 4, max(len(l) for l in body + [footer]) + 6)
        box_w = (min(w - 2, max(box_w, min(30, w - 2)))
                 if self.prompt_text.startswith(("Commit signing needs your help.", "Commit needs your help.")) else max(box_w, 30))
        if support_url:
            # 43 visible URL characters need a 48-wide box at 1-column padding.
            box_w = min(w - 2, max(box_w, len(support_url) + 5))
        box_h = len(body) + 4
        top = max(0, (h - box_h) // 2)
        left = max(0, (w - box_w) // 2)
        title = {"confirm": " approve ", "enter": " review ", "input": " input ", "support": " support Uncle ", "finished": " Finished "}.get(
            self.prompt_kind, " uncle ")
        if self.prompt_text.startswith(("Commit signing needs your help.", "Commit needs your help.")):
            title = " signed commit required "
        if self.prompt_text.startswith("Audit finding "):
            title = " blocking audit finding "

        border = self.color["title"]
        try:
            self.stdscr.addnstr(top, left, "\u250c" + title.center(box_w - 2, "\u2500") + "\u2510", box_w, border)
            for i in range(box_h - 2):
                self.stdscr.addnstr(top + 1 + i, left, "\u2502" + " " * (box_w - 2) + "\u2502", box_w, border)
            self.stdscr.addnstr(top + box_h - 1, left, "\u2514" + "\u2500" * (box_w - 2) + "\u2518", box_w, border)
        except curses.error:
            pass
        self.support_link = None
        for i, line in enumerate(body):
            attr = self.color["accent"]
            col, width = left + 3, box_w - 6
            if line is body[-1]:
                attr = self.color["sel"]
            elif self.prompt_kind == "input" and line.startswith("> "):
                attr = self.color["cursor"]
            elif support_url and line == support_url:
                col, width = left + 2, box_w - 4
                self.support_link = (top + 2 + i, col, support_url)
            try:
                self.stdscr.addnstr(top + 2 + i, col, line, width, attr)
            except curses.error:
                pass

    def _paint_support_link(self):
        """Wrap the support URL already on screen in an OSC 8 hyperlink.

        curses has no hyperlink attribute, so after it refreshes we rewrite
        the same cells raw with the link open/close sequences around them,
        then restore the cursor so curses' idea of it stays true.
        """
        link = getattr(self, "support_link", None)
        if not link or self.prompt_kind != "support":
            return
        y, x, url = link
        # DECSC/DECRC bracket the write so cursor and SGR state return intact.
        seq = ("\x1b7\x1b[%d;%dH\x1b[4m\x1b]8;;%s\x1b\\%s\x1b]8;;\x1b\\\x1b8"
               % (y + 1, x + 1, url, url)).encode()
        try:
            os.write(sys.stdout.fileno(), seq)
        except (OSError, ValueError):
            pass

    # ---- input ----
    def handle_key(self, k):
        preview = getattr(self, 'completion_preview', None)
        if (k == 27 and self.state == 'running' and preview
                and not getattr(self, 'prompt_kind', '')
                and not getattr(self, 'chat_picker', False)
                and preview.process and preview.process.poll() is None):
            preview.close()
            return
        if self.state == 'triage':
            self._triage_key(k)
            return
        if (k == 9 and getattr(self, 'chat_open', False) and
                self.state in ('menu', 'chat', 'running') and
                self.chat_focus == 'chat' and self.chat_picker):
            try:
                self._complete_chat_file()
            except (OSError, ValueError) as exc:
                self.chat_error = sanitize(str(exc))
            return
        if self.state == 'menu':
            self._ensure_chat()
            if self._homepage_key(k):
                return
        if getattr(self, 'chat_open', False) and self.state in ('menu', 'chat', 'running'):
            if self._chat_key(k):
                return
        if (self.state == "running" and getattr(self, "prompt_kind", "") == "enter"
                and self.prompt_text.startswith(("Commit signing needs your help.", "Commit needs your help."))):
            if k in (ord("c"), ord("C")) and getattr(self, "signing_command", ""):
                self._copy_signing_command()
                return
            if k == 27:
                self.stop_workflow()
                self.state = "menu"
                self.sel = 0
                return
            if k in (curses.KEY_UP, curses.KEY_DOWN):
                self.prompt_scroll = max(0, self.prompt_scroll + (1 if k == curses.KEY_DOWN else -1))
                return
        if self.state == "running" and getattr(self, "prompt_kind", "") in ("support", "finished"):
            if self.prompt_kind == "support" and k in (ord("s"), ord("S")):
                self.prompt_kind = ""
                self.chat_focus = "chat"
                threading.Thread(target=webbrowser.open,
                                 args=(STAR_URL,),
                                 daemon=True).start()
            elif k in (10, 13, 27, ord("q"), ord("Q")):
                self.prompt_kind = ""
                self.chat_focus = "chat"
            elif k == 3:
                self._quit()
            return
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
                self.state = getattr(self, "notice_destination", "config")
                self.notice_destination = "config"
                self.notice_title = "markdown reader"
                self.config_sel = 0
                return
            if self.state == "running" and self.prompt_kind:
                if self.prompt_kind in ("confirm", "audit"):
                    self.answer_prompt("n")     # anything but y declines
                elif self.prompt_kind == "input":
                    self.prompt_kind = ""       # leave the question standing
                    self.chat_focus = "chat"
                    self.prompt_seen = 0
                return
            self._go_back()
            return

        if self.state == "notice":
            # Any key is OK; that is what an OK box is.
            self.state = getattr(self, "notice_destination", "config")
            self.notice_destination = "config"
            self.notice_title = "markdown reader"
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
            # `t` is unbound at these prompts; `input` prompts take text, so
            # they reach triage through /triage in the composer instead.
            if self.prompt_kind in ("confirm", "enter", "audit") and k in (ord("t"), ord("T")):
                self.open_triage()
                return
            if self.prompt_kind == "audit":
                if k in (ord("s"), ord("S"), ord("r"), ord("R"), ord("n"), ord("N")):
                    self.answer_prompt(chr(k).lower())
                elif k in (curses.KEY_UP, curses.KEY_DOWN):
                    self.prompt_scroll = max(0, getattr(self, "prompt_scroll", 0) + (1 if k == curses.KEY_DOWN else -1))
                elif k in (ord("v"), ord("V")) and self.gate_file:
                    self._open_viewer(self.gate_file)
                return
            if self.prompt_kind == "confirm":
                if self.prompt_text.startswith("Audit finding ") and k in (curses.KEY_UP, curses.KEY_DOWN):
                    self.prompt_scroll = max(0, getattr(self, "prompt_scroll", 0) + (1 if k == curses.KEY_DOWN else -1))
                elif k in (ord("y"), ord("Y")):
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
            nrows = len(self._config_items())
            if k == curses.KEY_UP or k in (ord("k"), ord("K")):
                self.config_sel = (self.config_sel - 1) % nrows
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")):
                self.config_sel = (self.config_sel + 1) % nrows
            elif k in (10, 13):
                section = getattr(self, "config_section", "")
                if not section:
                    self.config_section = ("stages", "opencode", "misc", "supervision")[self.config_sel]
                    self.config_sel = self.config_scroll = 0
                elif section == "supervision":
                    self._supervision_enter()
                elif section == "misc":
                    if self.config_sel == 0:
                        self._set_field("!misc", "auto_mode", "false" if self.misc.get("auto_mode") == "true" else "true")
                    else:
                        self._open_picker("approval_name", "!misc")
                elif section == "opencode" and self.config_sel == 1:
                    self._set_field("@connection", "base_url", connection_settings(self.stage_api_keys).get("base_url", ""))
                else:
                    self._open_stage(self._config_row())
            elif k in (ord("q"), ord("Q")):
                self._go_back()
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
            elif k in (ord("a"), ord("A")):
                self._apply_opencode_to_all_stages()
            elif k in (ord("d"), ord("D")) and not self.stage_target.startswith("@"):
                self._set_field(self.stage_target, self._stage_field(), "")
                self.stage_sel = min(self.stage_sel,
                                     len(self.stage_fields(self.stage_target)) - 1)
            elif k in (ord("q"), ord("Q")):
                self.state = "config"
            return

        if self.state in ("menu", "issue_mode"):
            # The main menu is a horizontal bar, so left/right move along it.
            side = self.state == "menu"
            if k == curses.KEY_UP or k in (ord("k"), ord("K")) \
                    or (side and k in (curses.KEY_LEFT, ord("h"), ord("H"))):
                self.sel = (self.sel - 1) % len(self.items())
            elif k == curses.KEY_DOWN or k in (ord("j"), ord("J")) \
                    or (side and k in (curses.KEY_RIGHT, ord("l"), ord("L"))):
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
            if getattr(self, "config_section", ""):
                self.config_section = ""
                self.config_sel = self.config_scroll = 0
            else:
                self.state = "running" if self.proc and self.proc.poll() is None else "menu"
        elif self.state == "stage":
            self.state = "config"
        elif self.state == "config_edit":
            self.state = "config" if self.picker_target in ("@new", "!misc", "!supervision") else "stage"
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
                filename = {0: "REQUIREMENTS.md", 2: "CHANGE_REQUEST.md"}[self.workflow_idx]
                try:
                    present = os.path.isfile(os.path.join(_project_root(), filename))
                except OSError:
                    present = False
                if not present:
                    self.notice_lines = [
                        filename + " is needed",
                        "Create it in the project root and try again.",
                    ]
                    self.notice_title = "Required input"
                    self.notice_destination = "menu"
                    self.workflow_idx = None
                    self.sel = 0
                    self.state = "notice"
                    return
                self._run()
        elif self.state == "issue_mode":
            self.issue_mode = ISSUE_MODES[self.sel][1]
            self._run()

    def _confirm_text(self):
        if self.state == "issue":
            issue = self.input_buf.strip().removeprefix('#')
            if not self._valid_issue(issue):
                self.notice = 'Enter an issue number or https://github.com/owner/repo/issues/123'
                return
            self.issue = issue
            self.notice = ""
            self.input_buf = ""
            self.state = "issue_mode"
            self.sel = 0
        elif self.state == "config_edit":
            val = self.input_buf.strip()
            if self.picker_kind == "model" and self.stage_runner(self.picker_target) != "self-hosted" and not valid_model_id(val):
                # Storing it would only surface as a failed stage later.
                self.notice = "not a cline model id: %s (expected modelType/model)" % val
                return
            self.notice = ""
            self._set_field(self.picker_target, self.picker_kind, val)
            if self.notice:
                return
            self.input_buf = ""
            if self.picker_target in ("!misc", "!supervision"):
                self.state = "config"
                return
            self.stage_sel = min(self.stage_sel,
                                 len(self.stage_fields(self.picker_target)) - 1)
            self.state = "stage"

    def _run(self):
        self._ensure_chat()
        if getattr(self, 'triage_request', None) is not None:
            self.chat_error = 'Wait for recovery to finish or use /clear to cancel before starting a workflow.'
            return
        if self.home_request is not None:
            self.chat_error = 'Wait for the current chat request or cancel it with /clear before starting a workflow.'
            return
        if self.workflow_idx == 1 and not self._valid_issue(self.issue):
            self.state = 'issue'
            self.input_buf = self.issue
            self.notice = 'Enter an issue number or https://github.com/owner/repo/issues/123'
            return
        # The run reads the file, so make sure we are not about to launch on
        # top of an edit we have not seen.
        self.maybe_reload()
        self.direct_issue = ""
        if self.workflow_idx == 2:
            self.direct_issue = _direct_origin_issue()
        self.recovery_active = False
        self.state = "running"
        self.start_workflow()

    def _quit(self):
        if getattr(self, "completion_preview", None):
            self.completion_preview.close()
        self.state = "quit"

    # ---- main loop ----
    def run(self):
        previous_term = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, terminate)
        try:
            self._run_loop()
        finally:
            try:
                if getattr(self, "home_request", None):
                    self.home_request.cancel()
                    self.home_request.thread.join(timeout=5)
                if getattr(self, "triage_request", None):
                    self.triage_request.cancel()
                    self.triage_request.thread.join(timeout=5)
                if getattr(self, "supervision_host", None):
                    self.supervision_host.controller.cancel('cancelled')
                    self.supervision_host.close()
                    self.supervision_host = None
                self.stop_workflow()
            finally:
                signal.signal(signal.SIGTERM, previous_term)

    def _run_loop(self):
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.stdscr.timeout(80)
        self._setup_colors()
        dirty = True
        size = None
        while self.state != "quit":
            dirty = self.poll_home_chat() or dirty
            dirty = self.poll_triage() or dirty
            dirty = self.poll_issue_picker() or dirty
            self._poll_workflow()
            dirty = self.poll_supervision() or dirty
            dirty = self.poll_status() or dirty
            dirty = self.poll_session_stats() or dirty
            if self.state in ("running", "triage") and getattr(self, "proc", None):
                # Drained in triage too: a driver still streaming a stage must
                # not block on a full pipe while the operator reads a reply.
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


def main(stdscr):
    UncleTUI(stdscr).run()


if __name__ == "__main__":
    curses.wrapper(main)
