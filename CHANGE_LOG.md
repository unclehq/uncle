# CHANGE_LOG.md — Chat History + Cursor Movement

## Part 1: Baseline Report
## Part 2: Change Specification
## Part 3: Change Plan

---

## Part 1: BASELINE REPORT

### 1. Repository

**Project:** uncle — a terminal-native agentic software engineer with a curses TUI.

**Language:** Python 3 (no `pyproject.toml`, no `setup.cfg`, no `Makefile`)

**Test runner:** `scripts/run-shell-tests.sh` — delegates to `scripts/lib/shell_suites.py` which runs `scripts/tests/*-test.sh` files (shell suites) concurrently. Python unit tests are under `scripts/tests/*-test.py` and are run by the shell suites or individually with `python3 -m unittest`.

**Where uncle is invoked:** `uncle_tui.py` defines `class UncleTUI` and runs via `curses.wrapper(main)`.

### 2. Chat Architecture

There are **two chat surfaces** sharing a single code path:

| Aspect | Home page (`state == 'menu'`) | Build page (`state == 'running'`) |
|---|---|---|
| Renderer | `_draw_homepage()` → `_draw_chat_composer()` | `_draw_running()` + `_draw_chat_panel()` → `_draw_chat_composer()` |
| Key handler | `handle_key()` → `_chat_key()` | Same `_chat_key()` |
| Buffer | `self.chat_composer` | Same `self.chat_composer` |
| Cursor | `self.chat_cursor` | Same `self.chat_cursor` |
| History | `self.chat_history` | Same `self.chat_history` |
| Send via | `send_home_chat()` which appends to `self.chat_history` | Same |

Both surfaces use the identical `_chat_key()` method at `uncle_tui.py:3837-3955` and the identical `_draw_chat_composer()` method at `uncle_tui.py:4404-4506`.

### 3. Current Input Handling (`_chat_key`, lines 3837–3955)

The method handles these keys **for the chat composer**:

| Key(s) | Action |
|---|---|
| Esc (27) | Recovery/gate focus changes |
| Ctrl-C (3) | Quit |
| Tab (9) | Toggle chat/menu focus |
| UP/DOWN | **Not handled here** — UP/DOWN at line 3863 are for `prompt_scroll` when `chat_focus == 'gate'`; otherwise unhandled (fall through to next handler) |
| F2–F8 | Various workflow commands |
| BACKSPACE (127/8) | `self.chat_composer = self.chat_composer[:-1]` — **removes from end, ignores `chat_cursor`** |
| Printable (32..0x10ffff) | `self.chat_composer = self.chat_composer[:self.chat_cursor] + char + self.chat_composer[self.chat_cursor:]` — inserts at cursor; advances `chat_cursor += 1` |
| Enter (10/13) | Sends message via `send_home_chat()` (home) or completes file picker |

**Missing key handlers:**
- `KEY_LEFT` / `KEY_RIGHT` — no cursor movement by character
- `KEY_HOME` / `KEY_END` — no jump to start/end of line
- Ctrl+Left / Ctrl+Right — no word-boundary movement
- `KEY_UP` / `KEY_DOWN` on the composer — no history navigation

### 4. Existing Infrastructure (Unused)

The following methods exist but are **never called** from any key handler:

- **`_move_cursor(delta)`** (line 3811–3815): Adjusts `self.chat_cursor` by delta, clamped to `[0, len(chat_composer)]`.
- **`_move_by_word(forward)`** (line 3817–3835): Moves `self.chat_cursor` to the next/previous word boundary.

### 5. History Storage

- **`self.chat_history`** (list of str, initialized at line 2468): Appended in `send_home_chat()` at line 2706 with `self.chat_history.append(sanitize(message))`.
- **`self.chat_history_index`** (int, initialized at line 2469 to `-1`): Reset to `-1` every time a message is sent. **Never read** in any key handler.
- History eviction: `_evict_chat_history()` (line 3805) drops oldest entries when total exceeds 1 MiB.
- No draft preservation: when the user navigates away from the current draft to browse history, the current draft is discarded (no `chat_saved_draft` mechanism is wired).

### 6. Cursor Rendering

`_draw_chat_composer()` at lines 4441–4465:
- Renders `sanitize(self.chat_composer)` into wrapped chunks
- **Cursor position is calculated as `left + 2 + len(chunks[-1])`** — i.e., always at the **end** of the text, not at `self.chat_cursor`
- The `self.chat_cursor` value is only used for insert position (line 3945) but **not reflected in the visual cursor**

### 7. Relevant Files

