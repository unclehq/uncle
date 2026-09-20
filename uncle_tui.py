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
from urllib.parse import urlparse
from urllib.request import url2pathname
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
from completion_preview import CompletionPreview, STAR_URL, launch_spec
from preview_server import PreviewServer
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
import supervisor_runner
from supervisor_runner import SupervisorRequest, build_command as supervisor_command
import supervisor_chat
from supervisor_chat import ChatRequest
import gate_answer
import worktree_runs

CLINE_CONFIG = os.environ.get("CLINE_CONFIG", os.path.expanduser("~/.cline/data/settings/providers.json"))

WORKFLOWS = [
    ("New application", [os.path.join(ROOT, "scripts", "stagegate.sh")]),
    ("From GitHub issue", [os.path.join(ROOT, "scripts", "from-issue.sh")]),
    ("Change request", [os.path.join(ROOT, "scripts", "change-workflow.sh")]),
]
EFFORTS = ["high", "medium", "low"]
ISSUE_MODES = [("auto", ""), ("change request", "--change"), ("new application", "--new"),
               ("change request in worktree", "--worktree")]
# A triage proposal that says there is nothing to edit needs no master turn.
NO_EDIT_PROPOSAL = re.compile(
    r'(?i)\bno\s+(?:files?\s+)?edits?\b|\bno\s+files?\s+edited\b|\bnothing\s+to\s+(?:edit|change)\b'
    r'|\bno\s+files?\s+changed\b|\bno\s+changes\s+(?:needed|required)\b|\bresume\s+as\s+is\b')
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


_APPROVE_WORDS = frozenset(('approve', 'approved', 'approval', 'accept', 'accepted',
                            'yes', 'y', 'ok', 'okay', 'confirm', 'confirmed',
                            'go', 'proceed', 'do', 'it'))
_DECLINE_WORDS = frozenset(('decline', 'declined', 'deny', 'reject', 'rejected',
                            'no', 'n', 'cancel', 'keep', 'stop', 'abort'))


