#!/usr/bin/env python3
"""Keep driver-owned checks out of the manual/browser worker queue.

The manual-checklist panel is allowed to propose broad evidence rows, but a
worker is expensive and should not rediscover facts that the driver has
already established through its green check or can inspect deterministically.
This reducer deliberately keeps any row that requires a live interaction,
service/CLI behavior, or a human judgement.  It removes only the clearly
static/automated rows and records them in a provenance packet for final audit.
"""
import argparse
import json
import re
from pathlib import Path


INTERACTIVE = re.compile(
    r"\b(browser|visual|screenshot|viewport|click|tap|mouse|keyboard|keypress|"
    r"key(?:down|up)?|focused|render(?:ed|ing)?|look(?:\s+and\s+feel)?|"
    r"human|user(?:\s+interface)?|accessible|a11y)\b", re.I)
LIVE_ACTION = re.compile(r"\b(open\s+(?:the\s+)?(?:page|app|browser)|click|tap|press|reload|"
                         r"take\s+(?:a\s+)?screenshot|visible\s+browser)\b", re.I)
STATIC_INSPECTION = re.compile(r"\b(read|inspect|search|grep|compare)\b", re.I)
MANUAL_JUDGMENT = re.compile(r"\b(judge|subjective|look(?:\s+and\s+feel)?|aesthetic|"
                             r"human\s+(?:review|sign[- ]?off)|by\s+eye)\b", re.I)
DRIVER_OWNED = re.compile(
    r"\b(green[ -]?check|verification command|npm\b|npx\b|vitest|playwright|"
    r"typecheck|build\b|dependency|lockfile|package\.json|launch\.json|"
    r"vite\.config|content-security-policy|\bcsp\b|mutation|scratch (?:copy|dir)|"
    r"port(?:\s*[:=]|\s+\d)|listener|lsof|curl|grep|\bsearch\b|\binspect\b|"
    r"\bread\s+(?:src|the |a )|source (?:file|code)|file (?:exists|contents)|"
    r"storage api|network api|localstorage|sessionstorage|indexeddb)\b", re.I)
AUTOMATED = re.compile(r"\b(playwright|vitest|pytest|jest|selenium|webdriver|automated browser)\b", re.I)


def driver_owned(check):
    text = ' '.join(str(check.get(key, '')) for key in
                    ('section', 'exact_action', 'expected_result', 'evidence_to_capture'))
    # An automated browser suite belongs to green-check even though it has the
    # word "browser" in it. A live browser observation stays manual when it
    # merely cites a configuration
    # file; only an automated browser command belongs to green-check.
    if AUTOMATED.search(text):
        return True
    if MANUAL_JUDGMENT.search(text):
        return False
    # A source/configuration inspection often mentions a keyboard listener or
    # UI component. It remains driver-owned unless the action actually asks a
    # live page to be exercised.
    if STATIC_INSPECTION.search(text) and not LIVE_ACTION.search(text):
        return True
    if INTERACTIVE.search(text):
        return False
    return bool(DRIVER_OWNED.search(text))


def prune(payload):
    kept, excluded = [], []
    for check in payload.get('checks', []):
        if driver_owned(check):
            excluded.append({
                'id': check.get('id', ''),
                'reason': 'driver-owned static or automated evidence',
                'section': check.get('section', ''),
            })
        else:
            kept.append(check)
    result = dict(payload)
    result['checks'] = kept
    scope = {
        'schema': 'uncle.artifact/v1',
        'kind': 'manual-checklist-driver-scope',
        'included_check_ids': [check.get('id', '') for check in kept],
        'excluded': excluded,
        'evidence_source': '.uncle/workflow/green-check.tsv',
    }
    return result, scope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checklist')
    parser.add_argument('--scope', required=True)
    parser.add_argument('--proposed', help='optional immutable copy before pruning')
    args = parser.parse_args()
    path = Path(args.checklist)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'manual-checklist':
        raise SystemExit('manual checklist driver scope: wrong canonical schema')
    if not isinstance(payload.get('checks'), list):
        raise SystemExit('manual checklist driver scope: checks must be an array')
    if args.proposed:
        proposed = Path(args.proposed)
        proposed.parent.mkdir(parents=True, exist_ok=True)
        proposed.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    result, scope = prune(payload)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    scope_path = Path(args.scope)
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    scope_path.write_text(json.dumps(scope, indent=2) + '\n', encoding='utf-8')
    print('manual checklist scope: %d worker row(s), %d driver-owned row(s)' %
          (len(result['checks']), len(scope['excluded'])))


if __name__ == '__main__':
    main()
