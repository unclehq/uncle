# Manual checklist

### MC-100
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal tab, cd into two different project directories (one named like grove-issue-33) and launch `uncle` in each tab; look at both tab titles while the TUI is idle.
- Expected result: Each tab title reads `<dir basename> · uncle` (e.g. `grove-issue-33 · uncle`), the two tabs are distinguishable, and the title matches the project name in the TUI status bar.
- Actual result: 
- Status: NOT RUN

### MC-101
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI from MC-100's tab, start a run with an issue number (e.g. #152), watch the tab title during the run, then let the run finish and watch again.
- Expected result: During the run the title reads `<project> · uncle issue #152`; after the run ends it returns to `<project> · uncle`, never bare `uncle`.
- Actual result: 
- Status: NOT RUN

### MC-102
- Exclusive resources: none
- Depends on: none
- Exact action: Set the tab title to a recognizable value (e.g. `printf '\033]2;MYSHELL\007'`), launch `uncle`, quit it normally, and observe the tab title.
- Expected result: After quitting, the tab title is restored to `MYSHELL` on a terminal supporting the xterm title stack (otherwise it stays `<project> · uncle`), and is never bare `uncle`.
- Actual result: 
- Status: NOT RUN

### MC-103
- Exclusive resources: none
- Depends on: none
- Exact action: Run `UNCLE_TERMINAL_TITLE=0 uncle` in a tab with a known title, then separately run `uncle | cat` and `TERM=dumb uncle`; observe the tab title each time.
- Expected result: In all three cases the tab title is never changed by uncle and no stray escape characters appear on screen.
- Actual result: 
- Status: NOT RUN

### MC-104
- Exclusive resources: none
- Depends on: none
- Exact action: In a tab, launch the `uncle` line-based menu (non-curses fallback), then start a driver (stagegate.sh, change-workflow.sh or from-issue.sh) from it with and without an issue number, and exit; watch the tab title throughout.
- Expected result: Title shows `<project> · uncle` (with ` issue #N` when an issue is given) once, is not mangled by child drivers, and is restored on exit including after Ctrl-C cancel.
- Actual result: 
- Status: NOT RUN

### MC-105
- Exclusive resources: none
- Depends on: none
- Exact action: Run each of `scripts/stagegate.sh`, `scripts/change-workflow.sh` and `scripts/from-issue.sh` directly from a terminal tab (not under the TUI), then abort each with Ctrl-C; observe the tab title during and after.
- Expected result: Each driver sets `<project> · uncle` (plus issue suffix where applicable) while running and restores the prior title on exit/cancel, with no garbage characters printed.
- Actual result: 
- Status: NOT RUN

### MC-106
- Exclusive resources: none
- Depends on: none
- Exact action: Create a directory whose name contains an embedded escape or BEL byte and a very long (100+ char) name via `mkdir $'/tmp/x/evil\033]0;PWNED\007name'` and a long-named dir; launch `uncle` in each and view the tab title.
- Expected result: No injected title or control effect occurs; control characters are absent from the title, the long project name is cut to 60 characters with ` · uncle` suffix intact.
- Actual result: 
- Status: NOT RUN

### MC-202
- Exclusive resources: none
- Depends on: none
- Exact action: Launch uncle with `UNCLE_TERMINAL_TITLE=0` in a titled tab, and separately run `uncle | cat`; watch the tab title and capture the raw output with `| od -c` for the piped case.
- Expected result: Tab title is unchanged and the piped output has no ESC]2 or CSI 22/23 t sequences.
- Actual result: 
- Status: NOT RUN

### MC-205
- Exclusive resources: none
- Depends on: none
- Exact action: Start a driver from inside the uncle TUI (a run) and from the uncle line-based menu, and watch the tab title for double-set or premature restore.
- Expected result: Only the owner (TUI or line menu) changes the title. The driver sets nothing and does not restore early, and the title is restored once on final exit.
- Actual result: 
- Status: NOT RUN

### MC-301
- Exclusive resources: browser:system
- Exact action: In a real terminal tab with a known custom title, start `uncle`, run a numbered issue, let it end, then quit the TUI; observe the title at each step.
- Expected result: Title goes `<project> · uncle`, then `<project> · uncle issue #N` during the run, back to `<project> · uncle` at run end, and the previous custom title is restored on exit; bare `uncle` never appears.
- Actual result: 
- Status: NOT RUN

### MC-302
- Exclusive resources: browser:system
- Exact action: Launch `UNCLE_TERMINAL_TITLE=0 uncle` in a tab, then run `uncle | cat` in another; watch the tab titles.
- Expected result: Neither tab title changes from its previous value and no stray escape text is printed.
- Actual result: 
- Status: NOT RUN

### MC-303
- Exclusive resources: browser:system
- Exact action: In a real terminal tab, run the `uncle` line-based menu and start a driver (stagegate.sh or change-workflow.sh) without an issue number; then exit it.
- Expected result: Title shows `<project> · uncle` during the run, with no nested push, and the prior title is restored on exit.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a real terminal tab, run `uncle` with no arguments (TUI), observe the tab title, then quit the TUI and observe the tab title again.
- Expected result: Tab title shows `<project> · uncle` while idle, and after quit the previous tab title is restored (or remains project-only if the terminal lacks a title stack); the bare literal `uncle` is never shown.
- Evidence to capture: Screenshots or notes of tab title before launch, during idle TUI, and after exit.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In the TUI, start an issue-backed run (with an issue number) and then a run without an issue number, watching the tab title at start and at end of each run.
- Expected result: Issue run shows `<project> · uncle issue #N`; no-issue run shows `<project> · uncle`; at run end the title returns to `<project> · uncle` without popping the saved title; status bar still shows `<dir> (<branch>)` unchanged.
- Evidence to capture: Tab title observations at each transition plus a status bar screenshot.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Run `UNCLE_TERMINAL_TITLE=0 uncle`, then separately `uncle | cat`, and observe the tab title and any stray escape characters in output.
- Expected result: Tab title is not changed in either case, and no escape sequence garbage appears in the piped output.
- Evidence to capture: Tab title observations and the piped output captured via `uncle | cat | cat -v`.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: From a TUI-launched run, observe the tab title while a driver (stagegate/change-workflow/from-issue) executes, then launch the same driver directly from the shell with `./scripts/stagegate.sh` and again with the line-based menu path of `uncle`.
- Expected result: Under the TUI the driver does not alter the title or push extra; run directly or from the line menu, the title is `<project> · uncle` (with ` issue #N` when applicable) and is restored on exit, including after Ctrl-C cancel.
- Evidence to capture: Tab title notes at start, during, and after exit for each launch path, including after cancel.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a directory whose name contains an escape/control character or exceeds 60 characters (create via `mkdir $'/tmp/x/a\e]2;PWNED\a'` and a 100-char directory), launch `uncle` in each and observe the tab title.
- Expected result: No injected title text appears; control characters are removed; long names are truncated to 60 characters with ` · uncle` suffix intact.
- Evidence to capture: Screenshots of tab titles for both directories.
- Actual result: 
- Status: NOT RUN
