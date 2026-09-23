#!/usr/bin/env python3
"""Validate and collate updated-plan specialist packets.

The collated file is the only worker input a parent plan stage may read.
Missing or malformed specialist output is a clear workflow failure, never a
silent invitation for the synthesis model to invent coverage.
"""
import argparse
import json
import sys
from pathlib import Path

SCHEMA = 'uncle.artifact/v1'
KIND = 'updated-plan-worker-packet'
REQUIRED = ('id', 'gap', 'evidence', 'risk', 'required_correction')


class PacketError(ValueError):
    pass


def _text(value, field, source, index):
    if not isinstance(value, str) or not value.strip():
        raise PacketError('%s: finding %d has empty or non-string %s' % (source, index, field))
    return value.strip()


def load_packet(path):
    source = Path(path).name
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise PacketError('%s: worker packet is missing' % source)
    except (OSError, json.JSONDecodeError) as error:
        raise PacketError('%s: invalid JSON worker packet: %s' % (source, error))
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('kind') != KIND:
        raise PacketError('%s: expected schema %s and kind %s' % (source, SCHEMA, KIND))
    findings = value.get('findings')
    if not isinstance(findings, list):
        raise PacketError('%s: findings must be an array' % source)
    normalized, ids = [], set()
    for index, finding in enumerate(findings, 1):
        if not isinstance(finding, dict):
            raise PacketError('%s: finding %d is not an object' % (source, index))
        item = {field: _text(finding.get(field), field, source, index) for field in REQUIRED}
        if item['id'] in ids:
            raise PacketError('%s: duplicate stable finding ID %s' % (source, item['id']))
        ids.add(item['id'])
        normalized.append(item)
    return normalized


def collate(directory, output, expected=()):
    directory = Path(directory)
    names = list(expected) or [path.stem for path in sorted(directory.glob('*.json'))]
    if not names:
        raise PacketError('no worker packets were supplied')
    merged, workers = {}, []
    for name in names:
        path = directory / (name if name.endswith('.json') else name + '.json')
        findings = load_packet(path)
        source = path.stem
        workers.append({'source': source, 'status': 'ok', 'finding_count': len(findings)})
        for item in findings:
            current = merged.setdefault(item['id'], {
                'id': item['id'], 'gaps': [], 'evidence': [], 'risks': [],
                'required_corrections': [], 'sources': []})
            for key, value in (('gaps', item['gap']), ('evidence', item['evidence']),
                               ('risks', item['risk']), ('required_corrections', item['required_correction'])):
                if value not in current[key]:
                    current[key].append(value)
            if source not in current['sources']:
                current['sources'].append(source)
    for item in merged.values():
        item['conflicting_corrections'] = len(item['required_corrections']) > 1
    payload = {'schema': SCHEMA, 'kind': 'updated-plan-worker-packets',
               'workers': workers, 'findings': [merged[key] for key in sorted(merged)]}
    target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?'); parser.add_argument('output', nargs='?')
    parser.add_argument('--expected', nargs='*', default=[])
    parser.add_argument('--validate', metavar='PACKET')
    args = parser.parse_args(argv)
    try:
        if args.validate:
            load_packet(args.validate)
        elif args.directory and args.output:
            collate(args.directory, args.output, args.expected)
        else:
            raise PacketError('directory and output are required unless --validate is used')
    except PacketError as error:
        print('updated-plan worker packets: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
