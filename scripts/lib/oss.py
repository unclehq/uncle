#!/usr/bin/env python3
"""Pure helpers for --oss mode: guideline discovery, AI policy, DCO, claimability,
PR body rendering, sign-off, commit/PR-title format discovery.

CLI: python3 -I oss.py check-publish --root DIR   (exit 3 on AI prohibition)
     python3 -I oss.py discover --root DIR        (JSON)
     python3 -I oss.py claimable --issue FILE     (exit 4 when not claimable)
"""
import argparse
import json
import os
import re
import sys

GUIDANCE_FILES = (
    "CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING", ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md", "AI_POLICY.md", "AI-POLICY.md", "POLICY.md",
    ".github/AI_POLICY.md", "DCO", "DCO.md", "CODE_OF_CONDUCT.md", "AGENTS.md",
    ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
)
PR_TEMPLATES = (
    ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
)
MAX_BYTES = 200_000

# Revisable pattern lists (deterministic heuristic, not a legal reading).
AI_PROHIBIT_RE = re.compile(
    r"(?i)\b(?:no|not|never|do not|don't|prohibit\w*|ban\w*|forbid\w*|reject\w*|will not accept"
    r"|not accept\w*|not allowed|disallow\w*)\b[^.\n]{0,80}\b(?:ai|llm|chatgpt|copilot|"
    r"generative|machine[- ]generated|ai[- ]generated|ai[- ]assisted)\b"
    r"|\b(?:ai|llm|chatgpt|copilot|generative|ai[- ]generated|machine[- ]generated)\b"
    r"[^.\n]{0,80}\b(?:prohibited|banned|forbidden|not allowed|not accepted|not permitted"
    r"|will be rejected|are rejected|is rejected)\b")
AI_DISCLOSE_RE = re.compile(
    r"(?i)\b(?:disclos\w*|declare|indicate|mention|state|label)\b[^.\n]{0,80}\b(?:ai|llm|"
    r"ai[- ]assisted|ai[- ]generated|generative|copilot)\b|\b(?:ai|llm|ai[- ]assisted|"
    r"ai[- ]generated)\b[^.\n]{0,80}\b(?:disclos\w*|must be (?:declared|labell?ed))")
AI_ALLOW_RE = re.compile(
    r"(?i)\b(?:ai|llm|ai[- ]assisted|ai[- ]generated|copilot)\b[^.\n]{0,80}\b(?:welcome|"
    r"allowed|permitted|accepted|ok)\b")
DCO_RE = re.compile(r"(?i)\bsigned-off-by\b|\bdeveloper certificate of origin\b|\bDCO\b|git commit -s")
COMMIT_FMT_RE = re.compile(
    r"(?i)(?:commit (?:message|title|subject)s?|conventional commits?)[^\n]{0,160}")
TITLE_FMT_RE = re.compile(r"(?i)(?:\bPR|pull request) (?:title|name)s?[^\n]{0,160}")
CLAIM_LABELS = ("needs discussion", "needs-discussion", "wontfix", "won't fix", "duplicate",
                "invalid", "blocked", "on hold", "stale", "question")
DISCLOSURE = ("AI disclosure: this change was prepared with AI assistance and reviewed "
              "by the submitter.")


def _read(path):
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    return data[:MAX_BYTES].decode("utf-8", "replace")


def discover(root):
    """Return {"guidelines": [{kind,text,source}], "unknown": [{path,reason}]}.

    Only files whose fully resolved path lies inside the resolved root are read.
    """
    real_root = os.path.realpath(root)
    guidelines, unknown = [], []
    for rel in GUIDANCE_FILES:
        p = os.path.join(root, rel)
        if not os.path.lexists(p):
            continue
        real = os.path.realpath(p)
        if real != real_root and not real.startswith(real_root + os.sep):
            unknown.append({"path": rel, "reason": "resolves outside repository; not read"})
            continue
        if not os.path.isfile(real):
            continue
        try:
            text = _read(real)
        except OSError as e:
            unknown.append({"path": rel, "reason": "unreadable: %s" % e.__class__.__name__})
            continue
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s:
                continue
            kind = classify(s)
            if kind:
                guidelines.append({"kind": kind, "text": s[:300], "source": "%s:%d" % (rel, n)})
    if not guidelines and not unknown:
        unknown.append({"path": "(repository)", "reason": "no contributing guidance found"})
    return {"guidelines": guidelines, "unknown": unknown}


