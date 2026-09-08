#!/usr/bin/env python3
"""Collect the human inputs a preflight blocker is waiting for.

A blocked prerequisite that needs a person is usually one of two things: a
sign-off that only a human can give, or a file that only a human can supply.
Both were previously provided by hand-editing markdown between runs, which is
the least reliable way to record something a later stage depends on -- the path
gets typed slightly differently, or the statement never gets dated, and a stage
reports "absent" for a thing that exists somewhere else.

This asks for them one blocker at a time and writes what it collected to
--out, one record per line:

    <id>\\tstatement\\t<destination path>\\t<the typed statement>
    <id>\\tcopy\\t<destination path>\\t<the source path>
    <id>\\tskip\\t\\t

It writes nothing into the project itself. The driver applies these records,
so that file writing stays out of a curses loop and can be tested on its own.

Exit 0 when at least one blocker was answered, 1 when the operator skipped
everything or dismissed the dialog, 2 when there is no terminal to draw on.
"""

import os
import re
import sys

EXIT_NOTHING = 1
EXIT_NO_TERMINAL = 2

# A path mentioned in a blocker's evidence, used to prefill the destination.
PATH = re.compile(r"[\w.\-/]*/[\w.\-/]+\.[A-Za-z0-9]+")


def suggested_path(evidence):
    m = PATH.search(evidence or "")
    if not m:
        return ""
    # Runs made before the state directory was renamed still name the old one.
    return m.group(0).replace(".uncle/workspace/", ".uncle/workflow/")


class Blocker(object):
    def __init__(self, spec):
        parts = (spec.split("\t") + ["", ""])[:3]
        self.id = parts[0].strip()
        self.status = parts[1].strip()
        self.evidence = parts[2].strip()
        self.action = "skip"
        self.target = suggested_path(self.evidence)
        self.payload = ""


