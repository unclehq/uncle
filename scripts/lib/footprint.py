"""Pure helpers for no-footprint publication: disclosure, body/message, scan.

No I/O, no git. Stdlib only.
"""
import re

DEFAULT_DISCLOSURE = "This change was prepared with AI assistance."
DEFAULT_TRAILER = "Assisted-by: AI tooling"

ENV_DISCLOSURE = "UNCLE_FOOTPRINT_DISCLOSURE"
ENV_TRAILER = "UNCLE_FOOTPRINT_TRAILER"
KEY_DISCLOSURE = "footprint.disclosure"
KEY_TRAILER = "footprint.trailer"
KEY_NAME_UNCLE = "footprint.name_uncle"

# Vendor attribution lines agent CLIs append to generated text.
_VENDOR_LINE = re.compile(
    r"^\s*(co-authored-by:.*(claude|anthropic|codex|openai|gemini|copilot|"
    r"noreply@anthropic\.com).*"
    r"|.*generated with \[?(claude|codex|gemini|copilot).*"
    r"|.*🤖.*generated.*"
    r"|assisted-by:.*)\s*$",
    re.IGNORECASE,
)

# Uncle workflow vocabulary that must not appear in publication fields.
_UNCLE_WORDS = re.compile(
    r"(\buncle\b|\.uncle\b|\buncle[-_]|\battestation\b|\badversarial[ _-]review\b|"
    r"\bCHANGE_(PLAN|SPEC|REQUEST)\b|\bPROJECT_PLAN\b|\bBASELINE_REPORT\b|"
    r"\bIMPLEMENTATION_NOTES\b|\bVERIFICATION_REPORT\b|\bFINAL_AUDIT\b|"
    r"\bMANUAL_CHECKLIST\b|\bstagegate\b)",
    re.IGNORECASE,
)

# Agent-vendor attribution ("Reviewed by Codex CLI") is a leak in publication fields.
_VENDOR_ATTRIB = re.compile(
    r"\b(codex|claude|anthropic|openai|gemini|copilot)\b", re.IGNORECASE)


def _lookup(source, key):
    if not source:
        return None
    try:
        return source.get(key)
    except AttributeError:
        return None


def _resolve(config, env, env_key, cfg_key, default, allow_empty):
    for value in (_lookup(env, env_key), _lookup(config, cfg_key)):
        if value is None:
            continue
        value = str(value)
        if not value.strip():
            if allow_empty:
                return ""
            raise ValueError(
                "empty or whitespace-only disclosure override (%s / %s) is invalid"
                % (env_key, cfg_key)
            )
        return value.strip()
    return default


def resolve_disclosure(config, env):
    """env beats config beats default; empty/whitespace override -> ValueError."""
    return _resolve(config, env, ENV_DISCLOSURE, KEY_DISCLOSURE,
                    DEFAULT_DISCLOSURE, allow_empty=False)


def resolve_trailer(config, env):
    """Same precedence; an empty trailer is allowed and means no trailer."""
    return _resolve(config, env, ENV_TRAILER, KEY_TRAILER,
                    DEFAULT_TRAILER, allow_empty=True)


def name_uncle_enabled(config):
    v = _lookup(config, KEY_NAME_UNCLE)
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def strip_vendor_lines(text):
    if not text:
        return ""
    kept = [ln for ln in text.splitlines() if not _VENDOR_LINE.match(ln)]
    return "\n".join(kept).strip("\n")


def render_body(summary, why, testing, followups, closing, disclosure):
    """Maintainer-style PR body; disclosure is always the last line."""
    if not disclosure or not str(disclosure).strip():
        raise ValueError("disclosure is required in the body")
    parts = []
    for heading, text in (("Summary", summary), ("Why", why),
                          ("Testing", testing), ("Follow-ups", followups)):
        text = strip_vendor_lines(text or "").strip()
        if text:
            parts.append("## %s\n\n%s" % (heading, text))
    closing = strip_vendor_lines(closing or "").strip()
    if closing:
        parts.append(closing)
    parts.append(str(disclosure).strip())
    return "\n\n".join(parts) + "\n"


def render_message(title, summary, trailer):
    """Commit message text only; empty trailer omits it."""
    title = strip_vendor_lines(title or "").strip()
    if not title:
        raise ValueError("commit title is empty")
    out = title
    summary = strip_vendor_lines(summary or "").strip()
    if summary:
        out += "\n\n" + summary
    if trailer and str(trailer).strip():
        out += "\n\n" + str(trailer).strip()
    return out + "\n"


def scan(fields, allow_uncle=False, disclosure=None):
    """Reject Uncle vocabulary in publication fields.

    fields: mapping name -> text (or iterable of (name, text)). No tracked
    content is exempt. When allow_uncle is true and a disclosure is given,
    only lines equal to the disclosure (or trailer-free disclosure line) in
    the fields are exempt. Raises ValueError listing leaks; returns [] if clean.
    """
    items = fields.items() if hasattr(fields, "items") else list(fields)
    exempt = str(disclosure).strip() if (allow_uncle and disclosure) else None
    leaks = []
    for name, text in items:
        for lineno, line in enumerate(str(text or "").splitlines(), 1):
            if exempt is not None and line.strip() == exempt:
                continue
            m = _UNCLE_WORDS.search(line) or _VENDOR_ATTRIB.search(line)
            if m:
                leaks.append("%s:%d: %r" % (name, lineno, m.group(0)))
    if leaks:
        raise ValueError("Uncle vocabulary in publication fields: " + "; ".join(leaks))
    return leaks
