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


def parse(text):
    """Return the checks in document order, plus the parse warnings."""
    checks, by_id, warnings = [], {}, []
    current = None
    for line in text.splitlines():
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
        # Strip a trailing "(reason)" and markdown emphasis around the value.
        value = value.strip().strip("`").strip()
        if name.startswith("exclusive"):
            if is_none(value) or not value:
                current.resources = set()
            else:
                current.resources = {r.lower() for r in split_list(value)}
        else:
            if is_none(value) or not value:
                current.depends = []
            else:
                current.depends = [d.upper() for d in re.findall(ID, value.upper())]
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
            elif by_id[d].order > c.order:
                # Groups are consecutive runs of the checklist, so a dependency
                # is satisfied by position. Pointing forward asks for a
                # reordering, and reordering checks is how a checklist that
                # relied on an undeclared setup step quietly stops working.
                errors.append("%s depends on %s, which appears after it; put a "
                              "check after the checks it depends on" % (c.id, d))
    # No separate cycle detector: groups are consecutive runs, so every cycle
    # contains at least one forward edge and is already reported above, with a
    # message that names the two checks and what to do about it.
    return errors


def runs(checks):
    """Pack the checks into ordered groups that may safely overlap.

    A group is a consecutive run of the checklist. That is the same shape the
    verification commands already use -- verify_parallel_groups requires
    consecutive command positions -- and it is the reason this can be trusted:
    document order is never rearranged, so a check that quietly assumes an
    earlier check already ran keeps that assumption whether or not anyone
    thought to declare it.

    A run extends to the next check while that check declares no resource the
    run already holds and no dependency on a member of the run. Otherwise a new
    run starts, and everything in the previous one finishes first.

    A check that declared nothing needs EVERYTHING, which collides with every
    run including an empty-resource one, so it lands alone and nothing joins it
    afterwards. An undeclared check is therefore a full barrier, which is the
    conservative reading of "nobody said what this touches".
    """
    groups = []
    current, held = [], set()

    for c in checks:
        needs = c.needs
        conflict = bool(needs & held) or EVERYTHING in needs or EVERYTHING in held
        depends_on_current = any(d in current for d in c.depends)
        if current and (conflict or depends_on_current):
            groups.append(current)
            current, held = [], set()
        current.append(c.id)
        held |= needs

    if current:
        groups.append(current)
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
        with open(args.checklist) as fh:
            text = fh.read()
    except IOError:
        text = ""

    checks, by_id, _ = parse(text)
    errors = validate(checks, by_id)
    groups = [] if (errors or not checks) else runs(checks)

    if not os.path.isdir(args.out_dir):
        os.makedirs(args.out_dir)
    groups_path = os.path.join(args.out_dir, "groups.txt")
    readme_path = os.path.join(args.out_dir, "README.md")
    # Stale groups from an earlier checklist must never be read as current.
    if os.path.exists(groups_path):
        os.remove(groups_path)
    if groups:
        with open(groups_path, "w") as fh:
            for g in groups:
                fh.write(" ".join(g) + "\n")
    with open(readme_path, "w") as fh:
        fh.write(render_readme(groups, checks, errors,
                               os.path.basename(args.checklist)))

    if errors:
        for e in errors:
            sys.stderr.write("checklist groups: %s\n" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