def _replacement_decision(text):
    """'approve', 'decline', or None for a pending replacement proposal.

    The prompt names two exact phrases, and only those were accepted. A typo --
    "approval replacement" for "approve replacement" -- fell through to the
    supervisor, which read it as approval and said so, while the TUI refused the
    action it proposed and re-showed the prompt. The operator was told both that
    it was proceeding and that it was not, with no way out.

    Short answers only: four words at most, so a sentence that merely mentions
    approving something is still a question for the supervisor rather than a
    decision. A message carrying both senses is neither.
    """
    words = re.findall(r"[a-z]+", (text or '').lower())
    if not words or len(words) > 4:
        return None
    approve = bool(_APPROVE_WORDS & set(words))
    decline = bool(_DECLINE_WORDS & set(words))
    if approve == decline:
        return None
    return 'approve' if approve else 'decline'


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
    "delegate_gates": "Standing delegation for routine dialogs (none/routine). With routine, the supervisor answers document approvals, audit findings and press-Enter prompts once each as they open, recorded as supervisor:standing. Signing, publication and waiver gates always need your explicit ask in chat.",
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
    VIEWER_PROGRAMS = ("cursor", "code", "glow", "bat", "less", "more", "cat")

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
        self.build_scroll = 0
        self.build_wrapped_count = 0
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
        # Read startup action from environment if present
        self._startup_action = os.environ.get("UNCLE_STARTUP_ACTION")
        self._startup_text = os.environ.get("UNCLE_STARTUP_TEXT")
        self._startup_unattended = os.environ.get("UNCLE_STARTUP_UNATTENDED") == "1"
        self._startup_injected = False
        if self._startup_unattended:
            self.misc['auto_mode'] = True
        # Bind the homepage composer before the first frame or key event.
        self._ensure_chat()
        self.chat_focus = 'chat'
        self.home_menu_open = False
        self.sel = 0
    # ---- colors (cline's CLI palette) ----
    def _setup_colors(self):
        # emphasis sits between plain text and the bold user rows of the supervisor chat;
        # without colours reverse video is the only level guaranteed to differ from bold.
        self.color = {"title": 0, "accent": 0, "good": 0, "sel": 0, "cursor": 0, "warning": curses.A_BOLD, "bad": curses.A_BOLD, "muted": curses.A_DIM,
                      "emphasis": curses.A_REVERSE}
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
        reg("emphasis", curses.COLOR_YELLOW, curses.A_BOLD)
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
        if section == "recovery":
            return "triage"
        # The stages list omits triage (it has its own section), so rows index
        # BUILD_CONFIG_STAGES; a CONFIG_STAGES index would name the wrong stage.
        if 0 <= self.config_sel < len(BUILD_CONFIG_STAGES):
            return BUILD_CONFIG_STAGES[self.config_sel]
        return self._profile_targets()[self.config_sel - len(BUILD_CONFIG_STAGES)]

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
        value = value or ""
        if not (stage == "!misc" and field == "markdown_viewer"):
            value = value.strip()
        elif not value.strip():
            value = ""
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
            return ["1. Configure stages", "2. Configure OpenCode / self hosting", "3. Miscellaneous", "4. Supervision", "5. Recovery"]
        if section == "supervision":
            return self._supervision_items()
        if section == "recovery":
            return ["Recovery model — diagnose failures and propose repairs"]
        if section == "opencode":
            return ["OpenCode connection — Base URL and API key", "Refresh supported models (%d loaded)" % len(self.stage_api_keys.get("__opencode_models__", {}))]
        if section == "misc":
            return ["Auto mode: " + ("on" if getattr(self, "misc", {}).get("auto_mode") == "true" else "off"),
                    "Name for approvals: " + getattr(self, "misc", {}).get("approval_name", "not set"),
                    "Markdown viewer: " + (getattr(self, "misc", {}).get("markdown_viewer") or "auto (first installed)")]
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
            return "Auto mode runs unattended: human gates are recorded as waived; failing tests still stop the run. It stops at the publication boundary: the PR title, summary, consent and any commit signing are asked of you here, never delegated. The approval name identifies your manual approvals."
        if getattr(self, "config_section", "") == "supervision":
            return self._supervision_desc()
        if not getattr(self, "config_section", ""):
            return "Choose a configuration section."
        return CONFIG_DESC.get(self._config_row(), "")

    # ---- generic picker (model / effort / runner) ----
    def _picker_rows(self):
        """Rows for the active picker: (kind, text), kind in header/option/model/custom."""
        if self.picker_kind == "markdown_viewer":
            return ([('option', name) for name in self.VIEWER_PROGRAMS if shutil.which(name)]
                    + [('custom', 'Custom… (type a command)')])
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
        if self.picker_kind == "markdown_viewer":
            return self._field_value(stage, self.picker_kind)
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
            self.input_buf = (self.pick_filter if self.picker_kind == "markdown_viewer"
                              else self.pick_filter.strip()) or self._picker_current()
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
        self.state = "config" if self.picker_target == "!misc" else "stage"

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
                    raw = line.rstrip("\r\n")
                    viewer_key = "misc.markdown_viewer"
                    if raw.startswith(viewer_key) and len(raw) > len(viewer_key) and raw[len(viewer_key)].isspace():
                        value = raw[len(viewer_key) + 1:]
                        self.misc["markdown_viewer"] = value if value.strip() else ""
                        continue
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
        if kind == 'test_execution':
            if getattr(self, 'workflow_exit_reported', False):
                return
            active = getattr(self, 'active_test_runs', set())
            identity = ev.get('id')
            if isinstance(identity, str):
                if ev.get('state') == 'Running':
                    active.add(identity)
                elif ev.get('state') == 'Stopped':
                    active.discard(identity)
            self.active_test_runs = active
            return
        host = getattr(self, 'supervision_host', None)
        if host is not None:
            try:
                host.controller.observe(ev)
            except (OSError, ValueError) as exc:
                self._ensure_chat()
                self.home_history.append(('supervisor', 'Supervision error: ' + sanitize(str(exc))))
        if kind in ('gate_open', 'gate_close', 'gate_answer'):
            # Driver-named dialog identity (D-5): the supervisor may answer a
            # prompt only while this metadata names it.
            self._ensure_chat()
            if kind == 'gate_open':
                self.gate_meta = {key: ev.get(key, '') for key in
                                  ('run', 'prompt_id', 'text', 'kind', 'class', 'reason', 'file', 'stage')}
                self.gate_meta['choices'] = list(ev.get('choices') or [])
            elif self.gate_meta and (self.gate_meta.get('run'), self.gate_meta.get('prompt_id')) == (
                    ev.get('run', self.gate_meta.get('run')), ev.get('prompt_id', self.gate_meta.get('prompt_id'))):
                if kind == 'gate_answer':
                    self.gate_meta['answered_by'] = ev.get('answered_by', '')
                else:
                    self.gate_meta = None
        if kind.startswith('steering_') or kind == 'chat_output':
            if getattr(self, 'workflow_exit_reported', False):
                return  # Late buffered events cannot reconnect a stopped build.
            self._ensure_chat()
            channels = getattr(self, 'steering_channels', {})
            self.steering_channels = channels
            stage = ev.get('stage', '')
            record = next((r for r in self.steer_records if r['id'] == ev.get('message_id')), None)
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
                if record is not None:
                    confirmable = str(ev.get('correlation', '') or '') in supervision_lib.CORRELATED
                    record['state'] = (('accepted' if confirmable else 'accepted-unconfirmed')
                                       if kind == 'steering_accepted' else 'rejected')
                    record['detail'] = sanitize(str(ev.get('detail', '')))[:400]
                    text = 'Steering %s %s by %s' % (record['id'][:8], record['state'], stage) if kind == 'steering_accepted' else text
                self.home_history.append(('system', text))
                if kind == 'steering_rejected': self.chat_error = text
            elif kind == 'steering_answered' and record is not None:
                record['state'] = 'answered'
                self.home_history.append(('system', 'Steering %s answered by %s' % (record['id'][:8], stage)))
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
            if ev.get("stage", "") != self.status_stage and self.status_stage:
                self.previous_stage = self.status_stage
                # A web app is viewable the moment implementation stops writing
                # code. Verification, the checklist and the audit still have to
                # run -- and still gate completion -- but they take longer than
                # the build did, and nothing is served by making someone wait
                # out a review to see whether the page looks right.
                self._preview_after_implementation(self.status_stage)
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
                if getattr(self, 'prompt_kind', '') not in ('support', 'finished', 'complete'):
                    self.prompt_kind = ''
                    self.chat_focus = 'chat'
                self._ensure_chat()
                self._dialog_closed('driver exited')
                self.gate_meta = None
                self.delegation_session = None
                if self.workflow_exit_code == 0:
                    # A run that ended because it was done is not a stopped
                    # run. It said so in neither the output nor the chat, and
                    # the old text sent the operator to the menu as if there
                    # were nothing left to look at.
                    getattr(self, 'output', []).append('Finished.')
                    message = 'Finished.'
                    self.home_history.append(('system', message))
                    self.chat_error = ''
                else:
                    reason = 'Workflow was killed (SIGKILL, exit code 137)' if self.workflow_exit_code in (137, -9) else 'Workflow stopped (exit code %s)' % self.workflow_exit_code
                    message = reason + '. Stage chat disconnected. Type /homepage to return to the menu.'
                    self.home_history.append(('system', message))
                    self.chat_error = message
                host = getattr(self, 'supervision_host', None)
                if host is not None:
                    # Triage owns a failure exit; an in-flight diagnosis is
                    # cancelled (and charged) and queued triggers wait for it.
                    host.controller.cancel('interrupted')
                    host.controller.driver_exited(self.workflow_exit_code)
                self._maybe_auto_triage()

    def _rerun_pending(self):
        """True when a stage rerun is waiting to be consumed in this project."""
        try:
            return (Path(_project_root()) / '.uncle/workflow/rerun-request.json').is_file()
        except OSError:
            return False

    def _enter_run_worktree(self):
        """Move this run into its own worktree before anything reads the root.

        It has to happen here rather than inside the driver: the driver can
        export UNCLE_PROJECT_ROOT to its own children, but this process already
        computed _project_root() and would spend the whole run watching the
        directory the driver left. Setting it in our own environment points
        both at the same place, since the driver inherits this env.
        """
        if os.environ.get("UNCLE_PROJECT_ROOT_LOCKED"):
            return
        # Never for an issue run. The name would be taken from whatever brief is
        # sitting in the project directory -- the *previous* run's, since this
        # one is fetched and written afterwards. That produced worktrees for
        # issues 68, 69 and 70 all named after an older request, separated only
        # by a counter. from-issue.sh creates the worktree once it knows the
        # issue's title, which is the only name that describes the work.
        if getattr(self, "workflow_idx", None) == 1:
            return
        try:
            result = subprocess.run(
                ["bash", "-c", '. "$1/scripts/lib/worktrees.sh"; worktree_auto "$2"',
                 "_", ROOT, _project_root()],
                capture_output=True, text=True, timeout=120,
                env=dict(os.environ, ROOT=ROOT), cwd=_project_root())
        except (OSError, subprocess.SubprocessError):
            return
        directory = (result.stdout or "").strip().splitlines()
        directory = directory[-1] if directory else ""
        if result.returncode or not directory or not os.path.isdir(directory):
            return
        os.environ["UNCLE_PROJECT_ROOT"] = directory
        os.environ["UNCLE_PROJECT_ROOT_LOCKED"] = "1"
        self.home_history.append(("system", "Working in " + sanitize(directory)))

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
        self.active_test_runs = set()
        self._supervision_start(env)
        env["UNCLE_SIGNING_JSON"] = "1"
        self.status_pos = 0
        self.panel_scroll = None
        self.proc_done = False
        self.workflow_completed = False
        self.early_preview_shown = False
        self._early_preview_stamp = None
        self._early_preview_next = 0.0
        self._preview_page = "index.html"
        self._close_early_preview()
        self.workflow_exit_reported = False
        self.support_checked = False
        self.completion_preview = None
        metrics = os.path.join(_project_root(), ".uncle", "workflow", "metrics")
        self.session_stats = {"active": {}, "live": {}, "records": [], "tick": -1,
                              "seen": set(os.listdir(metrics)) if os.path.isdir(metrics) else set()}
        self._restore_session_totals()
        self.output = []
        self.build_scroll = 0
        self.build_wrapped_count = 0
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
            command = self.cmd_for()
            # Recorded at launch: the boundary guard in _apply_gate_answer must
            # not follow a settings change made while this run is in flight.
            self.workflow_unattended = "--unattended" in command
            self.proc = subprocess.Popen(command, cwd=_project_root(), env=env,
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
        self._poll_early_preview()
        preview_changed = self._poll_completion_preview()
        return got or preview_changed or before != (self.proc_done, self.prompt_kind)

    def _build_finished(self):
        """A successful, finished run: banner seen, exit observed, exit code 0.

        Failures and human stops keep today's Esc behaviour; only a build that
        actually completed has nothing left to step back into.
        """
        return (getattr(self, "workflow_completed", False)
                and getattr(self, "workflow_exit_reported", False)
                and getattr(self, "workflow_exit_code", None) == 0)

    def _back_from_build(self):
        """Esc on a finished build page opens the complete dialog instead of
        walking back through screens of a run that no longer exists."""
        if (self.state != "running" or getattr(self, "prompt_kind", "")
                or getattr(self, "recovery_active", False) or not self._build_finished()):
            return False
        self.prompt_kind = "complete"
        self.prompt_text = "Build is complete. Press Enter to return to the home page."
        self.chat_focus = "gate"
        self.chat_error = ""
        return True

    def _complete_key(self, k):
        """Enter dismisses the completion dialog and stays on the build page.

        It used to drop to the home page, which threw away the thing the
        operator had just spent the whole run producing: the output, the stage
        history and the chat about it. Leaving is now an explicit /homepage.
        """
        if k in (10, 13):
            self.stop_workflow()
            self.prompt_kind = ""
            self.prompt_text = ""
            self.recovery_active = False
            self.chat_focus = "chat"
            self.chat_error = ""
        elif k == 3:
            self._quit()

    def _offer_support(self):
        """Offer once per local user, only after this workflow finishes."""
        if getattr(self, "support_checked", False) or not self.proc:
            return
        # The completion modal owns the screen until Enter; the offer waits.
        if getattr(self, "prompt_kind", "") == "complete":
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

    # How often to look for a page. Not a settling delay: the first
    # sighting opens it.
    _PREVIEW_POLL_SECONDS = 0.5

    # Stages that write the application. The preview build exists purely to put
    # something on screen early, so it is the first place to watch, not the last.
    _PREVIEW_STAGES = ("implementation", "preview-build")

    def _poll_early_preview(self):
        """Open the page the moment one exists, from whichever stage wrote it.

        Opened on first sighting rather than after it settles. The earlier
        two-reading wait existed because a `file://` page could not correct
        itself: catch index.html half-written and the operator was left looking
        at a broken page until the stage ended. The page is now served with a
        reload script, so an early open fixes itself within a poll -- and an
        empty file is still skipped, which is the only case worth waiting for.
        """
        if getattr(self, "completion_preview", None) is not None:
            return
        if getattr(self, "early_preview_shown", False):
            return
        stage = (getattr(self, "status_stage", "") or "")
        if not any(stage.startswith(name) for name in self._PREVIEW_STAGES):
            return
        now = time.monotonic()
        if now < getattr(self, "_early_preview_next", 0.0):
            return
        self._early_preview_next = now + self._PREVIEW_POLL_SECONDS
        if self._previewable_page() is None:
            return
        self._show_early_preview()

    def _previewable_page(self):
        """(size, mtime) of a finished-enough page on disk, or None.

        Only file-backed pages qualify. A `webpage` spec pointing at a local
        server needs that server running, which during implementation it is
        not, and a `command` project would start a process behind the
        operator's back. launch_spec falls back to index.html, so an ordinary
        static site needs no configuration.
        """
        try:
            spec = launch_spec(_project_root())
        except (OSError, ValueError):
            return None
        if spec.get("kind") != "webpage":
            return None
        url = spec.get("url", "")
        if not url.startswith("file://"):
            return None
        try:
            page = url2pathname(urlparse(url).path)
            info = os.stat(page)
        except OSError:
            return None
        if not info.st_size:
            return None
        # launch_spec resolves the root, so relpath must too: on macOS a
        # /var project root resolves to /private/var, and comparing the two
        # spellings yields a ../.. path the preview server rightly 404s.
        try:
            relative = Path(page).relative_to(Path(_project_root()).resolve())
        except ValueError:
            return None
        self._preview_page = relative.as_posix()
        return (info.st_size, info.st_mtime_ns)

    def _preview_after_implementation(self, finished_stage):
        """Fallback for a page that only appears as the stage ends."""
        if finished_stage not in ("implementation", "implementation-step"):
            if not finished_stage.startswith("implementation-step-"):
                return
        if self._previewable_page() is None:
            return
        self._show_early_preview()

    def _show_early_preview(self):
        """Open the page in a browser, served so it can refresh itself.

        Deliberately not CompletionPreview: that object announces `done` when it
        finishes launching, which raises the finished/star dialog. Correct at the
        end of a run, wrong in the middle of one -- the build is still going, and
        the dialog also burns the once-per-user star prompt.
        """
        if getattr(self, "early_preview_shown", False):
            return
        if getattr(self, "completion_preview", None) is not None:
            return
        self.early_preview_shown = True
        server = PreviewServer(_project_root(), self._preview_page)
        if server.url is None:
            return
        self.preview_server = server
        if not webbrowser.open(server.url):
            server.close()
            self.preview_server = None

    def _close_early_preview(self):
        server = getattr(self, "preview_server", None)
        if server is not None:
            server.close()
            self.preview_server = None

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
        if text in ("Workflow complete.", "Change workflow complete.",
                    "Workflow complete with waived acceptance.",
                    "Change workflow complete with waived acceptance."):
            self.workflow_completed = True
        # Review banners identify the document only. The following question
        # owns stdin; never synthesize an answer on the user's behalf.
        if text.startswith("AUDIT REVIEW REQUIRED:"):
            # Audit findings ask for a decision immediately, with no initial
            # press-Enter gate. Never send a synthetic answer here.
            self.gate_file = text.split(":", 1)[1].strip()
            return
        if text.startswith("HUMAN REVIEW REQUIRED:"):
            self.gate_file = text.split(":", 1)[1].strip()
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
                # Banner metadata must not become part of the stage label.
                stage = re.split(r'\s+(?:Effort|Model|Cap):', stage, maxsplit=1)[0]
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
    def _viewer_command(self, full):
        """Return the configured reader, or the first installed safe default."""
        quoted = shlex.quote(full)
        configured = getattr(self, "misc", {}).get("markdown_viewer", "")
        candidates = list(self.VIEWER_PROGRAMS)
        if configured:
            if configured not in self.VIEWER_PROGRAMS:
                return configured + " " + quoted
            candidates.remove(configured)
            candidates.insert(0, configured)
        for name in candidates:
            if not shutil.which(name):
                continue
            if name == "glow":
                return ("glow %s | less" % quoted if shutil.which("less")
                        else "glow -p %s" % quoted)
            return "%s %s" % (name, quoted)
        return ""

    def _open_viewer(self, path):
        full = path if os.path.isabs(path) else os.path.join(_project_root(), path)
        if not os.path.exists(full):
            self.view_lines = ["not found: %s" % full]
            self.view_title = path
            self.view_scroll = 0
            self.state = "viewer"
            return

        snapshot_dir = tempfile.mkdtemp(prefix="uncle-viewer-")
        snapshot = os.path.join(snapshot_dir, os.path.basename(full))
        try:
            shutil.copyfile(full, snapshot)
            os.chmod(snapshot, 0o444)
            cmd = self._viewer_command(snapshot)
            if cmd:
                self._run_in_terminal(cmd)
                if shlex.split(cmd)[0] in ("cursor", "code"):
                    snapshot_dir = ""  # detached editors may read after returning
                return
            with open(full, errors="replace") as fh:
                body = fh.read().splitlines() or ["(empty file)"]
            self.view_lines = [
                "No Markdown viewer found (%s)." % ", ".join(self.VIEWER_PROGRAMS),
                "Choose one in Configure > Miscellaneous > Markdown viewer.",
            ] + body
        except Exception as exc:
            self.view_lines = ["could not read %s" % full, str(exc)]
        finally:
            if snapshot_dir:
                shutil.rmtree(snapshot_dir, ignore_errors=True)
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
                self._dialog_opened(plain)
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
        self._dialog_opened(plain)

    def _dialog_opened(self, plain):
        """SB-9: the chat partner sees every dialog open, with its driver-named class when known."""
        focus = getattr(self, 'chat_focus', 'gate')
        self._ensure_chat()
        self.chat_focus = focus  # a first _ensure_chat must not steal the gate focus just set
        self.prompt_raw = plain
        dialog = self._dialog_record()
        label = dialog['kind'] + (', ' + dialog['class'] + (':' + dialog['reason'] if dialog['reason'] else '')
                                  if dialog['class'] else '')
        self.home_history.append(('system', 'Dialog opened (%s): %s' % (label, sanitize(plain)[:300])))

    def _dialog_closed(self, how):
        if getattr(self, 'prompt_raw', ''):
            self._ensure_chat()
            self.home_history.append(('system', 'Dialog closed (%s): %s' % (how, sanitize(self.prompt_raw)[:120])))
        self.prompt_raw = ''

    def _gate_matches(self):
        """The driver metadata for the prompt on screen, or None (text fallback: advice only)."""
        meta = getattr(self, 'gate_meta', None)
        if not meta or not getattr(self, 'prompt_kind', '') or not getattr(self, 'prompt_raw', ''):
            return None
        shown = re.sub(r'\s+', ' ', self.prompt_raw).strip()
        named = re.sub(r'\s+', ' ', str(meta.get('text', ''))).strip()
        if not named or not (shown.startswith(named[:60]) or named.startswith(shown[:60])):
            return None
        return meta

    def _dialog_record(self):
        """The dialog block the supervisor sees: driver class when named, else text-classified advice only."""
        if not getattr(self, 'prompt_kind', ''):
            return None
        meta = self._gate_matches()
        if meta:
            return supervisor_chat.dialog_record(meta.get('kind') or self.prompt_kind, meta.get('text'),
                                                 meta.get('file') or getattr(self, 'gate_file', ''), meta.get('class'),
                                                 meta.get('reason'), meta.get('run'), meta.get('prompt_id'),
                                                 meta.get('choices'))
        kind, klass, reason, choices = gate_answer.classify(getattr(self, 'prompt_raw', ''),
                                                            signing=bool(getattr(self, 'signing_command', '')))
        record = supervisor_chat.dialog_record(self.prompt_kind or kind, getattr(self, 'prompt_raw', ''),
                                               getattr(self, 'gate_file', ''), klass, reason, choices=choices)
        record['answerable'] = False
        return record

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

    def _stdin_line(self, answer):
        """One line to the driver's stdin; True only when the write and flush succeeded."""
        try:
            self.proc.stdin.write((answer + "\n").encode())
            self.proc.stdin.flush()
            return True
        except Exception:
            return False

    def answer_prompt(self, answer, how='human'):
        """Send one line down the driver's stdin and close the modal."""
        if self._triage_blocks_stdin():
            return False
        self.chat_focus = "chat"
        if not self.proc or self.proc.poll() is not None:
            self.prompt_kind = ""
            self._dialog_closed('driver gone')
            return False
        sent = self._stdin_line(answer)
        # Keep the answer in the transcript, so the log reads like a session.
        self._absorb_line("%s%s" % (self.partial.rstrip(), answer))
        self.partial = ""
        self.prompt_kind = ""
        self.prompt_text = ""
        self.prompt_buf = ""
        self.prompt_seen = 0
        self._dialog_closed(how)
        return sent

    def stop_workflow(self):
        if getattr(self, "completion_preview", None):
            self.completion_preview.close()
            self.completion_preview = None
        # The preview server outlives the stage that triggered it, but never
        # the run: a stray listener on a working tree is not something to leave
        # behind.
        self._close_early_preview()
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
            self.chat_history = []
            self.chat_history_index = -1
            self.chat_saved_draft = ''
            self.chat_cursor = 0
        # Supervisor chat state (Issue 45): the latest driver-named gate, the
        # session's standing grant, steering delivery records and call counts.
        # Set individually: tests bind `chat` before the first call here.
        for name, default in (('gate_meta', None), ('prompt_raw', ''), ('delegation_session', None),
                              ('standing_answered', set), ('steer_records', list), ('steer_retained', None),
                              ('chat_calls', 0), ('standing_calls', 0), ('previous_stage', ''),
                              ('home_request', None), ('home_history', list), ('home_issue_context', '')):
            if not hasattr(self, name):
                setattr(self, name, default() if callable(default) else default)
        self.chat_open = True

    def open_chat(self):
        self._ensure_chat()
        self.chat_focus = 'chat'
        self.state = 'running' if self.proc and self.proc.poll() is None else 'chat'

    def homepage_model(self):
        """Use the first stage shown in Configure for homepage inference."""
        stage = CONFIG_STAGES[0]
        return stage, self.stage_runner(stage), self.stage_model(stage), self.stage_effort(stage)

    def test_execution_status(self):
        process = getattr(self, 'proc', None)
        running = (getattr(self, 'active_test_runs', set()) and process is not None
                   and process.poll() is None
                   and not getattr(self, 'workflow_exit_reported', False))
        return 'Running' if running else ''

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
        fix = re.match(r'^(?:please\s+)?fix(?:\s|$)', message.strip(), re.I)
        markdown_request = re.match(r'^(?:please\s+)?(?:edit|update|correct|repair|rewrite)\b', message.strip(), re.I) and re.search(r'\.md\b|markdown|\.uncle(?:/|\b)', message, re.I)
        if fix or markdown_request:
            self._ensure_chat()
            self.recovery_active = True
            self.chat_focus = 'chat'
            self._triage_turn('execute', proposal=(1, message.strip()), followup=message.strip())
            return
        # "stage" is optional. Requiring it meant "rerun final-audit" -- the
        # exact remedy the driver prints when an audit binding goes stale --
        # went to the supervisor, which has no action for running one stage and
        # could only offer to rerun the whole workflow.
        rerun = re.fullmatch(
            r'(?:please\s+)?(?:run|rerun)\s+(?:the\s+)?([a-z][a-z-]+)(?:\s+stage)?(?:\s+again)?[.!]?',
            message.strip(), re.I)
        if rerun and self._is_known_stage(rerun[1].lower()):
            self.run_named_stage(rerun[1].lower())
            return
        pending = getattr(self, 'home_replace_proposal', None)
        decision = _replacement_decision(message) if pending else None
        if decision:
            self.home_history.append(('user', message))
            self.home_replace_proposal = None
            if decision == 'approve':
                self._home_action(pending, replace_approved=True)
            else:
                self.home_history.append(('system', 'Replacement declined; existing brief preserved.'))
            return
        """Every prose message goes to the supervisor, in every state (SI-1).

        Deterministic operator commands stay local: an issue-build phrase at
        home, `/app-input` for a running preview, `/do` and `/resume` for
        recovery. Nothing here spawns a stage runner or writes raw prose to a
        steering channel; steering is a supervisor action the operator asked for.
        """
        self._ensure_chat()
        if self.home_request is not None:
            raise ValueError('A reply is still running. Wait or use /clear to cancel.')
        if not message.strip():
            return
        proc = getattr(self, 'proc', None)
        gate_question = (self.state == 'running' and bool(getattr(self, 'prompt_kind', ''))
                         and proc is not None and proc.poll() is None)
        running = self.state == 'running' or bool(proc and proc.poll() is None)
        issue_request = re.fullmatch(
            r'(?:please\s+)?(?:build|bulid|implement|start|run|work on)\s+'
            r'(?:(?P<change>change\s+request)\s+)?'
            r'(?:(?:from\s+)?(?:github\s+)?issue\s+|from\s+|this\s+(?:issue\s+)?)?'
            r'(?P<issue>https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*/?|#?[1-9][0-9]*)[.!]?',
            message.strip(), re.IGNORECASE)
        if issue_request and not running and not getattr(self, 'recovery_active', False):
            self.home_history.append(('user', sanitize(message)))
            # Asked to implement an issue now: select auto mode so the run
            # answers its own gates and the build page goes straight to work.
            self._set_field("!misc", "auto_mode", "true")
            self._home_action({'uncle_action': 'github_issue',
                               'issue': issue_request['issue'].removeprefix('#'),
                               'start': True,
                               'issue_mode': '--change' if issue_request['change'] else ''})
            return
        intent = supervisor_chat.delegation_intent(message)
        delegation = None
        if intent and intent['source'] == 'revoke':
            self.home_history.append(('user', sanitize(message)))
            self.delegation_session = None
            self.home_history.append(('system', 'Standing delegation revoked for this session; gates are yours again.'))
            return
        if intent and intent['source'] == 'standing':
            self.home_history.append(('user', sanitize(message)))
            self.delegation_session = {'request': intent['request'], 'granted': int(time.time())}
            self.home_history.append(('system', 'Standing delegation granted for routine dialogs this run '
                                                '(document approvals, audit findings, press-Enter, plain input). '
                                                'Signing, publication and waiver gates still need an explicit ask. '
                                                '/delegate off revokes it.'))
            if not gate_question:
                return
            delegation = {'source': 'standing', 'request': intent['request'], 'choice': None, 'literal': None,
                          'config_key': '', 'config_value': ''}
        elif intent and intent['source'] == 'explicit':
            if not gate_question:
                self.home_history.append(('user', sanitize(message)))
                self.home_history.append(('system', 'No dialog is waiting, so there is nothing to answer.'))
                return
            delegation = dict(intent, config_key='', config_value='')
        self._supervisor_turn(message, delegation=delegation, trigger='chat')

    def _supervisor_turn(self, message, delegation=None, trigger='chat'):
        """One bounded supervisor call on the isolated worker (D-1, D-9, D-12)."""
        self._ensure_chat()
        config = supervision_lib.load_config(CONFIG_PATH)
        proc = getattr(self, 'proc', None)
        gate_question = (self.state == 'running' and bool(getattr(self, 'prompt_kind', ''))
                         and proc is not None and proc.poll() is None)
        running = bool(proc and proc.poll() is None)
        dialog = self._dialog_record()
        if delegation is not None and dialog is not None:
            delegation = dict(delegation, dialog_class=dialog.get('class'), dialog_kind=dialog.get('kind'),
                              answerable=bool(dialog.get('run')))
        steer_request = supervisor_chat.steer_intent(message) if trigger == 'chat' else None
        resend = trigger == 'chat' and supervisor_chat.send_intent(message)
        if resend:
            self.home_history.append(('user', sanitize(message)))
            self._resend_steering()
            return
        try:
            command, env, home = supervisor_command(config, ROOT)
        except (OSError, ValueError) as exc:
            raise ValueError('Supervisor unavailable: %s. Set supervision.runner claude in Configure and retry.'
                             % sanitize(str(exc)))
        root = _project_root()
        state_dir = os.path.join(root, '.uncle', 'workflow')
        known = supervision_lib.known_secret_values(os.environ, CONFIG_PATH)
        roots = [root]
        stage = getattr(self, 'status_stage', '')
        logs = supervisor_chat.gather_logs(state_dir, [stage, getattr(self, 'previous_stage', '')], roots, known)
        status = supervisor_chat.status_tail(getattr(self, 'status_path', None), [tempfile.gettempdir(), root], known)
        recovery = ''
        if getattr(self, 'recovery_active', False):
            recovery = supervision_lib.redact(
                supervision_lib.bounded_read(os.path.join(state_dir, 'TRIAGE.md'), roots, supervisor_chat.LOG_TAIL), known)
        extra = {}
        if dialog and dialog.get('file'):
            excerpt = supervision_lib.bounded_read(os.path.join(root, dialog['file']), roots, supervisor_chat.LOG_TAIL)
            if excerpt:
                extra['dialog_document'] = {'file': dialog['file'], 'excerpt': supervision_lib.redact(excerpt, known)}
        if not running:
            extra['home_actions'] = (home_action_prompt([], root) +
                                     '\nPut the action object in home_action within the supervisor reply envelope. '
                                     'A brief description is enough to request an app build. Structure it into the '
                                     'required Markdown sections; preserve all stated details. Set start=true '
                                     'when asked to build or create the app; do not ask for another confirmation.')
        user_text = self.chat.refs.expand(sanitize(message)) if trigger == 'chat' else sanitize(message)
        history = self.home_history + [('user' if trigger == 'chat' else 'system', user_text)]
        state = {'running': running, 'gate_pending': gate_question, 'stage': stage,
                 'previous_stage': getattr(self, 'previous_stage', ''), 'workflow_state': self._workflow_state(),
                 'recovery': bool(getattr(self, 'recovery_active', False)),
                 'standing_delegation': bool(self.delegation_session) or config.delegate_gates == 'routine'}
        context_delegation = dict(delegation or {'source': None}, steer_request=steer_request)
        prompt = supervisor_chat.compose_context(self._chat_contract(), user_text, history, dialog, context_delegation,
                                                 [{k: r.get(k) for k in ('id', 'stage', 'state', 'detail')}
                                                  for r in self.steer_records],
                                                 logs, status, supervisor_chat.cost_summary(state_dir), state,
                                                 recovery=recovery, extra=extra)
        if trigger == 'chat' and not issue_references(message):
            prompt += getattr(self, 'home_issue_context', '')
        self.chat_calls += 1
        meta = {'call_id': uuid.uuid4().hex, 'number': self.chat_calls, 'trigger': trigger,
                'deadline': config.call_timeout_seconds, 'workflow_state': self._workflow_state(), 'stage': stage}
        log = os.path.join(state_dir, 'logs', 'supervisor-chat-%d.jsonl' % self.chat_calls)
        lookup = None
        if trigger == 'chat' and not running and issue_references(message):
            lookup = lambda: issue_context(root, message)
        if trigger == 'chat':
            self.chat.send(message)
            self.chat_history.append(sanitize(message))
            self.chat_cursor = 0
            self.chat_history_index = -1
            self.chat_saved_draft = ''
            self._evict_chat_history()
        self.home_history = history
        # Use a worker that is already up; never start one here. Standing one
        # up belongs to startup, where it costs nothing anyone is waiting on.
        session = getattr(self, 'supervisor_session', None)
        if session is not None and not session.alive():
            session = None
        if session is not None:
            # The live worker owns the argv, environment and home it was started
            # with; a second set would answer in a different process.
            command, env, home = session.command, session.env, session.home
        if session is None:
            request = ChatRequest(command, prompt, env, home, log, meta, issue_lookup=lookup)
        else:
            request = ChatRequest(command, prompt, env, home, log, meta, issue_lookup=lookup,
                                  session=session)
        request.delegation = delegation
        request.dialog_id = (dialog['run'], dialog['prompt_id']) if dialog and dialog.get('run') else None
        request.steer_request = steer_request
        request.home_intent = trigger == 'chat' and supervisor_chat.home_intent(message)
        request.operator = message
        request.config = config
        self.home_request = request

    def _supervisor_session(self):
        """The long-lived supervisor worker, started once and kept.

        Spawned on first use and, because the homepage asks for it as the TUI
        comes up, that is before anyone has typed -- so the ~2s of process and
        connection setup is spent while the greeting is being read rather than
        in front of the first answer. Steady-state turns measured 1.3s against
        2.4s for a worker started per message.

        Returns None whenever a shared worker is not available, and every caller
        then uses the per-call path unchanged.
        """
        if os.environ.get('UNCLE_SUPERVISOR_SESSION') == '0':
            return None
        session = getattr(self, 'supervisor_session', None)
        if session is not None and session.alive():
            return session
        try:
            config = supervision_lib.load_config(CONFIG_PATH)
            command, env, home = supervisor_command(config, ROOT)
            session = supervisor_runner.SupervisorSession(command, env, home)
        except (OSError, ValueError):
            self.supervisor_session = None
            return None
        self.supervisor_session = session if session.alive() else None
        return self.supervisor_session

    def _warm_supervisor(self):
        """Startup thread: stand the worker up and spend its first-turn cost."""
        session = self._supervisor_session()
        if session is not None:
            session.prime()

    def _close_supervisor_session(self):
        session = getattr(self, 'supervisor_session', None)
        if session is not None:
            session.close()
            self.supervisor_session = None

    def _chat_contract(self):
        path = os.path.join(ROOT, 'prompts', 'supervise-chat.md')
        with open(path, encoding='utf-8') as fh:
            return fh.read()

    def _workflow_state(self):
        try:
            with open(os.path.join(_project_root(), '.uncle', 'workflow', 'state'), encoding='utf-8') as fh:
                raw = fh.readline().strip()
        except OSError:
            return ''
        return raw.split(':', 1)[1] if re.match(r'^[0-9]+:', raw) else raw

    def poll_chat_progress(self):
        """Show the supervisor's answer as it streams, not once it finishes.

        The runner writes stream-json to its log while the call runs, but the
        log was only parsed after the worker exited, so a sixteen-second reply
        showed nothing for sixteen seconds and then arrived whole. The bytes
        were always there; this reads them on the way past.

        The text never enters `home_history`: that list is replayed to the
        model as conversation, and a half-written sentence is not something it
        should be told it said.
        """
        request = getattr(self, 'home_request', None)
        if request is None:
            return False
        progress = getattr(request, 'progress', None)
        if progress is None:
            return False
        raw = getattr(self, '_chat_partial_raw', '')
        got = False
        try:
            while True:
                raw += progress.get_nowait()
                got = True
        except queue.Empty:
            pass
        if not got:
            return False
        self._chat_partial_raw = raw
        text = supervisor_chat.partial_reply(raw)
        if text == getattr(self, 'chat_partial', ''):
            return False
        self.chat_partial = text
        return True

    def poll_home_chat(self):
        request = getattr(self, 'home_request', None)
        if request is None:
            return False
        try:
            item = request.events.get_nowait()
        except queue.Empty:
            return False
        self.home_request = None
        # The finished reply replaces the streamed preview.
        self.chat_partial = ''
        self._chat_partial_raw = ''
        if isinstance(item, tuple):
            # Issue imports keep the homepage tuple protocol.
            kind, value = item
            if kind == 'issue_seeded':
                self.home_history.append(('system', sanitize(value)))
                self.chat_error = ''
            else:
                self.chat_error = sanitize(str(value))
            return True
        outcome = item
        context = getattr(request, 'issue_context', '')
        if isinstance(context, str) and context:
            self.home_issue_context = context
        self._record_chat_call(request, outcome)
        status = outcome.get('status')
        if status != 'reply':
            detail = sanitize(str(outcome.get('detail', '')))[:400]
            message = {'unavailable': 'Supervisor unavailable: configure supervision.runner',
                       'timeout': 'Supervisor call timed out after %ds' % (getattr(request, 'config', None).call_timeout_seconds
                                                                            if isinstance(getattr(request, 'config', None), supervision_lib.Config) else 0),
                       'cancelled': 'Supervisor call cancelled'}.get(status, 'Supervisor call failed')
            self.chat_error = message + (': ' + detail if detail else '') + '. The dialog is unchanged; retry.'
            self.home_history.append(('system', self.chat_error))
            return True
        try:
            parsed = supervisor_chat.parse_reply(outcome.get('reply', ''))
        except ValueError as exc:
            self.home_history.append(('supervisor', sanitize(str(outcome.get('reply', '')))[:8000]))
            self.chat_error = 'Supervisor reply did not follow the contract (%s); no action taken.' % sanitize(str(exc))
            self.home_history.append(('system', self.chat_error))
            return True
        if parsed['reply'].strip():
            self.home_history.append(('supervisor', sanitize(parsed['reply'])))
        self.chat_error = ''
        try:
            if parsed['gate_answer'] is not None:
                self._apply_gate_answer(request, parsed['gate_answer'])
            elif parsed['steer'] is not None:
                self._apply_steer(request, parsed['steer'])
            elif parsed['home_action'] is not None:
                self._apply_home_action(request, parsed['home_action'])
        except (OSError, ValueError) as exc:
            self.chat_error = sanitize(str(exc))
            self.home_history.append(('system', self.chat_error))
        return True

    def _record_chat_call(self, request, outcome):
        """AC-6: every chat call is measured separately from stage and diagnosis usage."""
        meta = getattr(request, 'meta', None)
        meta = meta if isinstance(meta, dict) else {}
        config = getattr(request, 'config', None)
        config = config if isinstance(config, supervision_lib.Config) else supervision_lib.load_config(CONFIG_PATH)
        try:
            supervision_lib.write_metric(
                os.path.join(_project_root(), '.uncle', 'workflow'), meta.get('number', 0), config.runner, config.model,
                config.effort, outcome.get('elapsed', 0), outcome.get('exit'), outcome.get('usage'), outcome.get('cost'),
                outcome.get('log', ''), meta.get('workflow_state', ''), outcome.get('usage_source'),
                error=outcome.get('status') != 'reply', usage_scope='supervisor chat',
                join={'call_id': meta.get('call_id'), 'trigger': meta.get('trigger'), 'supervised_stage': meta.get('stage'),
                      'outcome': outcome.get('status')})
        except OSError as exc:
            self.home_history.append(('system', 'Supervisor usage could not be recorded: ' + sanitize(str(exc))))

    def _apply_gate_answer(self, request, proposal):
        """SI-2/SI-3/SI-4: a stdin write needs TUI-decided delegation, the same
        driver-named prompt, a valid literal, and a persisted receipt, in that order."""
        delegation = getattr(request, 'delegation', None)
        answer = sanitize(proposal.get('answer', ''))
        rationale = sanitize(proposal.get('rationale', ''))
        if not delegation or delegation.get('source') not in ('explicit', 'standing'):
            self.home_history.append(('system', 'Recommendation only: the supervisor would answer %r (%s). '
                                                'Say "answer this one" to have it submitted.' % (answer, rationale[:200])))
            return
        dialog = self._dialog_record()
        if dialog is None or not dialog.get('run') or (dialog['run'], dialog['prompt_id']) != getattr(request, 'dialog_id', None):
            self.home_history.append(('system', 'Not sent: the dialog changed or closed before the supervisor replied '
                                                '(proposed %r). Ask again if it is still waiting.' % answer))
            return
        if delegation['source'] == 'standing' and dialog.get('class') == 'sensitive':
            self.home_history.append(('system', 'Not sent: this is a %s gate; standing delegation covers routine dialogs only. '
                                                'Say "answer this one" if you want the supervisor to answer it.'
                                      % (dialog.get('reason') or 'sensitive')))
            return
        if getattr(self, 'workflow_unattended', False) and dialog.get('reason') in ('publication', 'signing'):
            # Auto mode ended at the publication boundary: the PR dialogs are
            # the person's own answers, so no supervisor submission (explicit,
            # literal or choice) is written or receipted for them.
            self.home_history.append(('system', 'Not sent: this %s gate is the publication boundary of an Auto run; '
                                                'the supervisor proposed %r. Type the answer into the dialog yourself.'
                                      % (dialog.get('reason'), answer)))
            return
        if delegation.get('literal') is not None:
            answer = delegation['literal']
        elif delegation.get('choice') is not None:
            answer = delegation['choice']
        try:
            line = gate_answer.validate_answer(dialog['kind'], answer, dialog.get('choices') or ())
        except ValueError as exc:
            raise ValueError('Not sent: %s (proposed %r).' % (exc, answer))
        if self._triage_blocks_stdin():
            return
        state_dir = os.path.join(_project_root(), '.uncle', 'workflow')
        name = getattr(self, 'misc', {}).get('approval_name', '')
        try:
            record = gate_answer.write_envelope(state_dir, dialog['run'], dialog['prompt_id'], line, delegation['source'],
                                                name, delegation.get('request', ''), rationale, dialog['kind'],
                                                dialog['text'], delegation.get('config_key', ''),
                                                delegation.get('config_value', ''))
        except OSError as exc:
            raise ValueError('Not sent: the answer record could not be written (%s).' % exc)
        self.home_history.append(('supervisor', 'Answering %r on your request (%s): %s'
                                  % (line, record['attribution'], rationale or 'no rationale given')))
        if self.answer_prompt(line, how=record['attribution']):
            gate_answer.update_envelope(state_dir, dialog['run'], dialog['prompt_id'], 'delivered')
        else:
            gate_answer.discard_envelope(state_dir, dialog['run'], dialog['prompt_id'], 'stdin write failed')
            raise ValueError('The answer could not be written to the driver; nothing was recorded as answered.')

    def _apply_steer(self, request, steer):
        """SI-5: a steering delivery needs an operator steering request in this turn."""
        if not getattr(request, 'steer_request', None):
            self.home_history.append(('system', 'Recommendation only: the supervisor suggests steering the stage: %s. '
                                                'Say "tell it to ..." to have it relayed.' % sanitize(steer['text'])[:400]))
            return
        record = {'id': str(uuid.uuid4()), 'stage': getattr(self, 'status_stage', ''), 'text': sanitize(steer['text']),
                  'operator': sanitize(getattr(request, 'operator', '')), 'state': 'retained', 'detail': ''}
        self.steer_records.append(record)
        del self.steer_records[:-supervisor_chat.DELIVERY_STATES]
        self._deliver_steering(record)

    def _deliver_steering(self, record):
        stage = getattr(self, 'status_stage', '')
        channel = getattr(self, 'steering_channels', {}).get(stage)
        if not channel or not self.proc or self.proc.poll() is not None or getattr(self, 'workflow_exit_reported', False):
            record['state'] = 'retained'
            record['detail'] = 'no live steering channel'
            self.steer_retained = record
            self.home_history.append(('system', 'Steering not delivered; retained (no live channel for %s). '
                                                'Say "send it" once the stage accepts steering.' % (stage or 'the stage')))
            return False
        payload = supervisor_chat.steer_payload(record['text'])
        if len(payload.encode('utf-8')) > 60000:
            record['state'] = 'failed'
            record['detail'] = 'payload exceeds 60 KB'
            raise ValueError('Steering not delivered: the instruction exceeds 60 KB; it was retained.')
        record['id'] = str(uuid.uuid4())
        record['stage'] = stage
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=channel)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'id': record['id'], 'text': payload}, stream)
            os.replace(temporary, os.path.join(channel, str(time.time_ns()) + '-' + record['id'] + '.json'))
        except OSError as exc:
            record['state'] = 'failed'
            record['detail'] = str(exc)[:200]
            self.steer_retained = record
            raise ValueError('Steering not delivered (%s); retained. Say "send it" to retry.' % exc)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        record['state'] = 'queued'
        self.steer_retained = None
        self.home_history.append(('system', 'Steering %s queued for %s' % (record['id'][:8], stage)))
        host = getattr(self, 'supervision_host', None)
        if host is not None:
            host.controller.steering_queued(stage, record['id'], payload)
        return True

    def _resend_steering(self):
        record = getattr(self, 'steer_retained', None)
        if record is None:
            self.home_history.append(('system', 'Nothing is retained to send.'))
            return
        self._deliver_steering(record)

    def _apply_home_action(self, request, action):
        proc = getattr(self, 'proc', None)
        running = self.state == 'running' or bool(proc and proc.poll() is None)
        if running:
            self.home_history.append(('system', 'Ignored: homepage actions cannot run while a workflow is active.'))
            return
        if not getattr(request, 'home_intent', False):
            self.home_history.append(('system', 'Recommendation only: the supervisor proposed %s. Ask to build, '
                                                'draft or start it to run the action.' % sanitize(str(action.get('uncle_action')))))
            return
        parsed = parse_home_action(json.dumps(action))
        if parsed is None:
            raise ValueError('The supervisor proposed an invalid homepage action.')
        self._home_action(parsed)

    def poll_delegation(self):
        """SB-7: standing delegation answers a routine, driver-named dialog once as it opens."""
        if not getattr(self, 'prompt_kind', '') or getattr(self, 'home_request', None) is not None:
            return False
        if self.state != 'running' or not self.proc or self.proc.poll() is not None:
            return False
        dialog = self._dialog_record()
        if dialog is None or not dialog.get('run') or dialog.get('class') != 'routine':
            return False
        key = (dialog['run'], dialog['prompt_id'])
        if key in self.standing_answered:
            return False
        config = supervision_lib.load_config(CONFIG_PATH)
        session = getattr(self, 'delegation_session', None)
        if config.delegate_gates != 'routine' and not session:
            return False
        self.standing_answered.add(key)
        if self.standing_calls >= config.max_calls_per_run:
            self.home_history.append(('system', 'Standing delegation paused: supervision.max_calls_per_run (%d) reached; '
                                                'this dialog is yours.' % config.max_calls_per_run))
            return True
        self.standing_calls += 1
        if session:
            delegation = {'source': 'standing', 'request': session['request'], 'choice': None, 'literal': None,
                          'config_key': '', 'config_value': ''}
        else:
            delegation = {'source': 'standing', 'request': 'supervision.delegate_gates routine', 'choice': None,
                          'literal': None, 'config_key': 'supervision.delegate_gates', 'config_value': 'routine'}
        try:
            self._supervisor_turn('Standing delegation: answer this routine dialog (%s).' % dialog['kind'],
                                  delegation=delegation, trigger='standing_gate')
        except (OSError, ValueError) as exc:
            self.chat_error = sanitize(str(exc))
            self.home_history.append(('system', self.chat_error))
        return True

    def _home_action(self, action, replace_approved=False):
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
                draft = Conversation(root)
                draft.kind = kind
                document = action['document']
                if kind == 'app' and not re.search(r'^## ', document, re.M):
                    # Plain descriptions are valid app seeds; do not force users
                    # to supply the internal Markdown section schema.
                    document = '# Application brief\n\n' + '\n\n'.join(
                        '## ' + field + '\n' + (document.strip() if field == 'Summary' else
                        'Not specified in the brief.' if field == 'Open questions' else 'None')
                        for field in Conversation.fields['app'])
                draft.preview = sanitize(document)
                target = Path(root) / filename
                backup = None
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise ValueError(filename + ' must be a regular file.')
                if target.exists() and not replace_approved:
                    self.home_replace_proposal = dict(action)
                    self.home_history.append(('system', draft.preview))
                    self.home_history.append(('system', 'Proposal: replace ' + filename +
                        ' with the brief above' + (' and start the workflow' if action['start'] else '') +
                        '. The previous file will be archived.\n'
                        'Waiting for your decision: type "approve replacement" or "decline replacement".'))
                    return
                if target.exists():
                    history = Path(root) / '.uncle' / 'brief-history'
                    history.mkdir(parents=True, exist_ok=True)
                    backup = Path(tempfile.mkdtemp(prefix='brief-', dir=history)) / filename
                    target.rename(backup)
                try:
                    draft.commit()
                except Exception:
                    if backup is not None and not target.exists():
                        backup.rename(target)
                    raise
                if backup is not None:
                    self.home_history.append(('system', 'Previous ' + filename + ' saved to ' + str(backup)))
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

    def _handle_startup_action(self):
        if self.state == 'running' or (getattr(self, 'proc', None) and self.proc.poll() is None):
            raise ValueError('A workflow is already active.')
        root = _project_root()
        try:
            if self._startup_action == 'create_app':
                req_path = Path(root) / 'REQUIREMENTS.md'
                if req_path.exists():
                    action_type = 'create_change'
                else:
                    action_type = 'create_app'
                action = {
                    'uncle_action': action_type,
                    'document': self._startup_text,
                    'start': True,
                    'message': 'Starting ' + ('change' if action_type == 'create_change' else 'application') + ' build'
                }
                self._home_action(action, replace_approved=True)
            elif self._startup_action == 'github_issue':
                action = {
                    'uncle_action': 'github_issue',
                    'issue': self._startup_text,
                    'start': True,
                    'message': 'Starting GitHub issue build'
                }
                self._home_action(action, replace_approved=True)
            else:
                raise ValueError('Unknown startup action: ' + str(self._startup_action))
        finally:
            self._startup_action = None
            self._startup_text = None

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
            self.triage_stream = ''

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
        if NO_EDIT_PROPOSAL.search(chosen[0][1]):
            self._triage_apply_local(chosen[0])
        else:
            self._triage_turn('execute', proposal=chosen[0])

    def _triage_apply_local(self, proposal):
        """A proposal that needs no edit never pays for the master: the guard
        verifies the untouched tree and the resume offer opens at once."""
        root = _project_root()
        wf = self._workflow_dir()
        turn = self.triage_turn + 1
        try:
            info = self._triage_guard('begin', '--state-dir', wf, '--project', root, '--root', ROOT,
                                      '--turn', str(turn), '--mode', 'execute')
            summary = self._triage_guard('end', '--state-dir', wf, '--project', root, '--root', ROOT,
                                         '--turn', str(turn), '--mode', 'execute',
                                         '--digest', info['digest'],
                                         '--proposal', 'Proposal %d: %s' % proposal)
        except (OSError, ValueError, KeyError) as exc:
            # The cheap path could not verify the tree; the master turn handles it.
            self._triage_turn('execute', proposal=proposal)
            return
        self.triage_turn = turn
        self.triage_proposals = []
        self.triage_history.append(('operator', '/do %d — %s' % (proposal[0], sanitize(proposal[1]))))
        notes = []
        if summary.get('applied'):
            notes.append('Applied: ' + ', '.join(summary['applied']))
        if summary.get('refused'):
            notes.append('Refused and reverted: ' + ', '.join(summary['refused']))
        if summary.get('failed'):
            notes.append('Not applied: ' + ', '.join(summary['failed']))
        if summary.get('no_edit'):
            notes.append('No files changed.')
        notes.extend(summary.get('messages', []))
        if summary.get('tainted'):
            self.triage_tainted = 'Resume refused: ' + ' '.join(summary.get('messages') or ['the guard could not verify the tree.'])
        if notes:
            self.triage_history.append(('system', sanitize(' '.join(notes))))
        if not summary.get('tainted'):
            self.triage_offer_resume = True
        if getattr(self, 'recovery_active', False):
            self.chat_error = ''

    def poll_triage(self):
        request = getattr(self, 'triage_request', None)
        if request is None:
            return False
        try:
            kind, value = request.events.get_nowait()
        except queue.Empty:
            return False
        if kind == 'delta':
            self.triage_stream = value
            return True
        self.triage_request = None
        self.triage_stream = ''
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

    def _is_known_stage(self, name):
        """True when this project's workflow really has a stage by that name.

        Without the word "stage" to anchor on, "rerun the tests" would otherwise
        be read as a stage request. Unknown names belong to the supervisor.
        """
        try:
            from rerun_stage import APP, CHANGE
            family = (Path(_project_root()) / '.uncle/workflow/family').read_text().strip()
        except (OSError, ImportError, ValueError):
            return False
        return name in (CHANGE if family == 'change' else APP)

    def run_named_stage(self, stage):
        from rerun_stage import APP, CHANGE
        if getattr(self, 'proc', None) and self.proc.poll() is None:
            raise ValueError('Stop the active workflow before running another stage.')
        if getattr(self, 'home_request', None) or getattr(self, 'triage_request', None):
            raise ValueError('Wait for the current chat request to finish.')
        root = Path(_project_root())
        directory = root / '.uncle/workflow'
        family = (directory / 'family').read_text().strip()
        choices = CHANGE if family == 'change' else APP
        stage = stage.strip().lower()
        if stage not in choices:
            raise ValueError('Usage: /run STAGE. Available: ' + ', '.join(choices))
        if not (directory / 'state').is_file():
            raise ValueError('Start a workflow before selecting a stage.')
        # Replace, do not refuse. This was an exclusive create, so a request the
        # driver never consumed -- it failed to start, or stopped before
        # reaching the state machine -- stranded the file and made every later
        # /run fail with a raw "File exists" errno naming a path the operator
        # had no reason to know about. No driver is running (checked above), so
        # the newest request is simply the one that counts.
        request = directory / 'rerun-request.json'
        pending = directory / 'rerun-request.json.pending'
        try:
            with pending.open('w') as stream:
                json.dump({'stage': stage, 'source': 'explicit-user-request'}, stream)
            os.replace(pending, request)
        except OSError as failure:
            pending.unlink(missing_ok=True)
            raise ValueError('Could not request the %s rerun: %s' % (stage, failure))
        self.workflow_idx = 2 if family == 'change' else 0
        self.new_workflow_pending = False
        self.home_history.append(('system', 'Requested rerun of ' + stage + '.'))
        self._run()

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

    def _clear_workflow_identity(self):
        directory = Path(_project_root()) / '.uncle' / 'workflow'
        for name in ('state', 'origin'):
            (directory / name).unlink(missing_ok=True)

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
                    self._clear_workflow_identity()
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
            proposal = bool(re.search(r'(?im)^\s*(?:\*\*)?Proposal(?:\s+\d+)?\s*:', str(text)))
            for i, line in enumerate(str(text).splitlines() or ['']):
                lines.extend((part, curses.A_BOLD if proposal else curses.A_NORMAL) for part in
                             (textwrap.wrap(('%s: ' % role if i == 0 else '') + line, max(1, w - 2)) or ['']))
            lines.append(('', curses.A_NORMAL))
        if self.triage_stream:
            # The reply forming: shown as it lands, replaced by the final text.
            for i, line in enumerate(self.triage_stream.splitlines() or ['']):
                lines.extend((part, curses.A_NORMAL) for part in
                             (textwrap.wrap(('master: ' if i == 0 else '') + line, max(1, w - 2)) or ['']))
            lines.append(('', curses.A_NORMAL))
        bottom = h - 5
        rows = max(0, bottom - 3)
        end = max(0, len(lines) - self.triage_scroll)
        for i, (line, attr) in enumerate(lines[max(0, end - rows):end]):
            put(3 + i, 0, line, w, attr)
        if self.triage_proposals:
            offer = 'Select: ' + '  '.join('[%d] %s' % (n, body[:max(1, w // 3)]) for n, body in self.triage_proposals)
        else:
            offer = 'No proposal is selectable.'
        if self.triage_offer_resume:
            offer += '  [r] resume'
        put(h - 4, 0, offer, w, curses.A_BOLD)
        put(h - 3, 0, self.triage_error, w)
        put(h - 2, 0, 'Triage> ' + self.triage_composer[-max(1, w - 10):], w)
        put(h - 1, 0, '1-3 select proposal | r resume | Esc back | /do N /resume /clear | text = follow-up question', w)
        self.stdscr.refresh()

    def chat_attr(self, role, base=0):
        """Attribute for one chat row, keyed by the stored history role only (never by text)."""
        role = str(role).lower()
        if role in ('user', 'proposal'):
            return base | curses.A_BOLD
        if role == 'supervisor':
            return getattr(self, 'color', {}).get('emphasis', curses.A_REVERSE)
        return base

    def chat_entries(self):
        """`chat_display()` rows paired with the role that produced each one."""
        recovery = getattr(self, 'triage_history', [])
        seen = getattr(self, '_recovery_displayed', 0)
        for role, text in recovery[seen:]:
            self.home_history.append(('Recovery' if role == 'master' else 'User' if role == 'operator' else 'System', text))
        self._recovery_displayed = len(recovery)
        history = getattr(self, 'home_history', [])
        rows = [('proposal' if str(role).lower() != 'user' and re.search(r'(?im)^\s*(?:\*\*)?Proposal(?:\s+\d+)?\s*:', text) else role,
                 str(role).capitalize() + ': ' + text) for role, text in history]
        if not rows:
            rows = [(None, line) for line in self.chat.messages]
        partial = getattr(self, 'chat_partial', '')
        if partial and getattr(self, 'home_request', None) is not None:
            rows = rows + [('supervisor', 'Supervisor: ' + partial)]
        return rows

    def chat_display(self):
        return [line for _, line in self.chat_entries()]

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
            self.chat_cursor = len(self.chat_composer)
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
            self.chat_cursor = len(self.chat_composer)
            self.chat_choices = choices
            self.chat_pick = 0
        else:
            reference = self.chat.refs.reference(name)
            self.chat_composer = self.chat_composer[:self.chat_ref_start] + reference + ' '
            self.chat_cursor = len(self.chat_composer)
            self.chat_choices = []
            self.chat_picker = False
        self.chat_error = ''

    def _chat_history_size(self):
        """Return aggregate byte size of chat_history + chat_composer."""
        total = 0
        for msg in getattr(self, 'chat_history', []):
            total += len(msg.encode('utf-8'))
        total += len(getattr(self, 'chat_composer', '').encode('utf-8'))
        return total

    def _evict_chat_history(self):
        """Drop oldest history entries until total bytes < 1 MiB (1048576)."""
        limit_bytes = 1048576
        while self._chat_history_size() >= limit_bytes and self.chat_history:
            self.chat_history.pop(0)

    def _move_cursor(self, delta):
        """Move cursor by delta, clamped to bounds."""
        text = getattr(self, 'chat_composer', '')
        new_pos = max(0, min(len(text), self.chat_cursor + delta))
        self.chat_cursor = new_pos

    def _move_by_word(self, forward):
        """Move cursor to next word boundary. forward=True moves forward, False moves backward."""
        text = getattr(self, 'chat_composer', '')
        if not text:
            return
        pos = self.chat_cursor
        if forward:
            while pos < len(text) and not text[pos].isspace():
                pos += 1
            while pos < len(text) and text[pos].isspace():
                pos += 1
        else:
            if pos > 0:
                pos -= 1
            while pos > 0 and text[pos].isspace():
                pos -= 1
            while pos > 0 and not text[pos - 1].isspace():
                pos -= 1
        self.chat_cursor = pos

    def _chat_key(self, k):
        if k == 27 and getattr(self, 'recovery_active', False):
            self.recovery_active = False
            self.chat_focus = 'gate' if self.state == 'running' and self.prompt_kind else 'chat'
            self.chat_error = ''
            return True
        if k == 27 and self.state == 'running' and getattr(self, 'workflow_exit_reported', False):
            # Esc used to leave for the home page the moment a run ended, so a
            # stray keypress discarded the finished build's screen. Clear the
            # transient state and stay; /homepage is how you leave.
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
            if not self.chat_choices and k in (curses.KEY_UP, curses.KEY_DOWN):
                if self.chat_history:
                    idx = self.chat_history_index
                    if k == curses.KEY_UP:
                        if idx == -1:
                            self.chat_saved_draft = self.chat_composer
                            idx = len(self.chat_history) - 1
                        else:
                            idx = max(-1, idx - 1)
                    elif idx != -1:
                        idx = idx + 1 if idx + 1 <= len(self.chat_history) - 1 else -1
                    self.chat_history_index = idx
                    self.chat_composer = self.chat_saved_draft if idx == -1 else self.chat_history[idx]
                    self.chat_cursor = len(self.chat_composer)
                return True
            if k in (10, 13):
                # A complete numeric mention is already usable, even while the
                # asynchronous picker is loading or has no matching results.
                if (self.chat_picker and getattr(self, 'chat_picker_kind', 'file') == 'issue'
                        and re.search(r'(?<!\S)#[1-9][0-9]*\s*$', self.chat_composer)):
                    self.chat_picker = False
                    self.chat_choices = []
                if self.chat_choices:
                    self._complete_chat_file()
                elif self.chat_picker:
                    self.chat_error = (self.issue_picker.message or 'No matching open issues.') if getattr(self, 'chat_picker_kind', 'file') == 'issue' else 'No matching files. Keep typing or press Esc to close.'
                elif self.chat_edit:
                    self.chat_composer += '\n'
                    self.chat_cursor = len(self.chat_composer)
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
                self.chat_cursor = len(self.chat_composer)
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
                if self.chat_cursor > 0:
                    self.chat_composer = self.chat_composer[:self.chat_cursor - 1] + self.chat_composer[self.chat_cursor:]
                    self.chat_cursor -= 1
            elif k == curses.KEY_LEFT:
                self._move_cursor(-1)
            elif k == curses.KEY_RIGHT:
                self._move_cursor(1)
            elif k in (curses.KEY_HOME, 1):  # Ctrl-A
                self.chat_cursor = 0
            elif k in (curses.KEY_END, 5):  # Ctrl-E
                self.chat_cursor = len(self.chat_composer)
            elif k in (curses.KEY_SLEFT, 2):  # Ctrl-B fallback
                self._move_by_word(forward=False)
            elif k in (curses.KEY_SRIGHT, 6):  # Ctrl-F fallback
                self._move_by_word(forward=True)
            elif 32 <= k <= 0x10ffff and k < curses.KEY_MIN:
                if len(self.chat_composer.encode('utf-8')) >= 1024 * 1024:
                    raise ValueError('Transcript exceeds 1 MiB limit')
                self.chat_history_index = -1
                char = chr(k)
                self.chat_composer = self.chat_composer[:self.chat_cursor] + char + self.chat_composer[self.chat_cursor:]
                self.chat_cursor += 1
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
                    'input': 'type, Enter', 'support': 's/Enter', 'complete': 'Enter'}
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
        commands = ['/homepage', '/configure', '/settings', '/file', '/quit', '/issue', '/requirements', '/change', '/approve', '/clear', '/triage', '/do', '/resume', '/run', '/delegate', '/app-input']
        text = self.chat_composer.lower()
        return [command for command in commands if command.startswith(text)] if text.startswith('/') and ' ' not in text else []

    def _chat_command(self, k):
        choices = self._slash_choices()
        if choices and k in (curses.KEY_UP, curses.KEY_DOWN):
            self.slash_pick = (getattr(self, 'slash_pick', 0) + (1 if k == curses.KEY_DOWN else -1)) % len(choices)
            return True
        if choices and k in (10, 13) and self.chat_composer.lower() not in choices:
            self.chat_composer = choices[getattr(self, 'slash_pick', 0) % len(choices)]
            self.chat_cursor = len(self.chat_composer)
            if self.chat_composer in ('/issue', '/run'):
                self.chat_composer += ' '
                self.chat_cursor = len(self.chat_composer)
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
            if argument and command not in ('/issue', '/do', '/run', '/delegate', '/app-input'):
                self.chat_error = command + ' does not take arguments'
                return True
            if command == '/run':
                try:
                    self.run_named_stage(argument)
                    self.chat_composer = ''
                except (OSError, ValueError) as exc:
                    self.chat_error = str(exc)
                return True
            if command == '/delegate':
                self.chat_composer = ''
                self.chat_choices = []
                self.chat_error = ''
                self._delegate_command(argument.lower())
                return True
            if command == '/app-input':
                self.chat_composer = ''
                self.chat_choices = []
                preview = getattr(self, 'completion_preview', None)
                if preview and preview.kind == 'command' and preview.process and preview.process.poll() is None:
                    preview.send(argument)
                    self.chat_error = ''
                    self.home_history.append(('system', 'Sent to the running application: ' + sanitize(argument)[:200]))
                else:
                    self.chat_error = 'No running application preview accepts input.'
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
            if command == '/homepage':
                # The build page no longer leaves on its own, so leaving is a
                # command. Stopping first keeps a live run from being orphaned.
                self.stop_workflow()
                self.state = 'menu'
                self.sel = 0
                self.prompt_kind = ''
                self.prompt_text = ''
                self.recovery_active = False
                self.chat_focus = 'chat'
                self.chat_composer = ''
                self.chat_error = ''
                self.chat_picker = False
                self.chat_choices = []
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
                try:
                    self._clear_workflow_identity()
                except OSError as exc:
                    self.chat_error = 'Could not clear workflow state/origin: ' + str(exc)
                    return True
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
                self.chat_error = 'Commands: /configure /settings /file /quit /issue # /requirements /change /approve /clear /triage /do N /resume /delegate on|off|status /app-input TEXT'
            return True
        return False

    def _delegate_command(self, argument):
        """Session standing delegation for routine dialogs; config `delegate_gates` is the persistent form."""
        self._ensure_chat()
        config = supervision_lib.load_config(CONFIG_PATH)
        if argument == 'on':
            self.delegation_session = {'request': '/delegate on', 'granted': int(time.time())}
            self.home_history.append(('system', 'Standing delegation granted for routine dialogs this session; '
                                                'sensitive gates still need an explicit ask.'))
        elif argument == 'off':
            self.delegation_session = None
            self.home_history.append(('system', 'Session standing delegation revoked.'
                                      + (' supervision.delegate_gates routine still applies from .uncle/config.'
                                         if config.delegate_gates == 'routine' else '')))
        elif argument in ('', 'status'):
            source = ('session (%s)' % self.delegation_session['request'] if self.delegation_session
                      else 'config (supervision.delegate_gates routine)' if config.delegate_gates == 'routine' else 'none')
            self.home_history.append(('system', 'Standing delegation: %s. Sensitive gates (signing, publication, waiver) '
                                                'always need an explicit ask.' % source))
        else:
            self.chat_error = 'Usage: /delegate on | off | status'

    def _draw_homepage(self, h, w):
        """Centered, prompt-first landing screen; workflow rendering is separate."""
        color = getattr(self, 'color', {})
        items = self.menu_items()
        entries = self.chat_entries()
        if self.chat.preview:
            entries += [('preview', 'Preview: '), ('preview', self.chat.preview)]
        pending = getattr(self, 'home_replace_proposal', None)
        if pending:
            filename = 'REQUIREMENTS.md' if pending['uncle_action'] == 'create_app' else 'CHANGE_REQUEST.md'
            entries.append(('proposal', 'Replace ' + filename + '? Previous file will be archived.'))
            entries.append(('proposal', 'Type "approve replacement" or "decline replacement".'))
        history = [line for _, line in entries]
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
        # The homepage is the menu and the prompt. Listing every worktree run
        # here put a growing block of paths above both -- and now that an issue
        # run takes its own worktree by default, that list only gets longer.
        # `scripts/lib/worktree_runs.py` still prints it on demand.
        run_y = bar_y + 1
        # The decorative logo yields its rows to the bar before the prompt does.
        logo_fits = w >= LOGO_W + 4 and h >= len(LOGO) + footer_rows + run_y
        logo = LOGO if logo_fits and not history else []
        body_rows = len(LOGO) if logo_fits else 0
        if h < 18:
            body_rows = 0
        top = max(run_y, (h - body_rows - footer_rows) // 2)
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
            joined = '\n'.join(history)
            tail = joined[-max(1, width * body_rows * 2):]
            # Each surviving line takes the role of the entry that owns its first
            # character; the text itself is cut and split exactly as before.
            spans = []
            start = 0
            for role, line in entries:
                spans.append((start, role))
                start += len(line) + 1
            offset = len(joined) - len(tail)
            lines = []
            for line, raw in zip(tail.splitlines(), tail.splitlines(keepends=True)):
                role = next((r for s, r in reversed(spans) if s <= offset), None)
                offset += len(raw)
                lines.extend((role, part) for part in textwrap.wrap(line, width) or [''])
            room = max(0, body_rows - 1)
            for i, (role, line) in enumerate(lines[-room:] if room else []):
                put(top + 1 + i, line, self.chat_attr(role, color.get('accent', 0)))
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
        if build:
            hint = ('/homepage to leave   / commands   @ files   # issues   Tab to chat' if width >= 66
                    else '/homepage   / cmds  @ files  # issues  Tab chat' if width >= 48
                    else '/homepage  / cmds  Tab chat' if width >= 28 else '/homepage')
        else:
            hint = ('/homepage   / commands   @ files   # issues   Ctrl-P menu  Tab to chat' if width >= 72
                    else '/ commands   @ files   # issues   Ctrl-P menu  Tab to chat' if width >= 60
                    else '/ cmds  @ files  # issues  Ctrl-P menu  Tab chat' if width >= 52
                    else '/ cmds @ files Ctrl-P menu Tab chat' if width >= 35
                    else '@ files  Ctrl-P menu Tab chat' if width >= 29 else 'Ctrl-P menu')
        put(row + (1 if compact else 3), hint, color.get('muted', curses.A_DIM), not build)
        put(row + (2 if compact else 5), '─' * width, color.get('muted', curses.A_DIM))
        text = sanitize(self.chat_composer).replace('\n', ' / ').expandtabs(4).lstrip()
        placeholder = 'Ask about the failure · /do N · /resume' if getattr(self, 'recovery_active', False) else 'Talk to uncle while he builds' if self.state == 'running' else 'Describe an app or a change…'
        if self.state == 'running' and getattr(self, 'prompt_kind', '') and self.chat_focus == 'chat':
            placeholder = 'Ask a question · Tab returns to the pending dialog'
        composer_row = row + (3 if compact else 6)
        wrap_width = max(8, width - 2)
        # The composer grows as the input wraps; long pastes scroll to the tail.
        all_chunks = self._wrap_input(text, wrap_width)
        viewport_n = max(1, min(6, h - composer_row - 3))
        viewport_start = max(0, len(all_chunks) - viewport_n)
        chunks = all_chunks[viewport_start:]
        extra = len(chunks) - 1 if text else 0
        if text:
            for i, chunk in enumerate(chunks):
                put(composer_row + i, ('› ' if i == 0 else '  ') + chunk, color.get('accent', 0))
        else:
            put(composer_row, '› ' + placeholder, color.get('muted', curses.A_DIM))
        put(composer_row, '›', color.get('warning', curses.A_BOLD))
        if self.chat_focus == 'chat' and (self.state != 'menu' or not getattr(self, 'home_menu_open', False)):
            prefix = sanitize(self.chat_composer[:self.chat_cursor]).replace('\n', ' / ').expandtabs(4).lstrip()
            prefix_chunks = self._wrap_input(prefix, wrap_width) if prefix else []
            cursor_chunk_idx = len(prefix_chunks) - 1 if prefix_chunks else 0
            cursor_col = len(prefix_chunks[-1]) if prefix_chunks else 0
            if cursor_chunk_idx >= viewport_start:
                cursor_y = composer_row + (cursor_chunk_idx - viewport_start)
                cursor_x = left + 2 + cursor_col
            else:
                cursor_y = composer_row
                cursor_x = left + 2
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
        project_status = project + '  ·  ' + ('mode(auto)' if auto else 'mode(manual)')
        if build:
            # Only shown while checks are actually running. "Tests: Stopped"
            # was on screen for most of every run and read as a fault, when it
            # only ever meant "no check is executing this second".
            tests = self.test_execution_status()
            if tests:
                model_status = 'Tests: ' + tests + '  ·  ' + model_status
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
        entries = self.chat_entries()
        chat = [line for _, line in entries]
        roles = {'chat': [role for role, _ in entries]}
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
            # Each row keeps the history role that produced it, so styling
            # survives replacement, eviction, and mocked string-only callers.
            kind_roles = roles.get(kind, [])
            messages.extend((kind, i, line, kind_roles[i] if i < len(kind_roles) else None)
                            for i, line in enumerate(current[common:], common))
        self._message_snapshot = (output, chat)
        self._message_stream = messages[-4000:]
        return [item[2] for item in self._message_stream]

    def _draw_running(self, h, w):
        if self.state == "viewer":
            self._draw_viewer(h, w)
            return
        tail = self._build_messages()
        stream = getattr(self, '_message_stream', [])
        # Roles come from the stored stream; a mocked string-only
        # `_build_messages` has no matching stream and draws unstyled.
        roles = ([item[3] if len(item) > 3 else None for item in stream]
                 if len(stream) == len(tail) else [None] * len(tail))
        if self.partial.strip() and not self.prompt_kind:
            tail.append(self.partial.rstrip())
            roles.append(None)
        # The transcript uses every column before the sidebar, independently
        # of the centered composer's narrower width.
        screen_width = self.stdscr.getmaxyx()[1]
        message_width = max(1, min(w, screen_width - 1))
        wrapped = []
        for message, role in zip(tail, roles):
            for line in message.splitlines() or ['']:
                wrapped.extend((role, part) for part in textwrap.wrap(line, message_width) or [''])
        rows = max(0, h - 1)
        self.build_page_rows = max(1, rows)
        offset = getattr(self, 'build_scroll', 0)
        if offset:
            offset += max(0, len(wrapped) - getattr(self, 'build_wrapped_count', len(wrapped)))
        self.build_wrapped_count = len(wrapped)
        self.build_scroll = min(offset, max(0, len(wrapped) - rows))
        end = len(wrapped) - self.build_scroll
        for i, (role, line) in enumerate(wrapped[max(0, end - rows):end] if rows else []):
            try:
                self.stdscr.addnstr(i, 0, line, message_width, self.chat_attr(role))
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
        elif self.prompt_kind == "complete":
            footer = "[Enter] return to home"
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
        title = {"confirm": " approve ", "enter": " review ", "input": " input ", "support": " support Uncle ", "finished": " Finished ",
                 "complete": " build complete "}.get(
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
        # Scroll transcript before the composer can consume navigation keys.
        # Dialog-focused navigation remains owned by the dialog.
        if self.state == 'running' and (not getattr(self, 'prompt_kind', '') or
                                       getattr(self, 'chat_focus', '') == 'chat'):
            if k in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                step = getattr(self, 'build_page_rows', 10)
                self.build_scroll = max(0, getattr(self, 'build_scroll', 0) +
                                        (step if k == curses.KEY_PPAGE else -step))
                return
            if k == curses.KEY_END and getattr(self, 'chat_focus', '') != 'chat':
                self.build_scroll = 0
                return
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
        # A finished build's only way back is through its dialog; chat must
        # not see these keys, or Esc there would jump straight to the menu.
        if self.state == "running" and getattr(self, "prompt_kind", "") == "complete":
            self._complete_key(k)
            return
        if k == 27 and self._back_from_build():
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
                    self.config_section = ("stages", "opencode", "misc", "supervision", "recovery")[self.config_sel]
                    self.config_sel = self.config_scroll = 0
                elif section == "supervision":
                    self._supervision_enter()
                elif section == "misc":
                    if self.config_sel == 0:
                        self._set_field("!misc", "auto_mode", "false" if self.misc.get("auto_mode") == "true" else "true")
                    elif self.config_sel == 1:
                        self._open_picker("approval_name", "!misc")
                    else:
                        self._open_picker("markdown_viewer", "!misc")
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
            self.state = "config" if self.picker_target == "!misc" else "stage"
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
            val = self.input_buf if self.picker_kind == "markdown_viewer" else self.input_buf.strip()
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
        # Before the state flips: everything after this reads _project_root(),
        # and it must already name the directory the run will happen in.
        # A rerun happens where its request was written. Relocating first left
        # the request in the old project root while the driver started in a new
        # worktree, which never saw it -- so "rerun final-audit" became a fresh
        # build from DERIVE_BRIEF in a directory named after an unrelated brief.
        if not self._rerun_pending():
            self._enter_run_worktree()
        self.state = "running"
        self.start_workflow()

    def _quit(self):
        if getattr(self, "completion_preview", None):
            self.completion_preview.close()
        self._close_early_preview()
        self._close_supervisor_session()
        self.state = "quit"

    # ---- main loop ----
    def run(self):
        previous_term = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, terminate)
        # Started before the first keystroke, on a thread so a slow or missing
        # runner delays nothing: the cost of standing the worker up is paid
        # while the homepage is being read instead of in front of the first
        # answer. A failure here is not an error -- the per-call path remains.
        threading.Thread(target=self._warm_supervisor, daemon=True).start()
        try:
            self._run_loop()
        finally:
            self._close_supervisor_session()
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
        # Inject startup action on first frame if present
        if self._startup_action and not self._startup_injected:
            self._startup_injected = True
            try:
                self._handle_startup_action()
                dirty = True
            except Exception as exc:
                self.home_history.append(('system', 'Startup action failed: %s. Try again or pick from menu.' % sanitize(str(exc))))
                dirty = True
        while self.state != "quit":
            dirty = self.poll_chat_progress() or dirty
            dirty = self.poll_home_chat() or dirty
            dirty = self.poll_delegation() or dirty
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
