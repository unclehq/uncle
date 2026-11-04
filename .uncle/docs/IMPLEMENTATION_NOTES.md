# Implementation notes

## Step 1

### Files changed

- `scripts/lib/desktop_launch.py` — Written by isolated step 1; 1

## Step 2

### Unresolved concerns

- The plan does not give exact signatures for desktop_launch; the module tests assume detect(root) returns dict/object with framework/command/candidates, launch_decision accepts keyword args attended/unattended/headless/opted_out and returns a tuple/dict/object whose text contains the reason, DesktopLaunch(root, argv).start() returns a result with status or writes desktop-launch.json, and close(). Adjust if step 1 differs.

## Step 3

### Files changed

- `uncle_tui.py` — Written by isolated step 3; 3

## Step 4

### Files changed

- `scripts/tests/tui-desktop-launch-test.py` — Written by isolated step 4; 4

## Step 5

### Files changed

- `scripts/README.md` — Written by isolated step 5; 5
