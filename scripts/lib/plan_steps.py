"""Implementation steps, independent of the Markdown layout chosen by a planner."""
import re

HEADING = re.compile(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$')
IMPLEMENTATION = re.compile(r'^(?:\d+[.)]\s*)?Implementation\s+(?:order|steps|sequence|plan)\b', re.I)
LABEL = r'\d+[a-z]*'
PREFIX = r'(?:Step\s+|S[ ._-]*|#)?'
FIELD = re.compile(r'(?<!\w)(?:\*\*|__)?(Owns(?:\s*\([^)]*\))?|Depends\s+on)(?:\*\*|__)?\s*:(?:\*\*|__)?\s*', re.I)


def plain(value):
    return value.replace('**', '').replace('__', '').strip()


def head(line):
    """(label, title/body, original task line), or None for ordinary prose."""
    value = line.strip()
    heading = HEADING.match(line)
    if heading:
        value = heading[2]
    value = re.sub(r'^[-*+]\s+', '', value)
    # An ordered list may wrap a separately labelled step.
    value = re.sub(r'^\d+\.\s+(?=(?:\*\*|__)?Step\s)', '', value, flags=re.I)
    match = re.match(r'^(?:\*\*|__)?' + PREFIX + '(' + LABEL + r')\s*[:.)\-–—]\s*(.*)$', value, re.I)
    if not match:
        match = re.match(r'^(?:\*\*|__)?Step\s*()[:.)\-–—]\s*(.*)$', value, re.I)
    if not match:
        return None
    label, title = match.groups()
    if value.startswith(('**', '__')):
        marker = value[:2]
        title = title.replace(marker, '', 1)
    return label, title, title


def sections(narrative):
    """Implementation spans with byte offsets; fenced examples never delimit sections."""
    result, active, fence, offset = [], None, '', 0
    for line in narrative.splitlines(keepends=True):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if not fence:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = ''
            offset += len(line)
            continue
        heading = HEADING.match(line.rstrip('\r\n')) if not fence else None
        if heading:
            implementation = IMPLEMENTATION.match(plain(heading[2]))
            if active and (implementation or (len(heading[1]) <= active['level'] and not re.match(r'(?:\*\*|__)?Step\s+' + LABEL + r'\b', heading[2], re.I))):
                active['end'] = offset
                result.append(active)
                active = None
            if implementation:
                active = dict(start=offset, body_start=offset + len(line), level=len(heading[1]),
                              heading=line.rstrip('\r\n'))
        offset += len(line)
    if active:
        active['end'] = len(narrative)
        result.append(active)
    return result


def paths(value):
    ticks = re.findall(r'`([^`]+)`', value)
    values = ticks or [part.strip().split(' ', 1)[0].rstrip('.;:') for part in plain(value).split(',') if part.strip()]
    result = []
    for token in values:
        while token.startswith('./'):
            token = token[2:]
        if token and not token.startswith('/') and (ticks or '/' in token or '.' in token or token == '*'):
            result.append(token)
    return result


def references(value):
    value = re.split(r'\.\s|\.$', plain(value), maxsplit=1)[0]
    result = []
    for match in re.finditer(PREFIX + '(' + LABEL + r')(?:\s*-\s*(' + LABEL + r'))?', value, re.I):
        low, high = match.groups()
        if high and low.isdigit() and high.isdigit() and 0 <= int(high) - int(low) < 100:
            result.extend(str(n) for n in range(int(low), int(high) + 1))
        else:
            result.append(low.lower())
    return result


def fields(line):
    matches = list(FIELD.finditer(line))
    values = []
    for n, match in enumerate(matches):
        end = matches[n + 1].start() if n + 1 < len(matches) else len(line)
        value = line[match.end():end].strip().rstrip(' —–-')
        values.append(('owns' if match[1].lower().startswith('owns') else 'depends_on', value))
    return (line[:matches[0].start()].rstrip(' —–-') if matches else line), values


def table_rows(lines):
    columns, rows = None, {}
    for i, line in enumerate(lines):
        if not line.lstrip().startswith('|'):
            continue
        cells = [cell.strip() for cell in re.split(r'(?<!\\)\|(?=(?:[^`]*`[^`]*`)*[^`]*$)', line.strip().strip('|'))]
        if not cells:
            continue
        if plain(cells[0]).lower() in ('step', 'steps', '#', 'id', 'no.', 'number'):
            columns = [plain(cell).lower() for cell in cells]
            continue
        label = re.fullmatch(PREFIX + '(' + LABEL + ')', plain(cells[0]), re.I)
        if columns and label:
            title, metadata, extra = '', [], []
            for column, value in zip(columns[1:], cells[1:]):
                if re.match(r'owns|paths?|files?', column):
                    metadata.append(('owns', value))
                elif column.startswith('depend'):
                    metadata.append(('depends_on', value))
                elif not title and re.match(r'desc|title|task|work|what|summary|name', column):
                    title = value
                elif value:
                    extra.append(column + ': ' + value)
            if not title and len(cells) > 1:
                title = cells[1]
            rows[i] = (label[1], title, metadata, extra)
    return rows


def extract_body(body):
    """Return records and prefix prose. Numbers remain literal for existing numbered plans."""
    lines = body.splitlines()
    rows = table_rows(lines)
    table_labels = {row[0].lower() for row in rows.values()}
    steps, prefix, current, fence, continuation = [], [], None, '', False
    starts = [len(line) - len(line.lstrip()) for line in lines if head(line)]
    base = min(starts, default=0)
    for i, line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker or fence:
            (current['_body'] if current else prefix).append(line[3:] if current and line.startswith('   ') else line)
            if marker:
                if not fence:
                    fence = marker[1][0]
                elif marker[1][0] == fence:
                    fence = ''
            continue
        metadata, extra = [], []
        found = head(line)
        if found and len(line) - len(line.lstrip()) > base:
            found = None
        prose = re.match(r'^\s*(?:[-*+]\s*)?' + PREFIX + '(' + LABEL + r')\s+(?=(?:\*\*|__)?Owns\b)(.*)$', line, re.I)
        if rows and i in rows:
            label, title, metadata, extra = rows[i]
            found = (label, title, title)
        elif rows and line.lstrip().startswith('|'):
            continue
        elif prose:
            label, rest = prose.groups()
            target = next((s for s in steps if s['label'].lower() == label.lower()), None)
            if target:
                _, values = fields(rest)
                for key, value in values:
                    target[key].extend(paths(value) if key == 'owns' else references(value))
                continue
            found = (label, '', '')
            _, metadata = fields(rest)
        elif rows and found and found[0].lower() in table_labels:
            prefix.append(line)
            continue
        if found:
            label, title, task = found
            label = label or str(len(steps) + 1)
            title, inline = fields(title)
            metadata = inline + metadata
            bold = re.match(r'^\*\*(.+?)\*\*\s*(?:[—–:-]+\s*)?(.*)$', title)
            if bold:
                title, text = bold.groups()
            elif re.match(r'^\s*\d+\.\s', line) and not re.match(r'^\s*\d+\.\s+(?:\*\*|__)?Step\b', line, re.I):
                title, text = '', title
            else:
                title, text = plain(title), ''
            current = dict(id='step-' + label, number=int(label) if label.isdigit() else len(steps) + 1,
                           label=label, title=title, text='', owns=[], depends_on=[], _body=[text] if text else [],
                           _task=task + ''.join(' ' + ('Owns: ' if key == 'owns' else 'Depends on: ') + value for key, value in metadata if (key, value) not in inline), _line=line)
            if not re.match(r'^\s*\d+\.\s', line) and i not in rows:
                current['_heading'] = re.sub(r'^#+\s*', '', line.strip())
                current['_heading_line'] = line
                current['_task'] = 'Step %s: %s' % (label, current['_task'])
            current['_body'].extend(extra)
            steps.append(current)
            continuation = False
        elif current:
            remaining, metadata = fields(line)
            if metadata:
                if remaining.strip(' -*+_'):
                    current['_body'].append(remaining)
            elif continuation == 'owns' and re.fullmatch(r'\s*(?:[-*+]\s*)?(?:`[^`]+`[,\s]*)+\s*', line):
                metadata = [('owns', line)]
            elif continuation == 'depends_on' and re.fullmatch(r'\s*(?:[-*+]\s*)?(?:Step\s+)?' + LABEL + r'[, \d]*', line, re.I):
                metadata = [('depends_on', line)]
            else:
                current['_body'].append(line[3:] if line.startswith('   ') else line)
                continuation = False
        else:
            prefix.append(line)
        if current:
            for key, value in metadata:
                current[key].extend(paths(value) if key == 'owns' else references(value))
                continuation = key
    # Alphabetic labels have no numeric identity. Map the whole section in order.
    mapped = any(not s['label'].isdigit() for s in steps)
    positions = {s['label'].lower(): (n if mapped else s['number']) for n, s in enumerate(steps, 1)}
    for n, step in enumerate(steps, 1):
        if mapped:
            step['number'] = n
            step['id'] = 'step-%d' % n
        step['text'] = '\n'.join(step.pop('_body')).strip()
        step['owns'] = list(dict.fromkeys(step['owns']))
        step['depends_on'] = list(dict.fromkeys(positions.get(ref, int(ref) if ref.isdigit() else ref) for ref in step['depends_on']))
    return steps, '\n'.join(prefix).strip()


def extract(narrative):
    return [step for section in sections(narrative)
            for step in extract_body(narrative[section['body_start']:section['end']])[0]]


def split_for_model(narrative):
    """Keep the existing H2 section ids, but recognize implementation spans at any level."""
    spans = sections(narrative)
    markers = [(m.start(), m.end(), m[0]) for m in re.finditer(r'^## .+$', narrative, re.M)
               if not any(s['start'] <= m.start() < s['end'] for s in spans)]
    markers += [(s['start'], s['body_start'] - 1, s['heading']) for s in spans]
    markers.sort()
    if not markers:
        return narrative.rstrip('\n'), []
    result = []
    for n, (start, end, heading) in enumerate(markers):
        stop = markers[n + 1][0] if n + 1 < len(markers) else len(narrative)
        span = next((s for s in spans if s['start'] == start), None)
        if span:
            stop = span['end']
        result.append(dict(heading=heading, body=narrative[end:stop].rstrip('\n')))
        # An H1 sibling after an H1 implementation is not an H2 marker.
        if span and stop < (markers[n + 1][0] if n + 1 < len(markers) else len(narrative)):
            tail_end = markers[n + 1][0] if n + 1 < len(markers) else len(narrative)
            result.append(dict(heading='##', body=narrative[stop:tail_end].rstrip('\n')))
    return narrative[:markers[0][0]].rstrip('\n'), result


def normalize(narrative):
    """Standardize alternate layouts, leaving already numbered lists and all other bytes alone."""
    from plan_model import render_block
    for section in reversed(sections(narrative)):
        body = narrative[section['body_start']:section['end']]
        steps, prefix = extract_body(body)
        if not steps or all(re.match(r'^\s*\d+\.\s', step['_line']) for step in steps):
            continue
        positions = {step['number']: n for n, step in enumerate(steps, 1)}
        for n, step in enumerate(steps, 1):
            step['depends_on'] = [positions.get(dep, dep) for dep in step['depends_on']]
            step['number'] = n
        rendered = render_block({'kind': 'steps', 'items': steps})
        leading = re.match(r'^\s*\n', body)
        trailing = re.search(r'\s*$', body)[0]
        replacement = (leading[0] if leading else '\n') + (prefix + '\n\n' if prefix else '') + rendered + trailing
        narrative = narrative[:section['body_start']] + replacement + narrative[section['end']:]
    return narrative
