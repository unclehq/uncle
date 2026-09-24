#!/usr/bin/env python3
"""Produce an updated plan locally only when there is nothing to resolve."""
import argparse
import json
from pathlib import Path


def read(path, kind):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != kind:
        raise ValueError('%s is not %s JSON' % (path, kind))
    return data


def build(project_plan, review, output):
    plan = read(project_plan, 'plan')
    assessment = read(review, 'adversarial-review')
    if assessment.get('findings'):
        return False
    result = dict(plan, dispositions=[])
    narrative = result.get('narrative', '')
    if narrative.startswith('# Project plan'):
        result['narrative'] = '# Updated project plan' + narrative[len('# Project plan'):]
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project_plan'); parser.add_argument('review'); parser.add_argument('output')
    args = parser.parse_args()
    try:
        raise SystemExit(0 if build(args.project_plan, args.review, args.output) else 1)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print('updated-plan fast path: ' + str(error))
        raise SystemExit(1)
