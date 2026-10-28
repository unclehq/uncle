"""Reconstruct a plan's full narrative from a small patch.

The synthesis stage that revises an approved plan after adversarial review
only has to change what the review found. Asking it to reproduce every
unaffected section too made its output proportional to the whole plan's size
instead of to the size of the review -- the dominant cost on a slow model.

A patch names only what changed: change a snippet inside an existing section
(`replace_text`, or `replace_item` for a row or entry that begins with a plan ID such as `T-33`), replace a section's whole body by its exact heading text
(`edit_sections`), or insert a whole new section next to one that already
exists (`insert_sections`). Sections are the plan's own
`## ` headings, numbered or not; nested `### ` headings stay inside whichever
section's body they already live in. Everything not named in the patch is
carried over from the base narrative byte for byte.
"""
import re

HEADING_RE = re.compile(r'(?m)^## .+$')

# A table row or list entry that begins with one of the plan's own IDs (`| T-33 | ...`, `- C-3 -> ...`, `B-7: ...`).
ITEM_RE = re.compile(r'^\s*(?:[-*+]\s+|\|\s*|\d+\.\s+)?[*_`]*([A-Z]{1,4}-\d+)\b')
UNRESOLVED = '\0unresolved item '   # an `old` no section contains: sends an unplaceable item edit down the "missing text" path


def split_sections(narrative):
    """(preamble, [{'heading': str, 'body': str}, ...]).

    `preamble` is whatever precedes the first `## ` heading (a title line,
    usually) with no trailing blank lines. Each section's `body` keeps
    whatever whitespace originally followed its heading -- a section may or
    may not have a blank line before its first line -- stripped only of
    trailing newlines, so an untouched section reproduces exactly."""
    matches = list(HEADING_RE.finditer(narrative))
    if not matches:
        return narrative.rstrip('\n'), []
    preamble = narrative[:matches[0].start()].rstrip('\n')
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(narrative)
        sections.append({'heading': match.group().rstrip(), 'body': narrative[match.end():end].rstrip('\n')})
    return preamble, sections


def join_sections(preamble, sections):
    """The inverse of split_sections(): one blank line between sections,
    whatever whitespace each section's own body carries after its heading."""
    parts = [preamble] if preamble.strip() else []
    for section in sections:
        parts.append(section['heading'] + section['body'])
    return '\n\n'.join(part for part in parts if part.strip()) + '\n'


def _heading_and_body(content):
    """Split a whole new section's `content` (heading line included) into
    (heading, body), the same convention split_sections() uses: whatever
    whitespace follows the heading is kept, only trailing newlines are cut.
    Raises if `content` does not start with a `## ` line."""
    stripped = content.lstrip('\n')
    match = HEADING_RE.match(stripped)
    if not match:
        raise ValueError('insert_sections: "content" must start with a "## " heading line')
    return match.group().rstrip(), stripped[match.end():].rstrip('\n')


def item_lines(body):
    """[(id, line)] for every line of `body` that begins with a plan ID."""
    return [(match.group(1), line) for line in body.split('\n') for match in [ITEM_RE.match(line)] if match]


def expand_items(narrative, patch, strict=True):
    """The patch with each `replace_item` turned into the `replace_text` that replaces that item's line.

    `replace_item`: [{'heading': the section, 'item': an ID such as 'T-33', 'new': the whole replacement line}].
    The ID names the line, so the writer has nothing to copy.  The section it names is only a hint: an ID that
    begins exactly one line of that section is that line, else exactly one line anywhere in the plan.  An item
    that cannot be placed raises ValueError when `strict`; otherwise it becomes an edit whose `old` text is in
    no section, which the caller handles like any other edit of text that is not there."""
    if not isinstance(patch, dict) or not patch.get('replace_item'):
        return patch
    sections = split_sections(narrative)[1]
    placed = list(patch.get('replace_text') or [])
    for op in patch['replace_item']:
        if not isinstance(op, dict) or not isinstance(op.get('item'), str) or not isinstance(op.get('new'), str):
            raise ValueError('replace_item entries need "item" and "new"')
        wanted = op['item'].strip().strip('*_`').upper()
        heading = (op.get('heading') or '').strip()
        found = [(section['heading'], line) for section in sections if section['heading'] == heading
                 for name, line in item_lines(section['body']) if name == wanted]
        if len(found) != 1:
            found = [(section['heading'], line) for section in sections
                     for name, line in item_lines(section['body']) if name == wanted]
        if len(found) == 1:
            placed.append({'heading': found[0][0], 'old': found[0][1], 'new': op['new']})
        elif strict:
            raise ValueError('replace_item: %s %s in section %r; name an ID that begins exactly one line of the plan'
                             % (wanted, 'begins %d lines' % len(found) if found else 'begins no line', heading))
        else:
            placed.append({'heading': heading, 'old': UNRESOLVED + wanted, 'new': op['new']})
    return dict({key: value for key, value in patch.items() if key != 'replace_item'}, replace_text=placed)


