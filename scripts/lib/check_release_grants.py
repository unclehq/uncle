#!/usr/bin/env python3
"""Pre-publish check: a release definition must grant the signed-link call.

Usage: python3 -B scripts/lib/check_release_grants.py <release-definition.json>

Exit 0 prints OK; 1 means valid JSON without a qualifying grant; 2 means
malformed JSON, duplicate keys, an unreadable or missing file, or bad usage.
Failures write a one-line value-free reason to stderr and nothing to stdout.
"""
import json
import sys

PUBLISHER = 'daytona'
METHOD = 'GET'
PATH = '/sandbox/{sandboxId}/ports/{port}/signed-preview-url'

DUPLICATE_KEY_MESSAGE = 'duplicate key in JSON object'


class DuplicateKeyError(ValueError):
    pass


def _reject_duplicates(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise DuplicateKeyError(DUPLICATE_KEY_MESSAGE)
        seen.add(key)
    return dict(pairs)


def parse_json(text):
    return json.loads(text, object_pairs_hook=_reject_duplicates)


def _qualifies(obj):
    return (
        obj.get('publisher') == PUBLISHER
        and obj.get('method') == METHOD
        and obj.get('path') == PATH
        and obj.get('require_approval') is False
    )


def find_signed_link_grant(data):
    """True when any object in the JSON tree is a qualifying grant."""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if _qualifies(node):
                return True
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return False


def _fail(code, reason):
    sys.stderr.write(reason + '\n')
    return code


def main(argv):
    if len(argv) != 2:
        return _fail(2, 'usage: check_release_grants.py <release-definition.json>')
    try:
        with open(argv[1], 'r', encoding='utf-8') as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return _fail(2, 'cannot read release definition file')
    try:
        data = parse_json(text)
    except DuplicateKeyError:
        return _fail(2, DUPLICATE_KEY_MESSAGE)
    except (ValueError, RecursionError):
        return _fail(2, 'release definition is not valid JSON')
    if not find_signed_link_grant(data):
        return _fail(1, 'no qualifying signed-preview-url grant '
                        '(publisher, method, path, require_approval false)')
    sys.stdout.write('OK\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
