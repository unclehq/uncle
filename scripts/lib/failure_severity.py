#!/usr/bin/env python3
"""Severity of failures, and the rule that only a CRITICAL one makes repair necessary.

  CRITICAL  the application is broken: a driver verification command failed in a way that says so -- a build or startup failure, a
            crash with no test summary, a runner that executed no tests, or a test suite where at least half of the tests fail
            (WORKFLOW_CRITICAL_FAIL_RATIO, default 0.5). Repair is for these.
  AUDIT     a final-audit finding is repaired only when its severity is CRITICAL (WORKFLOW_REPAIR_AUDIT_SEVERITY=high adds HIGH) and it is
            not a person's decision: a BLOCKED-HUMAN row, a missing waiver or a subjective judgement is not something a code change fixes.
  ISOLATED  a few tests of a suite fail while the application builds, serves and the rest pass. That is as likely a wrong test as a wrong
            application, and the manual checklist observes the application itself, so it is not critical: it goes to the final audit.
  MAJOR     the tests are weaker than the plan asked for: an assertion gap (ASSERTIONS) or a coverage gap (COVERAGE).
  MINOR     evidence about the tests themselves: an oracle not independently re-derived (ORACLE), defect-injection (mutation)
            evidence (NEGATIVE, and a failing mutation command).

A MAJOR or MINOR finding names something a repair pass usually cannot fix (a protected test, a mutation list) and is never evidence the
application is wrong, so it is written to the ledger the final audit reads and the run continues. INTEGRITY and RESULTS describe the
driver's own evidence and are not downgraded here. This only changes the driver's routing, never the reviewer's report or a row's status.

usage:
  failure_severity.py critical GREEN_CLASS GREEN_LOG   exit 0 and print the reason when a CRITICAL failure is present, exit 1 if not
  failure_severity.py unrunnable GREEN_LOG             exit 0 when the application cannot be built, served or tested
  failure_severity.py isolated GREEN_CLASS GREEN_LOG   exit 0 and print each failed command that is only an isolated test failure
  failure_severity.py downgrade TEST_REVIEW.json [--symptoms]   mark the failing MAJOR/MINOR rows non-blocking; print "ID<TAB>SEVERITY" for each
  failure_severity.py audit-critical FINAL_AUDIT.json  exit 0 and print each final-audit finding a repair is for; exit 1 if there is none
  failure_severity.py scope GREEN_CLASS GREEN_LOG [TEST_REVIEW.json [FINAL_AUDIT.json]]
                                                        print the repair brief: the critical failures to fix, and the rows NOT to touch
"""
import json
import os
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


COUNT = re.compile(r'\b(\d+)\s+(failed|passed)\b', re.I)


def ratio_limit():
    try:
        return float(os.environ.get('WORKFLOW_CRITICAL_FAIL_RATIO', '0.5'))
    except ValueError:
        return 0.5