def classify(line):
    if AI_PROHIBIT_RE.search(line):
        return "ai-prohibit"
    if AI_DISCLOSE_RE.search(line):
        return "ai-disclose"
    if AI_ALLOW_RE.search(line):
        return "ai-allow"
    if DCO_RE.search(line):
        return "dco"
    if TITLE_FMT_RE.search(line):
        return "pr-title-format"
    if COMMIT_FMT_RE.search(line):
        return "commit-format"
    return None


def ai_policy(entries):
    """prohibited > disclose > allowed > unknown. A prohibition always wins."""
    kinds = {e["kind"] for e in entries}
    if "ai-prohibit" in kinds:
        return "prohibited"
    if "ai-disclose" in kinds:
        return "disclose"
    if "ai-allow" in kinds:
        return "allowed"
    return "unknown"


def policy_sources(entries, kind="ai-prohibit"):
    return [e["source"] for e in entries if e["kind"] == kind]


def dco_required(entries):
    return any(e["kind"] == "dco" for e in entries)


def commit_format(entries):
    """Explicit commit-message format lines with sources (empty when none)."""
    return [e for e in entries if e["kind"] == "commit-format"]


def pr_title_format(entries):
    return [e for e in entries if e["kind"] == "pr-title-format"]


def claimable(issue):
    """Return (ok, reasons). Warn when closed, assigned, or labeled as not ready."""
    reasons = []
    if (issue.get("state") or "open").lower() != "open":
        reasons.append("issue is not open (state=%s)" % issue.get("state"))
    assignees = issue.get("assignees") or ([issue["assignee"]] if issue.get("assignee") else [])
    if assignees:
        names = ", ".join(str(a.get("login", a)) if isinstance(a, dict) else str(a)
                          for a in assignees)
        reasons.append("issue is assigned to %s" % names)
    for lab in issue.get("labels") or []:
        name = (lab.get("name") if isinstance(lab, dict) else str(lab)) or ""
        if name.strip().lower() in CLAIM_LABELS:
            reasons.append("issue has label '%s'" % name)
    return (not reasons, reasons)


def render_pr_body(template, summary, testing):
    """Fill the project's PR template; always retain an AI disclosure."""
    body = template or ""
    if not body.strip():
        body = "## Summary\n\n{summary}\n\n## Testing\n\n{testing}\n"
        body = body.replace("{summary}", summary).replace("{testing}", testing)
    else:
        body = re.sub(r"(?im)^(#+\s*(?:summary|description|what|changes?)[^\n]*\n)(?:\s*<!--.*?-->\s*)?",
                      lambda m: m.group(1) + "\n" + summary + "\n\n", body, count=1, flags=re.S) \
            if re.search(r"(?im)^#+\s*(?:summary|description|what|changes?)", body) \
            else body.rstrip() + "\n\n" + summary + "\n"
        if re.search(r"(?im)^#+\s*(?:testing|tests?|how (?:has )?this been tested)", body):
            body = re.sub(r"(?im)^(#+\s*(?:testing|tests?|how (?:has )?this been tested)[^\n]*\n)",
                          lambda m: m.group(1) + "\n" + testing + "\n\n", body, count=1)
        else:
            body = body.rstrip() + "\n\n## Testing\n\n" + testing + "\n"
    if not re.search(r"(?i)\bAI\b[^\n]{0,40}\bdisclos|\bdisclos\w*[^\n]{0,40}\bAI\b", body):
        body = body.rstrip() + "\n\n" + DISCLOSURE + "\n"
    return body