| File | Role |
|---|---|
| `uncle_tui.py` | **Primary target** — all TUI input handling and rendering |
| `scripts/lib/chat.py` | `Conversation` class (chat state, references, seeding) |
| `scripts/lib/home_chat.py` | `HomeRequest` — background chat request management |
| `scripts/lib/home_actions.py` | Home page action parsing (create_app, create_change, etc.) |
| `scripts/tests/home-chat-test.py` | Unit tests for home chat UI |
| `scripts/tests/chat-test.py` | Unit tests for chat/Conversation |
| `scripts/run-shell-tests.sh` | Test runner |

### 8. Key Line References (all in `uncle_tui.py`)

| Line(s) | What |
|---|---|
| 709 | `self.input_buf = ""` — separate buffer used for prompt/issue input, NOT chat |
| 2468–2469 | `chat_history` init as `[]`, `chat_history_index` init as `-1` |
| 2471 | `chat_cursor` init as `0` |
| 2706–2708 | `chat_history.append`, `chat_cursor = 0`, `chat_history_index = -1` on send |
| 3805–3809 | `_evict_chat_history()` — byte-limit eviction |
| 3811–3815 | `_move_cursor(delta)` — exists, unused |
| 3817–3835 | `_move_by_word(forward)` — exists, unused |
| 3837–3955 | `_chat_key(k)` — main chat input handler |
| 3939–3946 | BACKSPACE and printable char handling in `_chat_key` |
| 4386–4402 | `_wrap_input()` — word-wrap for composer rendering |
| 4404–4506 | `_draw_chat_composer()` — renders input, cursor always at end |
| 4457–4465 | Cursor rendering — always at `len(chunks[-1])` |
| 4507–4512 | `_draw_chat_panel()` — build page composer wrapper |
| 5186–5229 | `handle_key()` — main event dispatch |

---

## Part 2: CHANGE SPECIFICATION

### Feature: Chat Window History + Shell Movement Commands

**Objective:** Add keyboard-driven history recall (UP/DOWN) and standard shell cursor movement (LEFT/RIGHT, HOME/END, word-boundary navigation) to both the home page and build page chat composer in uncle's TUI.

### Key Bindings

| Key | Action | Notes |
|---|---|---|
| `KEY_UP` / `Ctrl-P` | Recall previous history entry | Save current draft first; cycle through `chat_history` |
| `KEY_DOWN` / `Ctrl-N` | Recall next history entry (or restore draft) | At bottom of history, restore saved draft |
| `KEY_LEFT` | Move cursor left by one character | Clamped to 0 |
| `KEY_RIGHT` | Move cursor right by one character | Clamped to `len(composer)` |
| `KEY_HOME` / `Ctrl-A` | Move cursor to beginning of line | |
| `KEY_END` / `Ctrl-E` | Move cursor to end of line | |
| `Ctrl-Left` / `Alt-b` | Move cursor back one word | Reuse `_move_by_word(forward=False)` |
| `Ctrl-Right` / `Alt-f` | Move cursor forward one word | Reuse `_move_by_word(forward=True)` |

### Behavioural Requirements

1. **History navigation** (UP/DOWN):
   - First UP press: save `chat_composer` to `chat_saved_draft`, load `chat_history[-1]`
   - Subsequent UP: walk backward through `chat_history`
   - DOWN: walk forward; at end of history, restore `chat_saved_draft`
   - `chat_cursor` goes to end of loaded text
   - History is shared between home and build page

2. **BACKSPACE fix**: Currently backspace removes from end regardless of cursor. Change to `chat_composer = chat_composer[:chat_cursor-1] + chat_composer[chat_cursor:]` with `chat_cursor -= 1`.

3. **Cursor rendering**: The visual cursor in `_draw_chat_composer()` must track `chat_cursor` position, not the end of the text. This requires computing which wrapped line and column corresponds to `chat_cursor`.

4. **No conflicts**: UP/DOWN must not interfere with existing `prompt_scroll` (lines 3863–3866) when `chat_focus == 'gate'`, or with `slash_pick` (lines 4130–4131) when slash completions are active.

5. **Both surfaces**: All changes apply uniformly to both home page (`state == 'menu'`) and build page (`state == 'running'`) chat.

### Non-goals

- No multi-line editing or undo
- No search-through-history (e.g., `Ctrl-R`)
- No history persistence across sessions
- No changes to the `Conversation` class or supervisor chat logic

---

## Part 3: CHANGE PLAN

### Phase 1: History Navigation (~1 hour)

**Step 1.1 — Save draft before browsing (line 3939 area)**
In `_chat_key()`, when UP is pressed, save current `chat_composer` to `chat_saved_draft` if not already in history-browsing mode.