def command_blocks(green_log):
    """{command: output} from the driver's green-check log, where each command's output follows a `$ command` line."""
    blocks, current, lines = {}, None, []
    try:
        text = Path(green_log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return blocks
    for line in text.splitlines():
        if line.startswith('$ '):
            if current is not None:
                blocks[current] = '\n'.join(lines)
            current, lines = line[2:].strip(), []
        else:
            lines.append(line)
    if current is not None:
        blocks[current] = '\n'.join(lines)
    return blocks


def test_counts(output):
    """(failed, passed) from a test runner's summary, or None when the output has no recognizable summary."""
    failed = passed = 0
    seen = False
    for line in output.splitlines():
        if re.match(r'\s*Test Files\b', line):      # vitest's file counts would double the test counts
            continue
        for number, word in COUNT.findall(line):
            seen = True
            if word.lower() == 'failed':
                failed += int(number)
            else:
                passed += int(number)
    return (failed, passed) if seen else None


def failing_commands(green_class):
    out = []
    try:
        for row in Path(green_class).read_text(encoding='utf-8').splitlines():
            kind, _, command = row.partition('\t')
            if kind in ('REGRESSION', 'FAIL'):
                out.append(command.strip())
    except OSError:
        pass
    return out


def classify_command(command, blocks):
    """('critical'|'isolated', detail) for one failed driver command."""
    output = blocks.get(command, '')
    if UNRUNNABLE.search(output):
        return 'critical', 'the application cannot be built or served'
    counts = test_counts(output)
    if counts is None or counts[0] == 0:
        return 'critical', 'it failed without a test summary (a build, startup or crash failure)'
    failed, passed = counts
    share = failed / float(failed + passed)
    detail = '%d of %d tests failed (%d%%)' % (failed, failed + passed, round(share * 100))
    return ('critical' if share >= ratio_limit() else 'isolated'), detail


def isolated_failures(green_class, green_log):
    """Failed commands that are not critical: [(command, detail)]."""
    blocks = command_blocks(green_log)
    out = []
    for command in failing_commands(green_class):
        kind, detail = classify_command(command, blocks)
        if kind == 'isolated':
            out.append((command, detail))
    return out


def critical(green_class, green_log):
    blocks = command_blocks(green_log)
    failed = []
    for command in failing_commands(green_class):
        kind, detail = classify_command(command, blocks)
        if kind == 'critical':
            failed.append('%s (%s)' % (command or 'a verification command', detail))
    if failed:
        return 'verification failed: ' + '; '.join(failed)
    try:
        text = Path(green_log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    # A clean record can still hide an application that never ran (nothing failed because nothing was built, served or run).
    return 'the application cannot be built or served, or no tests ran' if UNRUNNABLE.search(text) and not failing_commands(green_class) else ''


def downgrade(path, symptoms=False):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != 'acceptance-report' or not isinstance(data.get('rows'), list):
        return []
    done = []
    for row in data['rows']:
        level = SEVERITY.get(row.get('id')) if isinstance(row, dict) else None
        # INTEGRITY and RESULTS only echo the driver's failed commands; once those are judged isolated they are the same finding.
        if level is None and symptoms and isinstance(row, dict) and row.get('id') in ('INTEGRITY', 'RESULTS'):
            level = 'ISOLATED'
        if (isinstance(row, dict) and level and row.get('required') is True and row.get('status') != 'PASS'):
            row['required'] = False
            row['severity'] = level
            row['severity_downgraded'] = True       # the driver's mark: acceptance_json accepts this row's absence from the required set
            done.append((row['id'], level))
    if done:
        Path(path).write_text(json.dumps(data, indent=1), encoding='utf-8')
    return done


def critical_items(green_class, green_log):
    """The failures a repair is for: each critical failed driver command, or the build/serve/no-tests condition."""
    blocks = command_blocks(green_log)
    items = []
    for command in failing_commands(green_class):
        kind, detail = classify_command(command, blocks)
        if kind == 'critical':
            items.append('`%s` failed (%s).' % (command or 'verification', detail))
    if not items and not failing_commands(green_class) and unrunnable(green_log):
        items.append('The application cannot be built or served, or its runner executed no tests (see the green-check log).')
    return items


def deferred_rows(review_json):
    """Failing review rows that are NOT critical: (id, severity, evidence)."""
    out = []
    try:
        data = json.loads(Path(review_json).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return out
    for row in data.get('rows', []) if isinstance(data, dict) else []:
        if not isinstance(row, dict) or row.get('status') in ('PASS', 'N/A', None):
            continue
        ident = row.get('id')
        if ident in SEVERITY:
            out.append((ident, SEVERITY[ident], ' '.join(str(row.get('evidence', '')).split())[:200]))
        elif ident in ('INTEGRITY', 'RESULTS'):
            out.append((ident, 'SYMPTOM', 'reports the driver verification failure above; it clears when that is fixed'))
    return out


AUDIT_RANK = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
HUMAN = re.compile(r'BLOCKED-HUMAN|waiver|human observation|subjective|aesthetic|judg(e)?ment|a person', re.I)


def audit_split(audit_json):
    """([findings to repair], [(finding, why it is left alone)]) from a final audit's JSON; both empty when it cannot be read."""
    try:
        data = json.loads(Path(audit_json).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return [], []
    wanted = AUDIT_RANK.get(os.environ.get('WORKFLOW_REPAIR_AUDIT_SEVERITY', 'critical').strip().upper(), 4)
    repair, left = [], []
    for finding in data.get('findings', []) if isinstance(data, dict) else []:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get('severity', '')).upper()
        text = '%s %s' % (finding.get('evidence', ''), finding.get('required_correction', ''))
        if AUDIT_RANK.get(severity, 0) < wanted:
            left.append((finding, '%s is below the repair threshold' % (severity or 'unrated')))
        elif HUMAN.search(text):
            left.append((finding, 'it needs a person (an observation, a waiver or a judgement), not a code change'))
        else:
            repair.append(finding)
    return repair, left


def audit_line(finding):
    return '**%s** (%s): %s' % (finding.get('id'), str(finding.get('severity', '')).upper(),
                                ' '.join(str(finding.get('required_correction') or finding.get('evidence') or '').split())[:200])


def deferred_commands(green_class, green_log=''):
    """Driver commands that failed but are not critical: isolated test failures, and the defect-injection (mutation) check."""
    out = []
    if green_log:
        for command, detail in isolated_failures(green_class, green_log):
            out.append(('`%s`' % command, 'ISOLATED', '%s; the application builds and serves and the rest pass, so a wrong test is as likely as a wrong application' % detail))
    try:
        for row in Path(green_class).read_text(encoding='utf-8').splitlines():
            kind, _, command = row.partition('\t')
            if kind == 'MUTATION':
                out.append(('`%s`' % command.strip(), 'MINOR', 'defect-injection evidence; it never blocks and a repair pass cannot supply it'))
    except OSError:
        pass
    return out


def scope(green_class, green_log, review_json='', audit_json=''):
    items = critical_items(green_class, green_log)
    to_repair, left_alone = audit_split(audit_json) if audit_json else ([], [])
    items += [audit_line(f) for f in to_repair]
    lines = ['# Repair scope (critical failures only)', '',
             'Repair is for critical failures. Fix exactly these, and nothing else:', '']
    lines += ['- ' + item for item in items] or ['- (none recorded by the driver; read the repair source)']
    deferred = deferred_commands(green_class, green_log) + (deferred_rows(review_json) if review_json else [])
    deferred += [(f.get('id'), str(f.get('severity', '')).upper(), why) for f, why in left_alone]
    if deferred:
        lines += ['', 'Do NOT address these. They are not critical, a repair pass cannot fix them, and the final audit reads them:', '']
        lines += ['- **%s** (%s): %s' % row for row in deferred]
    lines += ['', 'Do not add tests, change protected tests or the defect-injection list, or edit anything unrelated to the failures above.']
    return '\n'.join(lines) + '\n'


def main(argv):
    if len(argv) == 4 and argv[1] == 'critical':
        reason = critical(argv[2], argv[3])
        if reason:
            print(reason)
        return 0 if reason else 1
    if len(argv) == 3 and argv[1] == 'unrunnable':
        return 0 if unrunnable(argv[2]) else 1
    if len(argv) == 3 and argv[1] == 'audit-critical':
        repair, _ = audit_split(argv[2])
        for finding in repair:
            print(audit_line(finding))
        return 0 if repair else 1
    if len(argv) in (4, 5, 6) and argv[1] == 'scope':
        sys.stdout.write(scope(argv[2], argv[3], argv[4] if len(argv) >= 5 else '', argv[5] if len(argv) == 6 else ''))
        return 0
    if len(argv) == 4 and argv[1] == 'isolated':
        found = isolated_failures(argv[2], argv[3])
        for command, detail in found:
            print('%s\t%s' % (command, detail))
        return 0 if found else 1
    if len(argv) in (3, 4) and argv[1] == 'downgrade':
        try:
            for identifier, severity in downgrade(argv[2], symptoms=len(argv) == 4 and argv[3] == '--symptoms'):
                print('%s\t%s' % (identifier, severity))
        except (OSError, ValueError):
            return 0
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