def signoff(message, name, email):
    """Append Signed-off-by trailer once; idempotent."""
    trailer = "Signed-off-by: %s <%s>" % (name, email)
    if trailer in message.splitlines():
        return message
    msg = message.rstrip("\n")
    lines = msg.splitlines()
    if lines and re.match(r"^[A-Za-z-]+: ", lines[-1]) and len(lines) > 1 and lines[-2] == "":
        return msg + "\n" + trailer + "\n"
    return msg + "\n\n" + trailer + "\n"


CONVENTIONAL_RE = re.compile(r"^[a-z]+(\([^)]+\))?!?: \S")


def apply_title_format(title, entries):
    """Apply an explicitly stated Conventional Commits format to a title; unchanged otherwise."""
    stated = commit_format(entries) + pr_title_format(entries)
    if not any(re.search(r"(?i)conventional", e["text"]) for e in stated):
        return title
    if CONVENTIONAL_RE.match(title):
        return title
    kind = "fix" if re.search(r"(?i)\b(fix|bug|crash|error|regression)", title) else "feat"
    return "%s: %s" % (kind, title[:1].lower() + title[1:])


def format_conflicts(entries):
    """Reasons when stated commit/title formats cannot both be satisfied (listed for the human gate)."""
    reasons = []
    texts = [e["text"].lower() for e in commit_format(entries) + pr_title_format(entries)]
    if any("conventional" in t for t in texts) and any(re.search(r"\[#?\w+-?\d*\]|ticket|issue number", t) for t in texts):
        reasons.append("conventional-commit format and a ticket-prefix format are both required")
    return reasons


def plan_conflicts(plan_text):
    """Items under the plan's Conflicts heading, plus an unresolved marker when the section is missing."""
    m = re.search(r"(?im)^#+\s*(?:\d+\.\s*)?\**conflicts\**[^\n]*\n(.*?)(?=^#+\s|\Z)", plan_text, re.S)
    if not m:
        return ["plan has no Conflicts section"]
    items = [re.sub(r"^[-*\d.\s]+", "", l).strip() for l in m.group(1).splitlines()]
    return [i for i in items if i and not re.match(r"(?i)^(none|n/a|no conflicts?)\b", i)]


def gate_reasons(plan_text, issue=None, root="."):
    """Everything the human gate must list before an OSS plan can be approved."""
    reasons = list(plan_conflicts(plan_text))
    reasons += format_conflicts(discover(root)["guidelines"])
    if issue is not None:
        reasons += claimable(issue)[1]
    return reasons


def check_publish(root):
    """Return (ok, message). Refuses when any AI prohibition is discovered."""
    entries = discover(root)["guidelines"]
    if ai_policy(entries) == "prohibited":
        src = ", ".join(policy_sources(entries))
        return False, "AI contributions are prohibited by project policy (%s); refusing to publish" % src
    return True, ""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="oss.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check-publish", "discover"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
    g = sub.add_parser("gate-reasons")
    g.add_argument("--plan", required=True)
    g.add_argument("--issue")
    g.add_argument("--root", default=".")
    c = sub.add_parser("claimable")
    c.add_argument("--issue", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "discover":
        print(json.dumps(discover(a.root), indent=2))
        return 0
    if a.cmd == "check-publish":
        ok, msg = check_publish(a.root)
        if not ok:
            print(msg, file=sys.stderr)
            return 3
        return 0
    if a.cmd == "gate-reasons":
        issue = None
        if a.issue and os.path.isfile(a.issue):
            with open(a.issue, encoding="utf-8") as f:
                issue = json.load(f)
        with open(a.plan, encoding="utf-8") as f:
            reasons = gate_reasons(f.read(), issue, a.root)
        for r in reasons:
            print(r)
        return 4 if reasons else 0
    with open(a.issue, encoding="utf-8") as f:
        ok, reasons = claimable(json.load(f))
    for r in reasons:
        print(r)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