**Step 1.2 — Wire UP/DOWN in `_chat_key()` (before line 3939)**
Insert key handling for `curses.KEY_UP` and `curses.KEY_DOWN` in the main `_chat_key()` method, before the BACKSPACE check:
- Ensure we are not in `chat_focus == 'gate'` mode (UP/DOWN already handled there for `prompt_scroll`)
- Ensure we are not in slash-completion mode (UP/DOWN already handled at line 4130)
- Set `chat_history_index` to valid range
- Load `chat_history[chat_history_index]` into `chat_composer`
- Set `chat_cursor` to end of loaded text

**Step 1.3 — Reset history index on edit**
When the user presses any printable key or BACKSPACE while browsing history (`chat_history_index != -1`), switch back to "editing" mode.

### Phase 2: Cursor Movement (~1 hour)

**Step 2.1 — Wire LEFT/RIGHT**
In `_chat_key()`, add `curses.KEY_LEFT` and `curses.KEY_RIGHT` handlers that call `_move_cursor(-1)` and `_move_cursor(1)` respectively.

**Step 2.2 — Wire HOME/END**
Add `curses.KEY_HOME` → `self.chat_cursor = 0` and `curses.KEY_END` → `self.chat_cursor = len(self.chat_composer)`.

**Step 2.3 — Wire Ctrl-Left / Ctrl-Right**
Detect `curses.KEY_SLEFT` (or escape sequences `\x1b[1;5D` / `\x1b[1;5C` depending on terminal) and call `_move_by_word(forward=False)` / `_move_by_word(forward=True)`.

**Step 2.4 — Fix BACKSPACE to use cursor**
Change line 3939 from:
```python
self.chat_composer = self.chat_composer[:-1]
```
to:
```python
if self.chat_cursor > 0:
    self.chat_composer = self.chat_composer[:self.chat_cursor-1] + self.chat_composer[self.chat_cursor:]
    self.chat_cursor -= 1
```

### Phase 3: Cursor Rendering (~1.5 hours)

**Step 3.1 — Compute cursor position**
In `_draw_chat_composer()`, replace the current cursor-at-end calculation (line 4459) with logic that:
1. Wraps `self.chat_composer` up to `self.chat_cursor` position
2. Finds which wrapped line and column `self.chat_cursor` falls on
3. Sets `cursor_y` and `cursor_x` accordingly

**Step 3.2 — Handle word-wrap boundary**
If `chat_cursor` falls on a word-wrapped position, add a new partial line for the cursor to sit on.

**Step 3.3 — Test edge cases**
- Empty input
- Cursor at position 0 (left edge)
- Cursor at end (right edge)
- Cursor on a word-wrap boundary
- Very long input that wraps multiple lines

### Phase 4: Testing (~1 hour)

**Step 4.1 — Unit tests for `_move_cursor` and `_move_by_word`**
Add tests in `scripts/tests/home-chat-test.py` (or a new `scripts/tests/chat-history-test.py`):
- `test_move_cursor_clamps_to_bounds`
- `test_move_by_word_forward`
- `test_move_by_word_backward`

**Step 4.2 — Unit tests for `_chat_key` history handling**
Mock the TUI and verify:
- UP loads `chat_history[-1]` into `chat_composer`
- DOWN restores draft
- Multiple UP/DOWN cycles work correctly

**Step 4.3 — Manual verification checklist**
- History works on both home and build page
- LEFT/RIGHT move cursor visually and logically
- HOME/END jump correctly
- Ctrl-LEFT/RIGHT skip words
- BACKSPACE deletes at cursor, not end
- No regression: menu focus, gate focus, slash completions, file/issue pickers still work

### Risk Register

| Risk | Mitigation |
|---|---|
| `curses.KEY_UP` consumed by `prompt_scroll` handler before reaching new code | Order matters: check `chat_focus == 'gate'` first, then fall through to history only when in composer focus |
| `curses.KEY_DOWN` conflicts with slash completion picker | `_chat_command` at line 4128–4132 already handles UP/DOWN for slash choices; new code must check `chat_choices` is empty first |
| Ctrl-Left/R Ctrl-Right escape sequences differ by terminal | Use `curses.KEY_SLEFT` / `curses.KEY_SRIGHT` where available; fall back to raw escape sequence parsing in `handle_key` or document terminal requirements |
| Cursor rendering breaks on narrow terminals | `_wrap_input` already handles narrow widths; cursor position calculation must use the same wrapping logic to stay consistent |
| History eviction loses messages during browse | `_evict_chat_history` only runs on send (line 2710); browsing does not trigger it |
