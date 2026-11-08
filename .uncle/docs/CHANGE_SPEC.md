# Change Spec

Omitted sections: Migration (none); Prototype isolation (not a prototype); Performance (negligible); Security (see 10, brief)

## 1. Change type
Feature + bug fix (multi-line paste currently submits per line).

## 2. Problem statement
Home composer cannot take multi-line pasted text (each newline submits) and offers no first-class newline key; Issue 190.

## 3. Current behavior
See baseline B-1..B-9.

## 4. Desired behavior
Enter submits; Ctrl+Enter inserts newline at cursor; pasted text (single or multi-line) is inserted at the cursor verbatim (newlines normalized to LF) without submitting; copy works with the system shortcut.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | PRESERVE | Enter with non-empty text, no picker/menu, not edit mode | submits, clears composer (B-1) | unchanged | unit test AC-1 |
| SB-2 | ADD | Ctrl+Enter reported by terminal as CSI-u `ESC[13;5u` or modifyOtherKeys `ESC[27;5;13~` | submits (or nothing) | newline inserted at cursor, no submit, cursor advances | unit test AC-2 + manual |
| SB-3 | ADD | Esc immediately followed by Enter (Alt+Enter / terminals mapping Ctrl+Enter to ESC CR) | Esc handled, Enter submits | newline inserted at cursor, no submit | unit test AC-2 |
| SB-4 | MODIFY | Bracketed paste `ESC[200~ ... ESC[201~` | each newline submits (B-6) | whole payload inserted at cursor; CR/CRLF normalized to LF; no submit; honors COMPOSER_LIMIT; control chars other than LF/TAB dropped | unit test AC-3 |
| SB-5 | MODIFY | Terminal without bracketed paste: Enter key arrives while further input already queued | submits per line | treated as newline (paste burst); a lone Enter still submits | unit test AC-3 |
| SB-6 | ADD | UI start / exit | no paste or enhanced-key modes | bracketed paste and enhanced-key reporting enabled at start and always disabled at exit/crash teardown | unit test + manual |
| SB-7 | PRESERVE | Backslash-Enter continuation, `\\` escape, edit-mode Enter, picker/slash Enter, Esc+other key, Meta b/f/d | per B-2..B-5, B-8 | unchanged | existing + new tests AC-4 |
| SB-8 | PRESERVE | Copy selected composer text with system shortcut | works via terminal selection (mouse capture off or terminal bypass modifier) | unchanged; Ctrl-C still quits | manual AC-5 |
| SB-9 | PRESERVE | Enter with empty composer | no message sent | unchanged | unit test AC-1 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | No newline contained in pasted or Ctrl+Enter input ever triggers `send_home_chat` | composer | paste/newline branches never call submit | unit test |
| SI-2 | EXISTING | Composer length <= COMPOSER_LIMIT; cursor within text | composer | `edit_insert` limit | unit test with oversize paste |
| SI-3 | NEW | Terminal mode enabled at start is disabled on every exit path | TUI lifecycle | teardown | unit test + manual |
| SI-4 | EXISTING | `_read_meta_key` restores input timeout on all paths and never blocks indefinitely on a truncated sequence | key reader | try/finally + bounded wait | unit test |
| SI-5 | EXISTING | Plain Enter semantics B-1..B-5 unchanged | composer | `_chat_key` | existing test + new |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Backslash-Enter continuation retained as fallback for terminals that cannot signal Ctrl+Enter. Existing `_chat_key(10)` must still submit.

## 8. Error behavior
Unterminated bracketed paste (no `ESC[201~` within bounded wait): insert what was received, resume normal input; never hang. Unknown CSI sequences after Esc are pushed back as today.

## 10. Security
Pasted bytes are sanitized (drop ESC and other C0 controls except LF/TAB) so a paste cannot inject terminal escape sequences or fake paste-end markers into the composer.

## 12. Rollback
Revert the commit; no persistence or schema.

## 14. Non-goals
Changing mouse-capture defaults; build-page triage composer; custom key-binding config; clipboard integration (OSC 52/pbcopy); making Ctrl+Enter work on terminals that cannot report it.

## 15. Assumptions
Terminals lacking enhanced-key reporting use backslash-Enter or Esc+Enter. Copy needs no code change (terminal-native selection).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Enter with non-empty text (no picker/menu/edit mode) sends it via send_home_chat and clears the composer; Enter with empty composer sends nothing. | Python unit test driving handle_key/_chat_key with stub UI (existing home-actions-test.py:396 still passes plus new case). |
| AC-2 | Ctrl+Enter (CSI-u `ESC[13;5u`, modifyOtherKeys `ESC[27;5;13~`) and Esc+Enter insert a newline at the cursor, advance the cursor, and do not submit or clear the composer. | Python unit test feeding byte sequences through the key reader with a fake screen; plus manual check in a CSI-u capable terminal. |
| AC-3 | Pasting single- or multi-line text (bracketed paste, or Enter-with-queued-input burst) inserts it at the cursor with CR/CRLF normalized to LF, never submits, respects COMPOSER_LIMIT, and drops escape/control characters other than LF and TAB; an unterminated paste does not hang. | Python unit tests of pure paste parser and key reader; manual paste in real terminal. |
| AC-4 | Existing composer behaviors are unchanged: backslash-Enter continuation, `\\` escape, edit-mode Enter, picker/slash Enter, Esc+non-Enter key pushback, Meta b/f/d, Ctrl-C quit. | bash scripts/run-python-tests.sh including home-actions-test.py and new home-composer-keys-test.py. |
| AC-5 | Copying selected composer text works with the standard system shortcut in the terminal (unchanged mechanism), and terminal paste/enhanced-key modes are disabled on exit. | Manual checklist: select composer text (mouse capture off via Ctrl-G or terminal bypass modifier), copy, paste elsewhere; after quitting, run `cat` and confirm pasted text has no ESC[200~ markers; unit test that teardown emits disable sequences. |

