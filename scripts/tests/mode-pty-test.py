#!/usr/bin/env python3
"""TUI passes --attended only when attended; nothing otherwise (AC-3)."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = open(os.path.join(ROOT, "uncle_tui.py"), encoding="utf-8").read()

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)
        print("FAIL:", name)
    else:
        print("ok:", name)


m = re.search(r"def cmd_for\(self\):\n(.*?)\n        if self\.workflow_idx == 1", SRC, re.S)
check("cmd_for found", m is not None)
body = m.group(1) if m else ""
check("cmd_for passes --attended", '"--attended"' in body)
check("cmd_for no longer appends --unattended", "--unattended" not in body)
check("attended is the non-unattended branch",
      re.search(r'auto = \[\] if self\._next_run_unattended\(\) else \["--attended"\]', body) is not None)
check("startup honors UNCLE_STARTUP_ATTENDED", 'UNCLE_STARTUP_ATTENDED' in SRC)
check("workflow_unattended keyed on --attended absence",
      'self.workflow_unattended = "--attended" not in command' in SRC)

sys.exit(1 if failures else 0)
