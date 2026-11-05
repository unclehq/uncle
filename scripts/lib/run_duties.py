"""Run duties shared by the TUI and the headless (--noui) runner.

Pure functions only: no curses, no process spawning. This module is the single
home of the completion-banner literals and the Finished-build line format that
uncle_tui.py's finished-line parser matches (moved verbatim).
"""
import os
import shlex

# Exact strings the driver prints on completion (verbatim from the TUI parser).
COMPLETION_BANNERS = (
    "Workflow complete.",
    "Change workflow complete.",
    "Workflow complete with waived acceptance.",
    "Change workflow complete with waived acceptance.",
)

# Finished-build line format and the prefixes the parser matches.
FINISHED_LINE_FORMAT = "Finished build: verdict={verdict} skipped={skipped} path={path}"
FINISHED_START_PREFIXES = ("Finished build:", "READY - ", "NOT READY - ")
FINISHED_CONTINUATION_PREFIXES = ("Total time:", "PR:")

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_BLOCKED = 3
EXIT_FAILED = 1

APP_BRIEF_FIELD_PLACEHOLDER = "Not specified in the brief."


def format_finished_line(verdict="UNKNOWN", skipped=0, path=""):
    return FINISHED_LINE_FORMAT.format(verdict=verdict, skipped=skipped, path=path)


def is_completion_banner(line):
    return str(line).strip() in COMPLETION_BANNERS


class BannerCollector:
    """Collects finished-build lines and completion from driver output lines."""

    def __init__(self):
        self.finished_lines = []
        self.completed = False
        self._in_block = False

    def feed(self, line):
        text = str(line).strip()
        if text.startswith(FINISHED_START_PREFIXES):
            self.finished_lines.append(text)
            self._in_block = True
        elif self._in_block and text.startswith(FINISHED_CONTINUATION_PREFIXES):
            self.finished_lines.append(text)
        if text in COMPLETION_BANNERS:
            self.completed = True
        return text


def read_banner(text, in_block=False):
    """One driver line -> (finished_line or None, in_finished_block, completed).

    The single-line form of BannerCollector.feed, for the TUI's per-line reader.
    """
    text = str(text).strip()
    finished = None
    if text.startswith(FINISHED_START_PREFIXES):
        finished, in_block = text, True
    elif in_block and text.startswith(FINISHED_CONTINUATION_PREFIXES):
        finished = text
    return finished, in_block, text in COMPLETION_BANNERS


def finished_build_lines(collected, path):
    """Lines to print after a finish; a synthetic UNKNOWN line when none seen."""
    lines = list(collected or [])
    return lines or [format_finished_line("UNKNOWN", 0, path)]


def finish_decision(unattended, completed, exit_code):
    """'exit' only for an unattended run that completed with exit 0; else 'dialog'."""
    return 'exit' if unattended and completed and exit_code == 0 else 'dialog'


def classify_exit(driver_returncode, completed, signal_number=None):
    """Launcher exit code. Precedence: signal > nonzero driver exit > no banner > ok.

    driver_returncode follows subprocess semantics (negative = killed by signal).
    signal_number may name a signal explicitly (e.g. a forwarded one).
    """
    if signal_number is None and driver_returncode is not None and driver_returncode < 0:
        signal_number = -driver_returncode
    if signal_number:
        return 128 + int(signal_number)
    if driver_returncode != 0:
        return EXIT_FAILED
    if not completed:
        return EXIT_BLOCKED
    return EXIT_OK


def desktop_decision(desktop_lib, root, environ=None, platform=None, unattended=False,
                     attended_noui=False, config_command=None):
    """Pure desktop decision. Returns dict(status, reason, argv, framework, candidates)
    or None when the desktop flow does not apply. status: skipped|prompt."""
    environ = os.environ if environ is None else environ
    try:
        found = desktop_lib.detect(root)
    except Exception:
        return None
    if not found or not found.get("framework") or found.get("framework") == "none":
        return None
    argv = found.get("command")
    candidates = found.get("candidates") or []
    if config_command is not None:
        try:
            parsed = shlex.split(config_command)
        except ValueError:
            parsed = []
        if parsed:
            argv, candidates = parsed, []
    out = {"framework": found["framework"], "argv": argv, "candidates": candidates}
    if attended_noui:
        return dict(out, status="skipped", reason="noui")
    headless = desktop_lib.headless_reason(environ, platform)
    if unattended:
        return dict(out, status="skipped", reason="unattended")
    if headless:
        return dict(out, status="skipped", reason="headless", detail=headless)
    if not argv:
        return dict(out, status="skipped", reason="ambiguous")
    return dict(out, status="prompt", reason="attended")


