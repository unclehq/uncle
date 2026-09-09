#!/usr/bin/env python3
"""Derive an approved parallel-execution plan for MANUAL_CHECKLIST.md.

The checklist stage is told to run independent checks concurrently. Left at
that, the executing agent has to infer what "independent" means from rows that
were never written to answer the question, and a wrong guess does not fail
loudly: two checks sharing a port produce a FAIL that looks like a defect in
the product rather than a defect in the schedule.

The verification commands solved this years earlier in this same repository.
The plan declares `## Parallel verification groups`, the driver validates them,
the test review audits their isolation, and parallel_checks.py runs them with a
barrier between groups. What may overlap is decided by someone other than the
agent whose results depend on the answer.

This is that design for the checklist. The reviewer who writes MANUAL_CHECKLIST.md
declares, per check, the resources it needs exclusively and the checks it
depends on. Those two facts are the safety-relevant judgment and they stay with
the independent reviewer. The layering itself is arithmetic, so it is done here
rather than typed out a second time by hand -- a hand-written group list is one
more thing that can contradict the per-check declarations, and the contradiction
would be invisible.

Conservative in both directions that matter:

  * A check that declares no resources runs alone. A checklist written before
    this existed therefore runs exactly as it runs today, one check at a time,
    rather than being read as "safe to overlap with everything".
  * Declarations that do not make sense -- an unknown dependency, an edge
    pointing forward through the checklist --
    do not stop the run. They fall back to serial and say so. Parallelism is an
    optimization; refusing to verify the product because a reviewer mistyped a
    check ID would trade a real verification pass for a formatting nit. Serial
    is always correct, so serial is the failure mode.
"""

import argparse
import os
import re
import sys

# MC-001, and anything shaped like it: a prefix, a hyphen, a number. The change
# pipeline standardizes on MC; the new-application checklist prompt does not
# name a format, so do not require one.
ID = r"[A-Z][A-Z0-9]{0,7}-\d{1,4}"

# A check begins at a heading that leads with its ID, or at an explicit
# "Check ID:" field. Both layouts appear in practice, and a bare ID token is
# deliberately not enough: the traceability matrix at the end of the checklist
# is full of them.
HEADING = re.compile(r"^#{1,6}\s+(?:check\s+)?(%s)\b" % ID, re.I)
CHECK_ID = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*|__)?check\s*id(?:\*\*|__)?\s*[:|]\s*(%s)\b" % ID, re.I)
FIELD = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*|__)?"
    r"(exclusive\s+resources?|depends\s+on)"
    r"(?:\*\*|__)?\s*:\s*(.*?)\s*$", re.I)

# A dense checklist is a table, not a list of fields, and the prompt that asks
# for density gets tables back. The column headers are abbreviated when they are
# in a header row, so accept both spellings.
ID_HEADERS = ("id", "check", "check id", "checkid")
RESOURCE_HEADERS = ("excl", "exclusive", "exclusive resource", "exclusive resources",
                    "resources", "resource")
DEPEND_HEADERS = ("deps", "dep", "depends", "depends on", "dependencies",
                  "dependency", "after")
SEPARATOR = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def table_cells(line):
    """The cells of a markdown table row, or None if this is not one."""
    if "|" not in line:
        return None
    row = line.strip()
    if not row.startswith("|"):
        return None
    cells = [c.strip() for c in row.strip("|").split("|")]
    return cells


def header_columns(cells):
    """Map a header row to the columns worth reading, or None.

    Both an ID column and at least one declaration column have to be present.
    A table with neither -- the traceability matrix every checklist ends with,
    whose ID column is full of check IDs -- must not be read as checks, or the
    grouping would list rows that are not checks at all.
    """
    if not cells:
        return None
    want = {}
    for i, cell in enumerate(cells):
        name = cell.strip().strip("*_`").lower()
        if name in ID_HEADERS and "id" not in want:
            want["id"] = i
        elif name in RESOURCE_HEADERS and "resources" not in want:
            want["resources"] = i
        elif name in DEPEND_HEADERS and "depends" not in want:
            want["depends"] = i
    if "id" not in want or ("resources" not in want and "depends" not in want):
        return None
    return want

# The resource a check with no declaration is assumed to need: all of them.
EVERYTHING = "*"

NONE_WORDS = {"none", "n/a", "na", "-", "--", "nil", "no", "(none)", "none."}


class Check(object):
    def __init__(self, cid, order):
        self.id = cid
        self.order = order
        self.resources = None       # None means "never declared"
        self.depends = []

    @property
    def declared(self):
        return self.resources is not None

    @property
    def needs(self):
        """The resource set to schedule against."""
        if not self.declared:
            return {EVERYTHING}
        return self.resources


def split_list(value):
    """Split a declared list on commas, semicolons, or the word 'and'."""
    parts = re.split(r"[,;]|\band\b", value)
    return [p.strip() for p in parts if p.strip()]


