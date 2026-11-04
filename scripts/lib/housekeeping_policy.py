#!/usr/bin/env python3
"""Housekeeping policy: pure, shell-free checks of a proposed plan.

Public entry point: check_plan(plan, disallow, context=None).  Commands are
argv lists (or strings read by a strict shlex reader); nothing here ever runs
a command.  The operation is derived from argv alone; the model's `op` label
is only cross-checked.  Refusal results name the rule and the command.
"""
import json
import os
import re
import shlex
import sys

UNREADABLE_RE = re.compile(r"[|;&`<>\n\r\x00]|\$\(")
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ISSUE_RE = re.compile(r"^[1-9][0-9]*$")
RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}"}
BASE_PROTECTED = ("main", "master")

# Locked floor (D-1). Hard-coded; never read from or written to config.
FLOOR_PATTERNS = ("gh repo delete", "gh repo archive", "sudo")
FLOOR_DESCRIPTIONS = (
    "gh repo delete / gh repo archive",
    "sudo",
    "rm with recursive/force flags on /, /*, ~, ~/, ~/*, $HOME, ${HOME}",
    "git push with force semantics (--force, -f, --force-with-lease, +refspec) "
    "targeting the default branch (main, master, origin HEAD)",
)

# Default editable list (change request, verbatim where expressible as word
# patterns).  `git push --delete` is intentionally absent: the branch-cleanup
# allowlist shape needs it and D-7 guards it; any other push --delete matches
# no allowlist shape and is refused.  `gh api -X/--method` covers writes.
DEFAULT_DISALLOW = (
    "rm -r", "rm -R", "rm -f", "rm --recursive", "rm --force",
    "sudo", "dd", "mkfs", "chmod -R", "chown -R",
    "git push --force", "git push -f", "git push --force-with-lease",
    "git reset --hard", "git clean -f", "git filter-branch", "git branch -D",
    "gh repo delete", "gh repo archive", "gh repo edit --visibility",
    "gh release delete", "gh secret", "gh variable", "gh ssh-key", "gh auth",
    "gh api -X", "gh api --method",
)


class Unreadable(Exception):
    pass


def display_argv(argv):
    """Render argv with control/non-printable characters escaped."""
    out = []
    for t in argv:
        s = []
        for ch in str(t):
            o = ord(ch)
            if ch == "\n":
                s.append("\\n")
            elif ch == "\r":
                s.append("\\r")
            elif ch == "\t":
                s.append("\\t")
            elif o < 32 or o == 127 or not ch.isprintable():
                s.append("\\x%02x" % o if o < 256 else "\\u%04x" % o)
            else:
                s.append(ch)
        out.append("".join(s))
    return " ".join(out)


def tokenize(cmd):
    """Strict reader: argv list or string -> list of tokens, else Unreadable."""
    if isinstance(cmd, (list, tuple)):
        toks = list(cmd)
        if not toks or not all(isinstance(t, str) and t != "" and "\x00" not in t for t in toks):
            raise Unreadable("argv must be a non-empty list of non-empty strings")
    elif isinstance(cmd, str):
        if UNREADABLE_RE.search(cmd):
            raise Unreadable("pipe, redirect, substitution, chaining or control character")
        try:
            toks = shlex.split(cmd, posix=True)
        except ValueError as e:
            raise Unreadable(str(e))
        if not toks:
            raise Unreadable("empty command")
    else:
        raise Unreadable("command is neither list nor string")
    if ENV_ASSIGN_RE.match(toks[0]):
        raise Unreadable("environment assignment token")
    if "--" in toks:
        raise Unreadable("`--` separator")
    return toks


def _prog(tok):
    return os.path.basename(tok)


def split_tokens(rest):
    """Return (words, flags): clusters expanded, --flag=value by name."""
    words, flags = [], set()
    for t in rest:
        if t.startswith("--") and len(t) > 2:
            flags.add(t.split("=", 1)[0])
        elif t.startswith("-") and len(t) > 1:
            if len(t) > 2:
                flags.update("-" + c for c in t[1:])
            else:
                flags.add(t)
        else:
            words.append(t)
    return words, flags