STARTUP_ACTIONS = ("create_app", "github_issue", "change_request")

# Fixed driver names per allowlisted action; paths never come from the environment.
_DRIVERS = {
    "create_app": "stagegate.sh",
    "github_issue": "from-issue.sh",
    "change_request": "change-workflow.sh",
}
_ISSUE_MODES = ("", "--change", "--new")


def build_driver_command(action, text, attended, root_dir, issue_mode=""):
    """Driver argv for a startup action (mirrors the TUI's cmd_for).

    Raises ValueError for an action outside the three-action allowlist (unknown,
    empty, path-like, non-string) or for missing text where the driver needs it.
    """
    if not isinstance(action, str) or action not in STARTUP_ACTIONS:
        raise ValueError("Unknown startup action: %r" % (action,))
    issue_mode = issue_mode or ""  # the TUI passes None for non-issue actions
    if issue_mode not in _ISSUE_MODES:
        raise ValueError("Unknown issue mode: %r" % (issue_mode,))
    cmd = [os.path.join(root_dir, "scripts", _DRIVERS[action])]
    if action == "github_issue":
        text = (text or "").strip()
        if not text:
            raise ValueError("Startup text is required for " + action)
        cmd.append(text)
        if action == "github_issue" and issue_mode:
            cmd.append(issue_mode)
    if attended:
        cmd.append("--attended")
    return cmd


def prepare_worktree(root_dir, project_root, environ=None, issue=False, runner=None):
    """Create the run worktree via worktrees.sh worktree_auto (non-issue runs).

    Returns the directory, or None when skipped or on any failure (same
    tolerance as the TUI).
    """
    import subprocess
    environ = os.environ if environ is None else environ
    if environ.get("UNCLE_PROJECT_ROOT_LOCKED") or issue:
        return None
    runner = runner or subprocess.run
    try:
        result = runner(
            ["bash", "-c", '. "$1/scripts/lib/worktrees.sh"; worktree_auto "$2"',
             "_", root_dir, project_root],
            capture_output=True, text=True, timeout=120,
            env=dict(environ, ROOT=root_dir), cwd=project_root)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (result.stdout or "").strip().splitlines()
    directory = lines[-1] if lines else ""
    if result.returncode or not directory or not os.path.isdir(directory):
        return None
    return directory


def resolve_startup_text(text, text_file_reader=None, text_file=None):
    """Startup text: the private file (via reader) wins over the plain text."""
    if text_file:
        if text_file_reader is None:
            raise ValueError("No reader for startup text file")
        return text_file_reader(text_file)
    return text or ""


def change_request_exists(project_root):
    return any(os.path.lexists(os.path.join(project_root, *part, "CHANGE_REQUEST.md"))
               for part in ((), (".uncle", "docs")))


def write_change_request(project_root, text):
    """Write CHANGE_REQUEST.md under .uncle/docs; refuses to overwrite."""
    if change_request_exists(project_root):
        raise FileExistsError("CHANGE_REQUEST.md already exists")
    directory = os.path.join(project_root, ".uncle", "docs")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "CHANGE_REQUEST.md")
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(text)
    return path


def startup_brief_document(text, kind, fields):
    """Brief document for a startup/home create action; plain app text is wrapped."""
    import re
    document = text
    if kind == 'app' and not re.search(r'^## ', document, re.M):
        document = '# Application brief\n\n' + '\n\n'.join(
            '## ' + field + '\n' + (document.strip() if field == 'Summary'
                                    else APP_BRIEF_FIELD_PLACEHOLDER)
            for field in fields)
    return document


def write_startup_brief(root, text, kind, fields, commit):
    """Write the startup brief for --application / create_app.

    `commit(document)` persists it (the TUI passes its Conversation-based writer).
    Returns the document written. No supervisor draft runs here.
    """
    document = startup_brief_document(text, kind, fields)
    commit(document)
    return document
