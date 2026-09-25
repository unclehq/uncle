#!/usr/bin/env python3
"""Validate and collate isolated execute-checklist worker result packets."""
import argparse
import json
from pathlib import Path

SCHEMA = 'uncle.artifact/v1'
KIND = 'checklist-execution-worker-packet'
STATUSES = {'PASS', 'FAIL', 'BLOCKED-SETUP', 'BLOCKED-HUMAN',
            'BLOCKED-IMPOSSIBLE', 'NOT RUN'}


class PacketError(ValueError):
    pass


def load(path):
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise PacketError('%s: worker packet is missing' % path.name)
    except (OSError, json.JSONDecodeError) as error:
        raise PacketError('%s: invalid JSON worker packet: %s' % (path.name, error))
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA or payload.get('kind') != KIND:
        raise PacketError('%s: expected %s %s' % (path.name, SCHEMA, KIND))
    results = payload.get('results')
    if not isinstance(results, list) or not results:
        raise PacketError('%s: results must be a nonempty array' % path.name)
    seen, normalized = set(), []
    for index, result in enumerate(results, 1):
        required = ('id', 'action', 'expected_result', 'actual_result', 'evidence', 'status')
        if not isinstance(result, dict) or any(not isinstance(result.get(key), str) or not result[key].strip()
                                               for key in required):
            raise PacketError('%s: result %d requires %s' % (path.name, index, ', '.join(required)))
        identifier = result['id'].strip()
        if identifier in seen:
            raise PacketError('%s: duplicate check ID %s' % (path.name, identifier))
        if result['status'].strip() not in STATUSES:
            raise PacketError('%s: result %d has invalid status %r' % (path.name, index, result['status']))
        seen.add(identifier)
        normalized.append({key: result.get(key, '').strip() if isinstance(result.get(key, ''), str) else ''
                           for key in (*required, 'defect_reference')})
    return normalized


def collate(directory, output, expected):
    directory = Path(directory)
    workers, by_id = [], {}
    for name in expected:
        results = load(directory / (name + '.json'))
        workers.append({'source': name, 'status': 'ok', 'result_count': len(results)})
        for result in results:
            identifier = result['id']
            if identifier in by_id:
                raise PacketError('%s.json: duplicate check ID %s already supplied by %s' %
                                  (name, identifier, by_id[identifier]['source']))
            by_id[identifier] = dict(result, source=name)
    payload = {'schema': SCHEMA, 'kind': 'checklist-execution-worker-packets',
               'workers': workers, 'results': [by_id[key] for key in sorted(by_id)]}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?')
    parser.add_argument('output', nargs='?')
    parser.add_argument('--expected', nargs='+', required=True)
    parser.add_argument('--validate', metavar='PACKET',
                        help='validate one worker packet without collating it')
    args = parser.parse_args()
    try:
        if args.validate:
            load(args.validate)
        else:
            if not args.directory or not args.output:
                parser.error('directory and output are required unless --validate is used')
            collate(args.directory, args.output, args.expected)
    except PacketError as error:
        print('checklist worker packets: ' + str(error), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