def is_none(value):
    return value.strip().lower().strip(".") in {w.strip(".") for w in NONE_WORDS}


def set_resources(check, value):
    value = value.strip().strip("`").strip("*_").strip()
    if is_none(value) or not value:
        check.resources = set()
    else:
        check.resources = {r.lower() for r in split_list(value)}


def set_depends(check, value):
    value = value.strip().strip("`").strip("*_").strip()
    if is_none(value) or not value:
        check.depends = []
    else:
        check.depends = [d.upper() for d in re.findall(ID, value.upper())]


def parse(text):
    """Return the checks in document order, plus the parse warnings."""
    checks, by_id, warnings = [], {}, []
    current = None
    columns = None            # active table header, while one is in force
    lines = text.splitlines()
    for n, line in enumerate(lines):
        cells = table_cells(line)
        if cells is not None:
            # A header row is one followed by a separator row. Re-evaluating on
            # every header is what stops a later table -- the traceability
            # matrix -- from being read through the previous table's columns.
            nxt = lines[n + 1] if n + 1 < len(lines) else ""
            if SEPARATOR.match(nxt) and "|" in nxt:
                columns = header_columns(cells)
                current = None
                continue
            if columns and not SEPARATOR.match(line):
                idx = columns["id"]
                cid = cells[idx] if idx < len(cells) else ""
                found = re.match(r"^\**\s*(%s)\b" % ID, cid.strip().strip("`"), re.I)
                if found:
                    cid = found.group(1).upper()
                    check = by_id.get(cid)
                    if check is None:
                        check = Check(cid, len(checks))
                        checks.append(check)
                        by_id[cid] = check
                    if "resources" in columns and columns["resources"] < len(cells):
                        set_resources(check, cells[columns["resources"]])
                    if "depends" in columns and columns["depends"] < len(cells):
                        set_depends(check, cells[columns["depends"]])
                    current = None
                    continue
        m = HEADING.match(line) or CHECK_ID.match(line)
        if m:
            cid = m.group(1).upper()
            if cid in by_id:
                # A repeated ID is the same check being restated (a heading and
                # then a Check ID field, most often). Keep collecting into it.
                current = by_id[cid]
            else:
                current = Check(cid, len(checks))
                checks.append(current)
                by_id[cid] = current
            continue
        if current is None:
            continue
        f = FIELD.match(line)
        if not f:
            continue
        name, value = f.group(1).lower(), f.group(2)
        if name.startswith("exclusive"):
            set_resources(current, value)
        else:
            set_depends(current, value)
    return checks, by_id, warnings


