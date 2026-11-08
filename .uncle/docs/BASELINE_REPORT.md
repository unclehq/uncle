# Baseline Report

Omitted sections: Reproduction result (not a bug report); Existing failures (none documented; driver baseline is authority)

## 1. Change-request summary
Issue 190 (CHANGE_REQUEST.md): home composer Enter submits; Ctrl+Enter inserts newline; multi-line paste inserted at cursor without submitting; copy via system shortcut.

## 2. Repository architecture
Single-file curses TUI `uncle_tui.py` (~9150 lines); helpers in `scripts/lib/` (e.g. `home_actions.py`); tests in `scripts/tests/*-test.py` (Python) and shell suites run by `scripts/run-shell-tests.sh`. Composer state: `chat_composer` + `chat_cursor` (uncle_tui.py:1126-1140). Pure edit helpers `edit_insert/backspace/delete/...` at uncle_tui.py:892-960, `COMPOSER_LIMIT` 1 MiB (895).

## 3. Relevant code paths
- Main loop `stdscr.getch()` -> `handle_key`: uncle_tui.py:9041-9046. `keypad(True)` at 8991; input timeout 80 ms at 8998.
- `handle_key` Esc handling for composer: 8472-8478 calls `_read_meta_key` (6247-6272), which reads one follow-up key with `timeout(0)`, handles Meta b/f/d/backspace, else `ungetch`s it and sets `esc_follow`.
- `_homepage_key` (6938): Enter resets `home_scroll`; menu handling.
- `_chat_key` (6348): Enter block 6425-6465 (k in 10,13); printable insert 6512-6513 (`32 <= k`, one char per key); `_chat_command` (6980) also keys on 10/13 for slash commands.
- `send_home_chat` (submits to home supervisor); `_remember_input`.
- Mouse capture: `_set_mouse` 8283-8289, default ON via UNCLE_MOUSE (8996); comment at 8992-8994 says capture blocks native text selection; Ctrl-G toggles.
- Terminal teardown writes `\x1b[?1002l` at ~9102.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Enter (curses delivers 10 under default nl mode; 13 possible) with text | `send_home_chat(text)` then composer cleared | uncle_tui.py:6460-6464; home-actions-test.py:406 calls `_chat_key(10)` | Yes |
| B-2 | Enter when line ends in single `\` | backslash replaced by newline, no submit | uncle_tui.py:6458-6459 | Yes |
| B-3 | Enter when line ends in `\\` | sends one trailing backslash | 6453-6457 | Yes |
| B-4 | Enter in `chat_edit` mode (F4) | inserts newline at cursor | 6450-6452 | Yes |
| B-5 | Enter with slash menu/issue picker open | accepts picker/menu entry; `/cmd` runs command | 6433-6449, 6985-6991 | Yes |
| B-6 | Terminal paste containing newlines | each newline arrives as key 10/13 and submits (prefix lines sent separately); text chars inserted one key at a time | 6425, 6512 | No (defect to fix) |
| B-7 | Ctrl+Enter | indistinguishable from Enter in plain terminals; submits | no handler | No |
| B-8 | Esc followed by other key | key pushed back, `esc_follow=True` | 6265-6269 | Yes |
| B-9 | Native copy (Cmd/Ctrl+C... via terminal selection) | works only when mouse capture is off (Ctrl-G) or via terminal's mouse-bypass modifier; key 3 (Ctrl-C) quits | 6371-6373, 8992-8996 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Composer text never exceeds COMPOSER_LIMIT | `edit_insert(limit=...)` 898 | UNRESOLVED (not located) | Medium |
| I-2 | Cursor always within 0..len(text) | `_composer_cursor` 1137-1138 | none located | Medium |
| I-3 | Enter with queued picker/slash state does not lose intent (B-5) | 6433-6449 | home-actions-test.py:396 | High |
| I-4 | Input timeout restored on every `_read_meta_key` path | try/finally 6271 | none located | High |

## 6. Interface contracts
No external API/schema. Internal: `_chat_key(k:int)->bool`, `handle_key(k)`, `edit_insert(text,cursor,value,limit)->(text,cursor,...)`. Terminal contract: bytes via curses getch.

## 7. Existing automated-test coverage
`scripts/tests/home-actions-test.py` drives `_chat_key(10)` against a stub UI (line ~406). No tests located for `_read_meta_key`, paste, or `edit_insert` directly. Shell suites and Python suites use separate temp dirs and no shared ports (per runner guidance), so they form one parallel group.

## 9. Baseline test results
Commands derived from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (both exist). Nothing executed in this stage; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 10. Existing failures
None known from repository docs; see driver baseline.

## 12. Likely change surface
`uncle_tui.py` (handle_key ~8472, `_read_meta_key` 6247, `_chat_key` 6425-6465 area, `_run_loop` startup 8984-9004 and teardown ~9102, new pure helpers near 898); new `scripts/tests/home-composer-keys-test.py`; optional docs line in README/QUICK_START.

## 13. Regression-sensitive components
Enter handling (slash commands, pickers, backslash continuation, edit mode), Esc semantics (interrupt/rewind, Meta keys), mouse capture/teardown, terminal state restoration on exit, inline mode raw `_tty_write`.

## 14. Outside the change
Build-page/triage composers (`triage_composer`, 5817-5901) unless sharing the same `_chat_key`; mouse-capture defaults; supervisor logic; `scripts/lib/home_actions.py`.

## 15. Unknowns and assumptions
- Plain terminals (e.g. macOS Terminal.app) cannot send a distinct Ctrl+Enter; only terminals supporting CSI-u / modifyOtherKeys (kitty, WezTerm, iTerm2, Ghostty, xterm) can. Assumed acceptable with fallbacks (backslash-Enter retained, Esc+Enter).
- Copy of composer text relies on terminal selection (mouse capture default ON blocks plain drag-select); assumed no code change needed for copy.

## 16. Initial risk assessment
Medium: key parsing changes touch every composer keystroke path; mitigated by confining new logic to escape-sequence and pending-input branches and by pure parser functions with unit tests.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