def apply_patch(narrative, patch):
    """Apply `{'edit_sections': [...], 'replace_text': [...], 'insert_sections': [...]}` to `narrative`.

    edit_sections: [{'heading': exact existing heading text, e.g. '## 7. Title',
                      'content': the section's new body, heading line excluded}]
    replace_text: [{'heading': exact existing heading text, 'old': text that occurs once in that
                     section's body (or `all`: true for every occurrence), 'new': its replacement}]
    insert_sections: [{'content': the whole new section, heading line included,
                        'after': an existing (or already-inserted) heading text,
                        'before': likewise, 'position': 'start'|'end'}]
    An insert with no `after`/`before` and `position` other than 'start'
    appends at the end. `before` wins over `after` if both are given.

    Raises ValueError naming the exact problem -- an edit target that does
    not exist, an insert anchor that does not exist, a heading inserted twice
    -- so a broken patch fails the stage loudly instead of silently dropping
    content the review asked for."""
    if not isinstance(patch, dict):
        raise ValueError('patch must be an object')
    patch = expand_items(narrative, patch)
    preamble, sections = split_sections(narrative)
    by_heading = {section['heading']: index for index, section in enumerate(sections)}

    edited = set()
    for edit in patch.get('edit_sections') or []:
        if not isinstance(edit, dict) or not edit.get('heading') or 'content' not in edit:
            raise ValueError('edit_sections entries need "heading" and "content"')
        heading = edit['heading'].strip()
        if heading not in by_heading:
            raise ValueError('edit_sections: no existing section with heading %r' % heading)
        if heading in edited:
            raise ValueError('edit_sections: duplicate entry for heading %r' % heading)
        edited.add(heading)
        # `content` is the body only, heading excluded, so its own leading
        # whitespace is not a signal to trust -- a model that forgot the
        # blank line would otherwise glue straight onto the heading text.
        # Always insert exactly one.
        content = edit['content'].strip('\n')
        sections[by_heading[heading]]['body'] = ('\n\n' + content) if content else ''

    # replace_text: change a snippet inside a section instead of rewriting the section.  Most review
    # findings change a sentence, a table row or a command; rewriting the whole section made the output
    # (and the time) proportional to the section, not to the change.
    for edit in patch.get('replace_text') or []:
        if (not isinstance(edit, dict) or not edit.get('heading') or not isinstance(edit.get('old'), str)
                or not edit['old'] or not isinstance(edit.get('new'), str)):
            raise ValueError('replace_text entries need "heading", a non-empty "old" and a "new"')
        heading = edit['heading'].strip()
        if heading not in by_heading:
            raise ValueError('replace_text: no existing section with heading %r' % heading)
        section = sections[by_heading[heading]]
        count = section['body'].count(edit['old'])
        if count == 0:
            raise ValueError('replace_text: %r does not occur in section %r; copy the text exactly as the base '
                             'plan has it' % (edit['old'][:80], heading))
        if count > 1 and not edit.get('all'):
            raise ValueError('replace_text: %r occurs %d times in section %r; include more surrounding text so '
                             'it is unique, or set "all" to true' % (edit['old'][:80], count, heading))
        section['body'] = section['body'].replace(edit['old'], edit['new'])

    for insert in patch.get('insert_sections') or []:
        if not isinstance(insert, dict) or not insert.get('content'):
            raise ValueError('insert_sections entries need "content"')
        heading, body = _heading_and_body(insert['content'])
        if heading in by_heading:
            raise ValueError('insert_sections: heading %r already exists; use edit_sections' % heading)
        before = insert.get('before')
        after = insert.get('after')
        before = before.strip() if isinstance(before, str) else None
        after = after.strip() if isinstance(after, str) else None
        if insert.get('position') == 'start':
            index = 0
        elif before:
            if before not in by_heading:
                raise ValueError('insert_sections: no section with heading %r to insert before' % before)
            index = by_heading[before]
        elif after:
            if after not in by_heading:
                raise ValueError('insert_sections: no section with heading %r to insert after' % after)
            index = by_heading[after] + 1
        else:
            index = len(sections)
        sections.insert(index, {'heading': heading, 'body': body})
        by_heading = {section['heading']: index for index, section in enumerate(sections)}

    return join_sections(preamble, sections)