FLAG_ALIASES = {
    "-r": {"-R", "--recursive"}, "-R": {"-r", "--recursive"},
    "--recursive": {"-r", "-R"},
    "-f": {"--force"}, "--force": {"-f"},
}


def match_pattern(pattern, tokens):
    """D-5 semantics: program+subcommands are a prefix; all pattern flags
    appear among the command's flags in any order/position."""
    ptoks = shlex.split(pattern)
    if not ptoks:
        return False
    prog = _prog(tokens[0])
    pp = _prog(ptoks[0])
    if not (prog == pp or prog.startswith(pp + ".")):
        return False
    psubs, pflags = split_tokens(ptoks[1:])
    cwords, cflags = split_tokens(tokens[1:])
    if cwords[:len(psubs)] != psubs:
        return False
    # Long/short spellings of the same flag are interchangeable (rm -r ==
    # rm --recursive) so a spelling change cannot evade a pattern.
    expanded = set(cflags)
    for f in cflags:
        expanded |= FLAG_ALIASES.get(f, set())
    return pflags <= expanded


def protected_branches(context):
    s = set(BASE_PROTECTED)
    if context and context.get("default_branch"):
        s.add(context["default_branch"])
    return s


def _ref_dest(ref):
    ref = ref.lstrip("+")
    if ":" in ref:
        ref = ref.split(":", 1)[1]
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    return ref


def floor_violation(tokens, context=None):
    """Return the floor rule name violated by tokens, or None (D-1)."""
    prog = _prog(tokens[0])
    words, flags = split_tokens(tokens[1:])
    if prog == "sudo":
        return "floor: sudo"
    if prog == "gh" and words[:2] in (["repo", "delete"], ["repo", "archive"]):
        return "floor: gh repo %s" % words[1]
    if prog == "rm" and (flags & {"-r", "-R", "-f", "--recursive", "--force"}) \
            and any(t in RM_TARGETS for t in tokens[1:]):
        return "floor: rm recursive/force on protected target"
    if prog == "git" and words[:1] == ["push"]:
        force = bool(flags & {"-f", "--force", "--force-with-lease"}) or \
            any(t.startswith("+") for t in tokens[1:])
        if force:
            prot = protected_branches(context)
            refs = words[2:]
            if not refs or any(_ref_dest(r) in prot for r in refs):
                return "floor: forced push to default branch"
    return None


def disallow_violation(tokens, disallow):
    for p in disallow or ():
        if not isinstance(p, str):
            continue
        try:
            if match_pattern(p, tokens):
                return "disallow: " + p
        except ValueError:
            continue
    return None


# ---- allowlist shapes -------------------------------------------------------
# flags: name -> takes_value
def _shape(op, prog, subs, flags, lo, hi, required=(), first=None):
    return dict(op=op, prog=prog, subs=subs, flags=flags, lo=lo, hi=hi,
                required=tuple(required), first=first)


SHAPES = [
    _shape("repo-rename", "gh", ["repo", "rename"], {"--yes": 0, "-y": 0}, 1, 1),
    _shape("worktree-prune", "git", ["worktree", "prune"], {"-v": 0, "--verbose": 0}, 0, 0),
    _shape("worktree-remove", "git", ["worktree", "remove"], {}, 1, 1),
    _shape("branch-delete-merged", "git", ["branch"], {"-d": 0}, 1, 1, required=["-d"]),
    _shape("branch-delete-merged", "git", ["push"], {"--delete": 0}, 2, 2,
           required=["--delete"], first="origin"),
    _shape("label-cleanup", "gh", ["label", "delete"], {"--yes": 0, "-y": 0}, 1, 1),
    _shape("issue-triage", "gh", ["issue", "edit"], {"--add-label": 1, "--remove-label": 1}, 1, 1),
    _shape("issue-triage", "gh", ["issue", "close"], {"--reason": 1}, 1, 1),
    _shape("issue-triage", "gh", ["issue", "comment"], {"--body": 1}, 1, 1, required=["--body"]),
]

