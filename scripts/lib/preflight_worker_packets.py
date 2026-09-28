"""Collate parallel preflight-lens worker packets into one acceptance report.

Each worker probes an assigned lens (tooling, data, reviewers) and returns a
subset of acceptance-gate rows in the same shape the single-agent preflight
path already produces. A live, side-effecting lens (browser/GUI) runs
serially, outside this panel, and its rows are merged in the same way.
"""
import json
import sys
from pathlib import Path

SCHEMA = 'uncle.artifact/v1'
STATUSES = ('PASS', 'FAIL', 'BLOCKED-SETUP', 'BLOCKED-HUMAN', 'BLOCKED-IMPOSSIBLE', 'NOT RUN', 'N/A')


class PacketError(ValueError):
    pass


def load(path, lens):
    name = Path(path).name
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise PacketError('%s: worker packet is missing (lens %s)' % (name, lens))
    except (OSError, json.JSONDecodeError) as error:
        raise PacketError('%s: invalid JSON worker packet: %s' % (name, error)) from error
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('kind') != 'preflight-worker-packet':
        raise PacketError('%s: expected schema %s and kind preflight-worker-packet' % (name, SCHEMA))
    rows = value.get('rows')
    if not isinstance(rows, list):
        raise PacketError('%s: rows must be an array' % name)
    out = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise PacketError('%s: row %d must be an object' % (name, i))
        identifier = row.get('id')
        status = row.get('status')
        required = row.get('required')
        evidence = row.get('evidence')
        if not isinstance(identifier, str) or not identifier.strip():
            raise PacketError('%s: row %d needs a nonempty id' % (name, i))
        if not isinstance(required, bool):
            raise PacketError('%s: row %d (%s) required must be a JSON boolean' % (name, i, identifier))
        if status not in STATUSES:
            raise PacketError('%s: row %d (%s) has an invalid status %r' % (name, i, identifier, status))
        if not isinstance(evidence, str) or not evidence.strip():
            raise PacketError('%s: row %d (%s) needs nonempty evidence' % (name, i, identifier))
        if '|' in identifier or '|' in evidence:
            raise PacketError('%s: row %d (%s) must not contain a literal pipe character' % (name, i, identifier))
        out.append({'id': identifier.strip(), 'required': required, 'status': status, 'evidence': evidence.strip()})
    return out


def collate(directory, output, expected):
    """expected: [(lens, path), ...] in the order lenses ran."""
    seen = {}
    rows = []
    for lens, path in expected:
        for row in load(path, lens):
            if row['id'] in seen:
                raise PacketError('row id %r appears in both the %s and %s lenses; lens boundaries must not overlap'
                                   % (row['id'], seen[row['id']], lens))
            seen[row['id']] = lens
            rows.append(row)
    if not rows:
        raise PacketError('no acceptance-gate rows were returned by any lens')
    payload = {'schema': SCHEMA, 'kind': 'acceptance-report', 'rows': rows}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return payload


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    parser.add_argument('output')
    parser.add_argument('--expected', nargs='+', required=True, help='lens names; <directory>/<lens>.json is read for each')
    args = parser.parse_args(argv)
    expected = [(lens, str(Path(args.directory) / (lens + '.json'))) for lens in args.expected]
    try:
        collate(args.directory, args.output, expected)
    except PacketError as error:
        print('preflight worker packets: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