def draw(stdscr, report, blockers):
    import curses

    color = {"title": 0, "bad": curses.A_BOLD, "muted": curses.A_DIM,
             "warning": curses.A_BOLD, "good": 0, "cursor": 0}
    if curses.has_colors():
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except Exception:
                bg = curses.COLOR_BLACK
            for i, (name, fg, attr) in enumerate(
                    [("title", curses.COLOR_CYAN, curses.A_BOLD),
                     ("bad", curses.COLOR_RED, curses.A_BOLD),
                     ("warning", curses.COLOR_YELLOW, 0),
                     ("good", curses.COLOR_GREEN, 0)], start=1):
                curses.init_pair(i, fg, bg)
                color[name] = curses.color_pair(i) | attr
            curses.init_pair(5, curses.COLOR_YELLOW, bg)
            color["cursor"] = curses.color_pair(5)
        except Exception:
            pass

    def render(lines, entry_label=None, buf=""):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        width = min(max(60, max([len(t) for _, t in lines] or [60]) + 6), max(24, w - 2))
        height = min(len(lines) + (5 if entry_label else 3), max(8, h - 2))
        win = stdscr.derwin(height, width, max(0, (h - height) // 2),
                            max(0, (w - width) // 2))
        win.erase()
        try:
            win.box()
        except Exception:
            pass
        title = " Human input needed "
        try:
            win.addnstr(0, max(1, (width - len(title)) // 2), title,
                        width - 2, color["title"])
        except Exception:
            pass
        row = 1
        for attr, text in lines:
            if row >= height - (4 if entry_label else 2):
                break
            if text:
                try:
                    win.addnstr(row, 2, text, width - 4, color.get(attr, 0))
                except Exception:
                    pass
            row += 1
        if entry_label:
            try:
                win.addnstr(height - 3, 2, entry_label, width - 4, color["muted"])
                visible = buf[-(width - 7):] if len(buf) > width - 7 else buf
                win.addnstr(height - 2, 2, "> " + visible, width - 4)
                if len(visible) < width - 7:
                    win.addstr(height - 2, 4 + len(visible), "█", color["cursor"])
            except Exception:
                pass
        win.refresh()

    def ask(lines, label):
        buf = ""
        while True:
            render(lines, label, buf)
            try:
                key = stdscr.get_wch()
            except Exception:
                key = stdscr.getch()
            if isinstance(key, str):
                if key in ("\n", "\r"):
                    return buf.strip()
                if key in ("\x1b", "\x03"):
                    return None
                if key in ("\x7f", "\b"):
                    buf = buf[:-1]
                elif key.isprintable():
                    buf += key
            else:
                if key in (10, 13):
                    return buf.strip()
                if key == 27:
                    return None
                if key in (curses.KEY_BACKSPACE, 127, 8):
                    buf = buf[:-1]

    curses.curs_set(1)
    answered = 0
    for n, b in enumerate(blockers, start=1):
        head = [
            ("title", "Blocker %d of %d: %s   [%s]" % (n, len(blockers), b.id, b.status)),
            ("", ""),
        ]
        for chunk in [b.evidence[i:i + 62] for i in range(0, len(b.evidence), 62)][:4]:
            head.append(("warning", "  " + chunk))
        head += [
            ("", ""),
            ("", "This is waiting on a person. Provide it here and it is"),
            ("", "written where the next run will look, with a date."),
            ("", ""),
            ("good", "  s  record a signed statement now"),
            ("good", "  f  point at a file to copy in"),
            ("muted", "  k  skip this one"),
            ("muted", "  q  stop and leave the run pending"),
        ]
        while True:
            render(head)
            try:
                key = stdscr.get_wch()
            except Exception:
                key = stdscr.getch()
            k = key if isinstance(key, str) else (chr(key) if 32 <= key < 127 else "")
            if k in ("q", "Q", "\x1b"):
                return answered
            if k in ("k", "K"):
                break
            if k in ("s", "S", "f", "F"):
                is_copy = k in ("f", "F")
                target = ask(head, "Write it to (Enter to accept, Esc to go back):"
                             if not is_copy else
                             "Copy it to (Enter to accept, Esc to go back):")
                if target is None:
                    continue
                target = target or b.target
                if not target:
                    continue
                prompt = ("Path of the file to copy:" if is_copy
                          else "Statement (who approved what, in your words):")
                payload = ask(head + [("", ""), ("muted", "  -> " + target)], prompt)
                if payload is None or not payload:
                    continue
                b.action = "copy" if is_copy else "statement"
                b.target = target
                b.payload = payload
                answered += 1
                break
    return answered


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    report, out = "the report", ""
    while argv and argv[0].startswith("--"):
        flag = argv.pop(0)
        value = argv.pop(0) if argv else ""
        if flag == "--report":
            report = value or report
        elif flag == "--out":
            out = value
    blockers = [Blocker(a) for a in argv if a.strip()]
    blockers = [b for b in blockers if b.id]
    if not blockers or not out:
        return EXIT_NOTHING

    if not sys.stderr.isatty():
        return EXIT_NO_TERMINAL
    try:
        import curses
    except Exception:
        return EXIT_NO_TERMINAL
    try:
        tty_in = open("/dev/tty", "rb", buffering=0)
        tty_out = open("/dev/tty", "w")
    except Exception:
        return EXIT_NO_TERMINAL

    answered = 0
    try:
        os.dup2(tty_in.fileno(), 0)
        os.dup2(tty_out.fileno(), 1)
        answered = curses.wrapper(draw, report, blockers)
    except Exception:
        return EXIT_NO_TERMINAL
    finally:
        for fh in (tty_in, tty_out):
            try:
                fh.close()
            except Exception:
                pass

    if not answered:
        return EXIT_NOTHING
    try:
        with open(out, "w") as fh:
            for b in blockers:
                if b.action == "skip":
                    continue
                fh.write("%s\t%s\t%s\t%s\n" % (b.id, b.action, b.target, b.payload))
    except IOError:
        return EXIT_NOTHING
    return 0


if __name__ == "__main__":
    sys.exit(main())