def validate(checks, by_id):
    """Reject declarations that cannot be scheduled. Returns a list of errors."""
    errors = []
    for c in checks:
        for d in c.depends:
            if d == c.id:
                errors.append("%s depends on itself" % c.id)
            elif d not in by_id:
                errors.append("%s depends on %s, which is not a check in this "
                              "checklist" % (c.id, d))
    # Cycles, by iterative depth-first search over the declared edges. A
    # forward edge is legal -- a section ordering that puts a check before the
    # one it needs is a real thing reviewers write, and the declaration is the
    # more reliable of the two signals -- so a cycle is genuinely possible and
    # has to be found rather than inferred from direction.
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict((c.id, WHITE) for c in checks)
    for start in checks:
        if color[start.id] != WHITE:
            continue
        stack = [(start.id, iter([d for d in start.depends if d in by_id]))]
        color[start.id] = GREY
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color.get(nxt) == GREY:
                    errors.append("dependency cycle through %s and %s" % (node, nxt))
                    color[nxt] = BLACK
                elif color.get(nxt) == WHITE:
                    color[nxt] = GREY
                    stack.append((nxt, iter([d for d in by_id[nxt].depends
                                             if d in by_id])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
    return errors


def runs(checks):
    """Pack the checks into ordered groups that may safely overlap.

    Two constraints pull against each other here.

    Document order matters more than it looks like it does. A checklist row
    often leans on state an earlier row left behind without saying so -- a
    logged-in session, a built artifact, a server someone started three checks
    ago -- so rearranging checks is a good way to break a checklist that worked.

    A declared dependency matters more still. When a reviewer writes
    `Depends on: MC-29` on a check that sits above MC-29, that is not a mistake
    to reject; it is the reviewer naming a fact the section ordering could not
    express. Explicit beats adjacent.

    So: document order is the default and the tiebreak, a declared dependency
    can defer a check past checks that come after it, and a check that declared
    nothing is a hard barrier -- it runs alone, and nothing crosses it in either
    direction, because a check whose needs are unknown is exactly the one you
    must not reorder around.
    """
    pending = list(checks)
    placed = {}
    groups = []
    known = set(c.id for c in checks)

    while pending:
        # A check that never declared what it touches goes alone, and only when
        # it is next in the document. Nothing is pulled forward past it, so a
        # checklist with no declarations at all stays strictly serial.
        if not pending[0].declared:
            head = pending.pop(0)
            placed[head.id] = len(groups)
            groups.append([head.id])
            continue

        group, held = [], set()
        for c in pending:
            if not c.declared:
                break                      # the barrier, and everything after it
            if any(d not in placed for d in c.depends if d in known):
                continue                   # deferred: its dependency is later
            if group and (c.needs & held):
                continue                   # would collide inside this group
            group.append(c.id)
            held |= c.needs

        if not group:
            # Nothing here can run: a check is waiting on a dependency that
            # sits behind a check nobody declared, and crossing that barrier is
            # the one thing this is not allowed to do. Say so instead of
            # inventing an order.
            return None

        taken = set(group)
        pending = [c for c in pending if c.id not in taken]
        for cid in group:
            placed[cid] = len(groups)
        groups.append(group)

    return groups


def render_readme(groups, checks, errors, source):
    out = []
    w = out.append
    w("# Parallel execution groups for checklist execution")
    w("")
    if not checks:
        w("NOT DECLARED: no checks were found in %s." % source)
        w("Run the checklist one check at a time, in document order.")
        return "\n".join(out) + "\n"
    if errors:
        w("NOT DECLARED: the checklist's parallel declarations could not be used.")
        w("")
        for e in errors:
            w("  - %s" % e)
        w("")
        w("Run every check one at a time, in document order. Do not overlap")
        w("checks on your own reading of their prerequisites: the declarations")
        w("that were supposed to settle that question did not parse, and a")
        w("guess here produces a failure that looks like a product defect.")
        return "\n".join(out) + "\n"

    undeclared = [c.id for c in checks if not c.declared]
    parallel = sum(1 for g in groups if len(g) > 1)
    w("Derived from the `Exclusive resources` and `Depends on` fields the")
    w("reviewer wrote in %s. Each line below is one group." % source)
    w("")
    w("Checks on the same line have no dependency between them and no declared")
    w("resource in common, so they may overlap. Finish every check in a group")
    w("before starting the next group: a dependency declaration means nothing")
    w("without that barrier.")
    w("")
    w("Overlapping is permission, not obligation. Run fewer at once if the")
    w("machine cannot take it; never run more, and never merge two lines.")
    w("")
    w("```")
    for g in groups:
        w(" ".join(g))
    w("```")
    w("")
    w("%d check(s) in %d group(s); %d group(s) hold more than one check."
      % (sum(len(g) for g in groups), len(groups), parallel))
    if undeclared:
        w("")
        w("%d check(s) declared no exclusive resources and are scheduled alone,"
          % len(undeclared))
        w("which is the conservative reading of a missing declaration rather")
        w("than a claim that they conflict: %s" % ", ".join(undeclared))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checklist", default="MANUAL_CHECKLIST.md")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    try:
        with open(args.checklist, encoding="utf-8") as fh:
            text = fh.read()
    except IOError:
        text = ""

    checks, by_id, _ = parse(text)
    errors = validate(checks, by_id)
    groups = []
    if checks and not errors:
        groups = runs(checks)
        if groups is None:
            groups = []
            errors.append(
                "a check depends on one that sits after a check with no "
                "Exclusive resources line; declare that check's resources so "
                "the dependency can be scheduled, or move it")

    if not os.path.isdir(args.out_dir):
        os.makedirs(args.out_dir)
    groups_path = os.path.join(args.out_dir, "groups.txt")
    readme_path = os.path.join(args.out_dir, "README.md")
    # Stale groups from an earlier checklist must never be read as current.
    if os.path.exists(groups_path):
        os.remove(groups_path)
    if groups:
        with open(groups_path, "w", encoding="utf-8", newline="\n") as fh:
            for g in groups:
                fh.write(" ".join(g) + "\n")

    # What the checklist needs, token by token, with the checks that need it.
    # A stage cannot serve a page it is forbidden to bind a port for, and no
    # amount of retrying changes that, so the driver reads this before running
    # rather than discovering it one BLOCKED row at a time.
    resources_path = os.path.join(args.out_dir, "resources.tsv")
    if os.path.exists(resources_path):
        os.remove(resources_path)
    if checks:
        needed = {}
        for c in checks:
            for token in sorted(c.needs):
                needed.setdefault(token, []).append(c.id)
        with open(resources_path, "w", encoding="utf-8", newline="\n") as fh:
            for token in sorted(needed):
                fh.write("%s\t%s\n" % (token, ",".join(needed[token])))
    with open(readme_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_readme(groups, checks, errors,
                               os.path.basename(args.checklist)))

    if errors:
        for e in errors:
            sys.stderr.write("checklist groups: %s\n" % e)
        return 2
    return 0


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.exit(main())
