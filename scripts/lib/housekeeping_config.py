#!/usr/bin/env python3
"""Housekeeping disallow-list config: stored in `.uncle/config` under the key
`housekeeping.disallow` as a JSON array.  The locked floor lives in
housekeeping_policy.py and is never stored here.  Every write changes only
that one line; all other lines are preserved byte for byte.
"""
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import housekeeping_policy as policy  # noqa: E402

KEY = "housekeeping.disallow"


class ConfigError(Exception):
    pass


def normalize(pattern):
    return " ".join(pattern.split())


def validate_pattern(pattern):
    """Return normalized pattern or raise ConfigError."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ConfigError("pattern is empty")
    if policy.UNREADABLE_RE.search(pattern):
        raise ConfigError("pattern contains shell metacharacters or control characters")
    try:
        toks = shlex.split(pattern)
    except ValueError as e:
        raise ConfigError("pattern does not parse: %s" % e)
    if not toks or any("*" in t for t in toks):
        raise ConfigError("empty or wildcard pattern is not allowed")
    if toks[0].startswith("-") or policy.ENV_ASSIGN_RE.match(toks[0]) or "--" in toks:
        raise ConfigError("pattern must start with a program name")
    return normalize(pattern)


def config_path(root=None):
    return os.environ.get("UNCLE_CONFIG") or os.path.join(root or os.getcwd(), ".uncle", "config")


def _read_lines(path):
    try:
        with open(path) as f:
            return f.read().splitlines(keepends=True)
    except OSError:
        return []


def _is_key_line(line):
    s = line.strip()
    return bool(s) and not s.startswith("#") and s.split(None, 1)[0] == KEY


def defaults():
    return list(policy.DEFAULT_DISALLOW)


def load(path):
    """Stored list; missing or corrupt falls back to defaults, never empty-by-accident."""
    for line in _read_lines(path):
        if _is_key_line(line):
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                return defaults()
            try:
                val = json.loads(parts[1])
                if not isinstance(val, list):
                    return defaults()
                return [validate_pattern(p) for p in val]
            except (ValueError, ConfigError):
                return defaults()
    return defaults()


def save(path, patterns):
    new = "%s %s\n" % (KEY, json.dumps(list(patterns)))
    lines = _read_lines(path)
    out, done = [], False
    for line in lines:
        if _is_key_line(line):
            if not done:
                out.append(new)
                done = True
            continue
        out.append(line)
    if not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(new)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".hk-tmp"
    with open(tmp, "w") as f:
        f.write("".join(out))
    os.replace(tmp, path)


def floor_patterns():
    return [normalize(p) for p in policy.FLOOR_PATTERNS]


def _check_new(current, pattern, skip=None):
    p = validate_pattern(pattern)
    if p in floor_patterns():
        raise ConfigError("pattern equals a locked built-in rule")
    for i, c in enumerate(current):
        if i != skip and c == p:
            raise ConfigError("duplicate pattern")
    return p


def add(path, pattern):
    cur = load(path)
    p = _check_new(cur, pattern)
    save(path, cur + [p])
    return cur + [p]


def edit(path, index, pattern):
    cur = load(path)
    if not 1 <= index <= len(cur):
        raise ConfigError("no such entry")
    p = _check_new(cur, pattern, skip=index - 1)
    cur[index - 1] = p
    save(path, cur)
    return cur


def remove(path, index):
    cur = load(path)
    if not 1 <= index <= len(cur):
        raise ConfigError("no such entry")
    del cur[index - 1]
    save(path, cur)
    return cur


def reset(path):
    save(path, defaults())
    return defaults()


def effective(path):
    """Floor patterns + editable list (the list can only add refusals)."""
    return floor_patterns() + load(path)


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: housekeeping_config.py CONFIG list|floor|add P|edit N P|remove N|reset|effective\n")
        return 2
    path, cmd, args = argv[0], argv[1], argv[2:]
    try:
        if cmd == "list":
            for i, p in enumerate(load(path), 1):
                print("%d. %s" % (i, p))
        elif cmd == "floor":
            print("\n".join(policy.FLOOR_DESCRIPTIONS))
        elif cmd == "add" and len(args) == 1:
            add(path, args[0])
        elif cmd == "edit" and len(args) == 2:
            edit(path, int(args[0]), args[1])
        elif cmd == "remove" and len(args) == 1:
            remove(path, int(args[0]))
        elif cmd == "reset":
            reset(path)
        elif cmd == "effective":
            print(json.dumps(effective(path)))
        else:
            sys.stderr.write("bad arguments\n")
            return 2
    except (ConfigError, ValueError) as e:
        sys.stderr.write("rejected: %s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