_JQ = {"--json": 1, "--jq": 1, "-q": 1}
VERIFY_SHAPES = [
    ("repo-rename", _shape("v-repo-view", "gh", ["repo", "view"], _JQ, 0, 1)),
    ("worktree-prune", _shape("v-worktree-list", "git", ["worktree", "list"], {"--porcelain": 0}, 0, 0)),
    ("worktree-remove", _shape("v-worktree-list", "git", ["worktree", "list"], {"--porcelain": 0}, 0, 0)),
    ("branch-delete-local", _shape("v-branch-list", "git", ["branch"],
                                   {"--list": 0, "-l": 0}, 0, 1, required=[])),
    ("branch-delete-remote", _shape("v-ls-remote", "git", ["ls-remote"],
                                    {"--heads": 0, "--exit-code": 0}, 1, 2, first="origin")),
    ("label-cleanup", _shape("v-label-list", "gh", ["label", "list"],
                             {"--json": 1, "--jq": 1, "-q": 1, "--limit": 1, "-L": 1}, 0, 0)),
    ("issue-triage", _shape("v-issue-view", "gh", ["issue", "view"],
                            dict(_JQ, **{"--comments": 0}), 1, 1)),
]


def match_shape(shape, tokens):
    """Exact full-argv match. Returns {'pos': [...], 'flags': {...}} or None."""
    if _prog(tokens[0]) != shape["prog"] or tokens[0] != shape["prog"]:
        return None
    n = len(shape["subs"])
    if tokens[1:1 + n] != shape["subs"]:
        return None
    pos, flags = [], {}
    rest = tokens[1 + n:]
    i = 0
    while i < len(rest):
        t = rest[i]
        if t.startswith("-") and len(t) > 1:
            name, eq, val = t.partition("=")
            if name not in shape["flags"] or name in flags:
                return None
            if shape["flags"][name]:
                if not eq:
                    i += 1
                    if i >= len(rest):
                        return None
                    val = rest[i]
                flags[name] = val
            else:
                if eq:
                    return None
                flags[name] = True
        else:
            if "://" in t:
                return None
            pos.append(t)
        i += 1
    if not (shape["lo"] <= len(pos) <= shape["hi"]):
        return None
    if any(r not in flags for r in shape["required"]):
        return None
    if shape["first"] is not None and (not pos or pos[0] != shape["first"]):
        return None
    return {"pos": pos, "flags": flags}


def _classify_op(tokens):
    """Derive (op, shape, parsed, kind) from argv alone, or None."""
    for sh in SHAPES:
        m = match_shape(sh, tokens)
        if not m:
            continue
        if sh["op"] == "issue-triage":
            if not ISSUE_RE.match(m["pos"][0]):
                continue
            if sh["subs"][1] == "edit" and not (set(m["flags"]) & {"--add-label", "--remove-label"}):
                continue
        kind = sh["op"]
        if kind == "branch-delete-merged":
            kind = "branch-delete-remote" if sh["subs"] == ["push"] else "branch-delete-local"
        return sh["op"], m, kind
    return None


def remote_delete_violation(branch, context=None):
    """D-7: refuse protected / refspec remote deletes."""
    if ":" in branch or branch.startswith("+"):
        return "remote-delete: colon/refspec form refused"
    b = branch[len("refs/heads/"):] if branch.startswith("refs/heads/") else branch
    prot = protected_branches(context) | {"HEAD"}
    if context and context.get("current_branch"):
        prot.add(context["current_branch"])
    if b in prot:
        return "remote-delete: protected branch %s" % b
    return None


def merged_check_argv(branch, default_branch="main"):
    """Read-only execute-time merged check for a remote delete (D-7)."""
    return ["git", "merge-base", "--is-ancestor", "origin/" + branch, "origin/" + default_branch]


def _refuse(rule, argv, op_id=None, message=""):
    return {"allow": False, "rule": rule, "command": display_argv(argv) if isinstance(argv, (list, tuple)) else str(argv),
            "op_id": op_id, "message": message or rule}


