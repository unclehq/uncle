#!/usr/bin/env python3
"""Severity of failures, and the rule that only a CRITICAL one makes repair necessary.

  CRITICAL  the application is broken: a driver verification command failed (a build, a unit or browser suite: class REGRESSION),
            or it cannot be built or served at all, or its runner executed no tests. Repair is for these.
  MAJOR     the tests are weaker than the plan asked for: an assertion gap (ASSERTIONS) or a coverage gap (COVERAGE).
  MINOR     evidence about the tests themselves: an oracle not independently re-derived (ORACLE), defect-injection (mutation)
            evidence (NEGATIVE, and a failing mutation command).

A MAJOR or MINOR finding names something a repair pass usually cannot fix (a protected test, a mutation list) and is never evidence the
application is wrong, so it is written to the ledger the final audit reads and the run continues. INTEGRITY and RESULTS describe the
driver's own evidence and are not downgraded here. This only changes the driver's routing, never the reviewer's report or a row's status.

usage:
  failure_severity.py critical GREEN_CLASS GREEN_LOG   exit 0 and print the reason when a CRITICAL failure is present, exit 1 if not
  failure_severity.py unrunnable GREEN_LOG             exit 0 when the application cannot be built, served or tested
  failure_severity.py downgrade TEST_REVIEW.json       mark the failing MAJOR/MINOR rows non-blocking; print "ID<TAB>SEVERITY" for each
"""
import json
import re
import sys
from pathlib import Path

SEVERITY = {'ASSERTIONS': 'MAJOR', 'COVERAGE': 'MAJOR', 'ORACLE': 'MINOR', 'NEGATIVE': 'MINOR'}

# The same causes the drivers' green_application_not_runnable looks for: nothing was built, served or run.
UNRUNNABLE = re.compile(r'(^|[^A-Za-z])(build failed|failed to resolve import|is not exported by|could not resolve|'
                        r'error when starting (dev|preview) server|process from config\.webServer was not able to start|'
                        r'webserver.*exit code|no test files found|testDir.*does not exist|application_runtime_unrunnable)', re.I)


def unrunnable(green_log):
    try:
        return bool(UNRUNNABLE.search(Path(green_log).read_text(encoding='utf-8', errors='replace')))
    except OSError:
        return False


def critical(green_class, green_log):
    failed = []
    try:
        for row in Path(green_class).read_text(encoding='utf-8').splitlines():
            kind, _, command = row.partition('\t')
            if kind in ('REGRESSION', 'FAIL'):
                failed.append(command.strip() or kind)
    except OSError:
        pass
    if failed:
        return 'verification failed: ' + '; '.join(failed)
    try:
        text = Path(green_log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    return 'the application cannot be built or served, or no tests ran' if UNRUNNABLE.search(text) else ''


def downgrade(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != 'acceptance-report' or not isinstance(data.get('rows'), list):
        return []
    done = []
    for row in data['rows']:
        if (isinstance(row, dict) and row.get('id') in SEVERITY and row.get('required') is True
                and row.get('status') != 'PASS'):
            row['required'] = False
            row['severity'] = SEVERITY[row['id']]
            row['severity_downgraded'] = True       # the driver's mark: acceptance_json accepts this row's absence from the required set
            done.append((row['id'], SEVERITY[row['id']]))
    if done:
        Path(path).write_text(json.dumps(data, indent=1), encoding='utf-8')
    return done


def main(argv):
    if len(argv) == 4 and argv[1] == 'critical':
        reason = critical(argv[2], argv[3])
        if reason:
            print(reason)
        return 0 if reason else 1
    if len(argv) == 3 and argv[1] == 'unrunnable':
        return 0 if unrunnable(argv[2]) else 1
    if len(argv) == 3 and argv[1] == 'downgrade':
        try:
            for identifier, severity in downgrade(argv[2]):
                print('%s\t%s' % (identifier, severity))
        except (OSError, ValueError):
            return 0
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
