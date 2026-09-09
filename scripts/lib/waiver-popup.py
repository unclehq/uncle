#!/usr/bin/env python3
"""A popup that records why a required check cannot be performed.

Waiving a check is the most consequential thing an operator does at this gate:
it lets a run continue past a required check that was never performed. It
should look like a decision, not like another line of log output scrolling by,
which is why it gets a window of its own.

It is only ever a window. The reason still has to be typed, Esc still
declines, and nothing here turns the check into a PASS -- the report keeps
saying it was not performed.

Writes the typed reason to the file named by --out and exits 0. Exits 1 when
the operator declines, and 2 when there is no terminal to draw on, which is
the driver's signal to fall back to its plain-text prompt (a piped or
non-interactive run must still be able to decline).

The reason goes to a file rather than to stdout because stdout is the terminal
curses is drawing on.
"""

import os
import sys

EXIT_DECLINED = 1
EXIT_NO_TERMINAL = 2


def draw(stdscr, report, ids):
    import curses

    curses.curs_set(1)
    color = {"title": 0, "bad": curses.A_BOLD, "muted": curses.A_DIM,
             "warning": curses.A_BOLD, "cursor": 0}
    if curses.has_colors():
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except Exception:
                bg = curses.COLOR_BLACK
            pairs = [("title", curses.COLOR_CYAN, curses.A_BOLD),
                     ("bad", curses.COLOR_RED, curses.A_BOLD),
                     ("warning", curses.COLOR_YELLOW, 0)]
            for i, (name, fg, attr) in enumerate(pairs, start=1):
                curses.init_pair(i, fg, bg)
                color[name] = curses.color_pair(i) | attr
            curses.init_pair(len(pairs) + 1, curses.COLOR_YELLOW, bg)
            color["cursor"] = curses.color_pair(len(pairs) + 1)
        except Exception:
            pass

    body = [
        ("bad", "These required checks cannot be performed here:"),
        ("", ""),
    ]
    # The report is named on its own line: interpolated mid-sentence it would
    # set the width of the whole window from the length of a filename.
    for cid in ids:
        body.append(("warning", "    " + cid))
    body += [
        ("", ""),
        ("", "Effort will not clear them. Amending the plan or the"),
        ("", "requirement behind them is the real fix, and is what"),
        ("", "should normally happen at this gate."),
        ("", ""),
        ("", "A waiver is the other option. It records why a required"),
        ("", "check cannot be performed and lets the run reach its"),
        ("", "audit. It does not make the check pass, and the report"),
        ("", "keeps saying it was not performed:"),
        ("muted", "    " + report),
        ("", ""),
        ("muted", "Reason (Enter to record, Esc to stop and amend the plan):"),
    ]

    buf = ""
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        width = min(max(58, max(len(t) for _, t in body) + 6), max(20, w - 2))
        height = min(len(body) + 6, max(7, h - 2))
        top = max(0, (h - height) // 2)
        left = max(0, (w - width) // 2)

        try:
            win = stdscr.derwin(height, width, top, left)
        except Exception:
            return None
        win.erase()
        try:
            win.box()
        except Exception:
            pass
        title = " Waive a required check "
        try:
            win.addnstr(0, max(1, (width - len(title)) // 2), title,
                        width - 2, color["title"])
        except Exception:
            pass

        row = 1
        for attr, text in body:
            if row >= height - 3:
                break
            if text:
                try:
                    win.addnstr(row, 2, text, width - 4, color.get(attr, 0))
                except Exception:
                    pass
            row += 1

        entry = height - 2
        try:
            win.addnstr(entry, 2, "> ", width - 4, color["muted"])
            visible = buf[-(width - 7):] if len(buf) > width - 7 else buf
            win.addnstr(entry, 4, visible, width - 6)
            if len(visible) < width - 7:
                win.addstr(entry, 4 + len(visible), "█", color["cursor"])
        except Exception:
            pass
        win.refresh()

        try:
            key = stdscr.get_wch()
        except KeyboardInterrupt:
            return None
        except Exception:
            key = stdscr.getch()

        if isinstance(key, str):
            if key in ("\n", "\r"):
                return buf.strip() or None
            if key == "\x1b":                      # Esc declines
                return None
            if key in ("\x7f", "\b"):
                buf = buf[:-1]
                continue
            if key == "\x03":                      # Ctrl-C declines
                return None
            if key.isprintable():
                buf += key
            continue
        if key in (10, 13):
            return buf.strip() or None
        if key == 27:
            return None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            buf = buf[:-1]


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
    ids = [a for a in argv if a]
    if not ids or not out:
        return EXIT_DECLINED

    # A popup needs a terminal at both ends: stdout is the reason's channel, so
    # the window is drawn on the controlling terminal instead.
    if not sys.stderr.isatty():
        return EXIT_NO_TERMINAL
    try:
        import curses
    except Exception:
        return EXIT_NO_TERMINAL

    try:
        tty_in = open("/dev/tty", "rb", buffering=0)
        tty_out = open("/dev/tty", "w", encoding="utf-8", newline="\n")
    except Exception:
        return EXIT_NO_TERMINAL

    reason = None
    try:
        os.dup2(tty_in.fileno(), 0)
        os.dup2(tty_out.fileno(), 1)
        reason = curses.wrapper(draw, report, ids)
    except Exception:
        return EXIT_NO_TERMINAL
    finally:
        try:
            tty_in.close()
            tty_out.close()
        except Exception:
            pass

    if not reason:
        return EXIT_DECLINED
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(reason + "\n")
    except IOError:
        return EXIT_DECLINED
    return 0


if __name__ == "__main__":
    sys.exit(main())