def _check_verify(op_kind, parsed, vtokens):
    """Verify argv must be on the read-only list and scoped to the op."""
    targets = set(parsed["pos"])
    targets |= {"refs/heads/" + t for t in parsed["pos"][-1:]}
    for k, sh in VERIFY_SHAPES:
        if k != op_kind:
            continue
        m = match_shape(sh, vtokens)
        if not m:
            continue
        if sh["op"] == "v-branch-list" and not ({"--list", "-l"} & set(m["flags"])):
            continue
        pos = m["pos"][1:] if sh["first"] else m["pos"]
        if sh["op"] == "v-issue-view":
            if pos != [parsed["pos"][0]]:
                return "verify-scope: issue number differs from operation"
        elif any(p not in targets for p in pos):
            return "verify-scope: target differs from operation"
        return None
    return "verify-allowlist: not a read-only verify for this operation"


def check_plan(plan, disallow, context=None):
    """Return {'allow': True, 'ops': [...]} or a refusal dict naming rule+command."""
    ops = plan.get("ops") if isinstance(plan, dict) else plan
    if not isinstance(ops, list) or not ops:
        return _refuse("plan-schema: zero operations", [], message="plan has no operations")
    seen = set()
    out = []
    for op in ops:
        if not isinstance(op, dict) or any(k not in op for k in ("id", "op", "argv", "expected", "verify")):
            return _refuse("plan-schema: missing field", [], message="op missing id/op/argv/expected/verify")
        oid = op["id"]
        if oid in seen:
            return _refuse("plan-schema: duplicate id", [], oid)
        seen.add(oid)
        v = op["verify"]
        vargv = v.get("argv") if isinstance(v, dict) else v
        for label, argv in (("operation", op["argv"]), ("verify", vargv)):
            try:
                tokens = tokenize(argv)
            except Unreadable as e:
                return _refuse("unreadable: %s (%s)" % (label, e), argv if isinstance(argv, list) else [str(argv)], oid)
            rule = floor_violation(tokens, context) or disallow_violation(tokens, disallow)
            if rule:
                return _refuse(rule, tokens, oid)
        tokens = tokenize(op["argv"])
        hit = _classify_op(tokens)
        if not hit:
            return _refuse("not-allowlisted: argv matches no allowlist operation", tokens, oid)
        derived, parsed, kind = hit
        if op["op"] != derived:
            return _refuse("op-label-mismatch: label %r but argv is %s" % (op["op"], derived), tokens, oid)
        if kind == "branch-delete-remote":
            rule = remote_delete_violation(parsed["pos"][1], context)
            if rule:
                return _refuse(rule, tokens, oid)
        vtokens = tokenize(vargv)
        rule = _check_verify(kind, parsed, vtokens)
        if rule:
            return _refuse(rule, vtokens, oid)
        out.append({"id": oid, "op": derived, "kind": kind, "argv": tokens, "verify_argv": vtokens})
    return {"allow": True, "ops": out}


def main(argv):
    if len(argv) >= 3 and argv[0] == "check":
        with open(argv[1]) as f:
            try:
                plan = json.load(f)
            except ValueError:
                print(json.dumps(_refuse("plan-schema: invalid JSON", [])))
                return 1
        with open(argv[2]) as f:
            disallow = json.load(f)
        ctx = {}
        rest = argv[3:]
        while len(rest) >= 2:
            ctx[rest[0].lstrip("-").replace("-", "_")] = rest[1]
            rest = rest[2:]
        res = check_plan(plan, disallow, ctx)
        print(json.dumps(res, sort_keys=True))
        return 0 if res["allow"] else 1
    if argv[:1] == ["floor"]:
        print("\n".join(FLOOR_DESCRIPTIONS))
        return 0
    if argv[:1] == ["merged-check"] and len(argv) >= 2:
        print(json.dumps(merged_check_argv(argv[1], argv[2] if len(argv) > 2 else "main")))
        return 0
    sys.stderr.write("usage: housekeeping_policy.py check PLAN.json DISALLOW.json "
                     "[--default-branch B --current-branch C] | floor | merged-check BRANCH [DEFAULT]\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
