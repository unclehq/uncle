# Change Plan

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (single-threaded input loop); Feature flag (none, see containment)

Issue 190

Seeded from [unclehq/uncle#190](https://github.com/unclehq/uncle/issues/190).

## 1. Selected technical approach

Burst-detection contract (AR-018): in `handle_key`, when composing and k in (10,13) with no preceding Esc, call a single nodelay `getch()` peek. If it returns a key (not -1), that key is pushed back with `ungetch` (order preserved) and Enter is inserted as a newline via `_composer_newline()` and never submits. If it returns -1 (nothing queued), Enter submits exactly as before. There is no time window and no sleep: the decision depends only on what the nodelay getch returns at that instant. Test contract: a fake screen exposes `getch()` returning a scripted queue (then -1) and records `ungetch` calls; tests assert newline vs submit and that the peeked key is pushed back.

Add pure, unit-testable helpers in `uncle_tui.py` near `edit_insert` (line ~898): `sanitize_paste(text)->str` (CRLF/CR->LF, drop ESC/C0 except LF/TAB) and `classify_escape(bytes)->('paste'|'newline'|None)`. Extend `_read_meta_key` (6247) to (a) on `[` read a CSI sequence with bounded short timeout; `200~` starts paste, read until `ESC[201~` or timeout/limit, then insert via `edit_insert` (limit COMPOSER_LIMIT); `13;5u` / `27;5;13~` -> newline; because modifyOtherKeys level 2 reports modified keys as CSI sequences, `27;5;99~`/`99;5u` (Ctrl-C) and Meta b/f/d modified forms are mapped back to their legacy keycodes (see D-2); other unknown CSI pushed back; (b) Esc followed by 10/13 -> newline. Add `_composer_newline()` that inserts LF at cursor (same logic as existing 6451-6452). In `handle_key` (before `_chat_key` dispatch, ~8479) add burst detection: when composing and k in (10,13), peek with up to two nodelay getch calls and push back every key read (ungetch, reverse order); Enter is treated as a newline only if at least 2 further keys were already pending; with 0 or 1 pending keys Enter submits unchanged. Enter-byte rule (binding): plain Enter may arrive as byte 10 or 13 (ICRNL), so burst detection and Esc+Enter apply identically to both 10 and 13; a lone 10 or 13 with no pending input and no preceding Esc always submits (so `_chat_key(10)` still submits, per the protected test); a lone Esc followed by 10/13 is a newline only when the plain composer has focus. In `_run_loop` start (after 8991) write exactly `ESC[?2004h` (bracketed paste) then `ESC[>4;2m` (xterm modifyOtherKeys level 2); the kitty keyboard protocol is NOT enabled (no `ESC[>Nu` push). In teardown (~9102) write exactly `ESC[?2004l` then `ESC[>4;0m`; no `ESC[<u` pop is emitted since nothing was pushed. `_chat_key` Enter block is left untouched, so key 10 still submits (existing test).

Modifier rule (AR-006): in CSI-u (`ESC[13;<mod>u`) and modifyOtherKeys (`ESC[27;<mod>;13~`) forms, only Ctrl (mod 5) Enter is a newline. Enter with any other modifier (e.g. Shift `13;2u`, Alt `13;3u`) is treated as plain Enter (submit, same path as key 13). All other unknown CSI sequences are pushed back unchanged via ungetch (reverse order). Pasted TAB is retained (sanitize_paste keeps LF/TAB).

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| Disable ICRNL/`curses.nonl()` so Ctrl+J (10) differs from Enter (13) | Rejected: `_chat_key(10)` is Enter in protected test home-actions-test.py:406; nonl alters ONLCR affecting inline-mode raw writes |
| Treat key 10 as Ctrl+Enter | Rejected: same conflict |
| Replace curses input with a new key library | Rejected: disproportionate |
| Clipboard integration for copy | Rejected: non-goal |

## 3. Why preferred

Confined to escape-sequence and pending-input branches; plain Enter path byte-for-byte unchanged. An Enter with fewer than 2 further keys already pending always takes the existing submit path.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Ctrl+Enter recognized only via enhanced-key sequences and Esc+Enter; backslash-Enter stays as fallback | Plain terminals cannot distinguish; test constraint |
| D-2 | Startup emits exactly `ESC[?2004h` (bracketed paste) and `ESC[>4;2m` (xterm modifyOtherKeys level 2), in that order. The kitty keyboard protocol is NOT enabled: no kitty sequence (`ESC[>1u`, `ESC[>5u`, `ESC[<u`) is ever written. Teardown emits exactly `ESC[?2004l` and `ESC[>4;0m`; disable strings are written iff the enable strings were written. Because level 2 re-encodes modified keys, the CSI reader defensively maps `27;mod;code~` and CSI-u forms of Ctrl-C (mod 5, code 99 -> 3) and Meta b/f/d (mod 3, codes 98/102/100 -> ESC+char path) to their legacy keycodes (preserving AC-4); only Enter with Ctrl is a newline, and all other unknown CSI is pushed back unchanged. Unit tests assert the exact emitted strings and the mappings; live behavior is verified manually. | Plain Enter must remain CR/LF; kitty flags could change plain Enter reporting and an unpaired pop is unsafe. modifyOtherKeys level 2 yields Ctrl+Enter as `ESC[27;5;13~`, and the defensive mapping keeps Ctrl-C and Meta b/f/d working. Gives tests an exact byte oracle. |
| D-3 | Burst detection (Enter keys 10 or 13) is limited to the plain composing state (composer focused; no picker, slash menu or edit mode). It applies only when bracketed paste is not active (inside an active paste the paste reader handles all bytes) and only ever inserts a newline, never submits. Bracketed paste, Ctrl+Enter (CSI-u/modifyOtherKeys) and Esc+Enter newline behavior are honored only when the plain composer has focus. Outside plain composing state (picker, slash menu, edit mode), bracketed paste and Ctrl+Enter/modifyOtherKeys sequences are fully consumed and discarded: they never insert text, never insert a newline, never submit, and never reach picker or edit-mode Enter handlers. Paste payload is read to its end marker and dropped. Esc followed by Enter outside plain composing keeps the old Esc-then-Enter behavior, so picker/edit-mode Enter behavior (AC-4) stays unchanged. | Fallback for terminals without bracketed paste; must not double-handle bytes of an active paste; swallowing outside plain composing prevents a paste or Ctrl+Enter from triggering picker/edit actions or submitting via Enter handlers. |
| D-6 | Bracketed paste, Ctrl+Enter (CSI-u/modifyOtherKeys) and Esc+Enter are honored only when the plain composer has focus. Outside it (picker, slash menu, edit mode) the sequence is fully consumed and discarded: no insert, no submit, and never delivered to picker or edit-mode Enter handlers; Esc followed by Enter outside plain composing keeps the legacy Esc-then-Enter behavior. | Resolves AR-010: avoids undefined paste/newline behavior in non-composing states and preserves AC-4 |
| D-4 | Paste sanitization (`sanitize_paste`) normalizes CRLF/CR to LF and drops ESC, C0 controls except LF/TAB, DEL (U+007F), C1 controls (U+0080-U+009F, including 8-bit CSI U+009B), and Unicode bidi controls U+202A-U+202E and U+2066-U+2069 | Security: no escape injection, 8-bit control-sequence injection, or bidi spoofing via pasted text |
| D-5 | No change to mouse-capture default | Out of scope; copy via terminal selection |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | REPOSITORY | home-actions-test.py:406 | AC-1, AC-4 | `_chat_key(10)` and `_chat_key(13)` submit; a lone 10/13 with no pending input and no preceding Esc always submits; burst detection and Esc+Enter treat 10 and 13 identically | Leave Enter block 6425-6465 unchanged | Protected test | CAP-PY-UNIT | CODING |
| R-2 | USER | CHANGE_REQUEST AC | AC-3 | Paste never submits | Bracketed paste + burst detection; after an unterminated paste timeout, paste-tail mode treats Enter as newline until 150 ms of input idleness | Both terminal classes | CAP-PY-UNIT | CODING |
| R-3 | DESIGN | SI-3 | AC-5 | Modes disabled iff enabled at start, on every exit path (normal, exception, SIGTERM, SIGHUP), and suspended/resumed correctly (SIGTSTP/SIGCONT) | Disable strings are written iff the enable strings were actually written (a single `_enhanced_keys_enabled` flag set at enable time; idempotent, at most once). Both enable and disable go through an injectable writer callable (default: tty stdout write). Enable is skipped when stdout is not a tty or `UNCLE_ENHANCED_KEYS=0`, so neither is then emitted. Disable is emitted from the `_run_loop` finally block, an atexit hook, and SIGTERM/SIGHUP handlers; on SIGTSTP the disable strings are written before suspend and the enable strings re-emitted on SIGCONT resume. | Avoid corrupt shell | CAP-PY-UNIT | CODING |
| R-4 | PLATFORM | curses/terminal | AC-2 | Ctrl+Enter only on capable terminals; non-Ctrl-modified Enter submits as plain Enter; unknown CSI pushed back unchanged | CSI-u/modifyOtherKeys parse: only modifier 5 with Enter code 13 yields newline; other modifiers map to plain Enter; unknown CSI pushed back | Terminal limit | CAP-LIVE-TERM | LIVE_VERIFICATION |

Runner binding: `bash scripts/run-python-tests.sh` (collects `scripts/tests/*-test.py`; verified present by baseline). Feasibility evidence: handle_key 8472-8478 and `_read_meta_key` 6247-6272 inspected; `ungetch` already used there. Capabilities: CAP-PY-UNIT = python3 available (CODING); CAP-LIVE-TERM = CSI-u-capable terminal + clipboard (LIVE_VERIFICATION only, never blocks coding).

## 4. Components not to modify
`_chat_key` Enter block, `scripts/lib/home_actions.py`, triage composer, mouse capture code, existing tests.

## 6. Data-flow changes
bytes -> getch -> handle_key -> [burst check] -> Esc path `_read_meta_key` -> [paste/newline] -> `edit_insert` -> `_set_composer`; otherwise unchanged.

## 8. Interface changes
New internal functions only (`sanitize_paste`, `classify_escape`, `_composer_newline`, `_read_csi`). No external API.

## 10. Compatibility
Backslash-Enter and all existing keys preserved.

## 12. Error and recovery

Paste read bounded (per-read timeout ~50 ms). The reader consumes bytes until the first ESC[201~. The insert is truncated, in characters, to the remaining composer capacity (COMPOSER_LIMIT); on overflow the remaining bytes are discarded until ESC[201~ or timeout and are never dispatched as keys (so no overflow byte can act as Enter/submit). On timeout the partial text is inserted and nothing further is dispatched from that paste. `_read_meta_key` finally restores timeout; unknown CSI pushed back via ungetch (reverse order).

Paste terminator rule: the paste reader returns at the first `ESC[201~` it sees; that marker is consumed and never dispatched as keys. A nested `ESC[200~` inside the payload is dropped as data (not inserted, not restarting the paste). Because the first end marker wins, any bytes of a payload that follow a fake early end marker arrive as ordinary input and are subject to the normal burst/Enter rules rather than being treated as paste content; tests cover payloads containing an early `ESC[201~` and a nested `ESC[200~`.

## 14. Rollback plan
Revert the single commit; no state or schema. If terminal left in odd mode, `reset`.

## 15. Containment

Paste overflow rule: the paste reader reads to the first ESC[201~ (or idle timeout) regardless of COMPOSER_LIMIT, so excess bytes are never dispatched as keystrokes. The sanitized payload is truncated to the remaining composer capacity measured in characters (COMPOSER_LIMIT minus current composer length), inserted via edit_insert, and the rest is discarded. This supersedes the earlier 'total cap COMPOSER_LIMIT bytes' wording.

Enhanced modes are emitted only when the injectable mode writer's stream is a tty and `UNCLE_ENHANCED_KEYS` is not `0`; tests inject a fake writer (no tty detection by test-environment sniffing). Disable strings are written iff enable strings were written, from finally, atexit and SIGTERM/SIGHUP handlers; on SIGTSTP they are written before suspend and the enable strings are re-emitted on SIGCONT resume. Paste read is bounded by a per-read timeout (~50 ms). The reader keeps draining every paste byte through the first `ESC[201~` (or until timeout), even after the composer limit is reached, so paste bytes are never left in the input stream to be dispatched as keys. The payload is sanitized, then truncated by characters (not bytes) to the composer's remaining capacity (COMPOSER_LIMIT minus existing composer characters) before edit_insert; all excess and the end marker are discarded, never inserted and never dispatched as keystrokes (so excess newlines cannot submit). If a read times out before the end marker, the partial payload is inserted under the same truncation rule and the composer enters paste-tail mode: any Enter (LF/CR, 10/13) arriving is inserted as a newline, never submitted, until input has been idle for 100 ms (a nodelay getch returning no key after that idle window), after which paste-tail mode ends and plain Enter submits again. `_read_meta_key` finally restores timeout; unknown CSI is pushed back via ungetch (reverse order).

Paste-tail mode: when a bracketed paste ends by timeout without ESC[201~, the partial payload is inserted and the composer enters paste-tail mode. While in paste-tail mode, Enter (10/13) is inserted as a newline and never submits, and a late ESC[201~ is consumed silently. Paste-tail mode ends when no input has arrived for 150 ms (checked on each nodelay getch idle) or on any non-Enter printable key following a 150 ms idle gap; the next lone Enter after that submits normally. This state is a pure flag on the key reader and is unit-testable with a fake screen and an injectable clock.

## 16. Automated-test strategy

New `scripts/tests/home-composer-keys-test.py` (hyphenated): sanitize_paste cases (CRLF, ESC, oversize); `_read_meta_key` with fake screen feeding `[200~a\nb[201~`, `[13;5u`, `[27;5;13~`, Esc+CR, Esc+x pushback, truncated paste; burst Enter vs lone Enter; submit not called for all newline paths; mode-emission test with an injectable writer asserting startup output is exactly `ESC[?2004h` + `ESC[>4;2m` (no `ESC[>1u`/`ESC[>5u`/`ESC[<u`) and teardown output is exactly `ESC[?2004l` + `ESC[>4;0m`, and that disable strings are written iff enable strings were. Defect injection: confirm tests fail if paste newline calls submit.

Additional required test cases in `home-composer-keys-test.py` (all use a fake screen with scripted getch/ungetch, an injectable clock and an injectable mode writer; submit is a recording stub): (1) parameterized over bytes 10 and 13: lone Enter submits, burst Enter (key pending) inserts newline, Esc+Enter inserts newline with plain composer focus. (2) Burst threshold: Enter with 0, 1 and 2+ pending keys asserting the plan's threshold, with pushback order checked. (3) Non-composing states (picker, slash menu, edit mode): paste, Ctrl+Enter and Esc+Enter leave state unchanged, call neither insert nor submit, and never invoke the picker/edit Enter handler; Esc then Enter keeps legacy behavior. (4) Paste overflow: multibyte paste into a partly filled composer with a CR in the overflow; composer length equals COMPOSER_LIMIT in characters, stream drained through ESC[201~, submit not called, no remaining paste bytes reach handle_key. (5) Timed-out paste with a following CR inside the idle window inserts newline and does not submit; after the window (fake clock) Enter submits. (6) Embedded early ESC[201~ followed by CR and a nested ESC[200~: reader returns at first end marker, nested start dropped, submit not called. (7) Burst detection is not consulted during an active paste and no paste-flow path calls submit. (8) sanitize_paste drops DEL, C1 controls incl. U+009B, U+202A-202E, U+2066-2069 and keeps TAB and LF. (9) Non-Ctrl modifiers ESC[13;2u, ESC[13;3u, ESC[27;2;13~ behave as plain Enter; unknown CSI is pushed back in correct order; Ctrl-C and Meta b/f/d modified forms map to legacy keycodes. (10) Mode writer: startup bytes equal exactly ESC[?2004h ESC[>4;2m and contain no ESC[>...u; teardown equals exactly ESC[?2004l ESC[>4;0m and has no ESC[<u; UNCLE_ENHANCED_KEYS=0 writes neither at start nor teardown; the registered finally, atexit and SIGTERM/SIGHUP cleanups invoked with the fake writer emit the disable strings once.

## 17. Regression-test strategy
Existing home-actions-test.py unchanged; full `bash scripts/run-python-tests.sh` and `bash scripts/run-shell-tests.sh` (parallel group `1 2`).

## 18. Manual verification

Enhanced modes are emitted only when stdout is a tty and `UNCLE_ENHANCED_KEYS` is not `0`; tests inject a fake writer instead of detecting a test environment. Disable strings are written iff enable strings were written, through the same injectable writer, so the teardown test asserts: enabled -> both disable strings emitted; gated off -> nothing emitted at start or teardown.

Additional manual checks: run the app in a capable terminal and `kill -TERM` / `kill -HUP` it, confirm the shell is clean (no bracketed-paste or modifyOtherKeys residue; paste and keys behave normally); Ctrl-Z suspend then `fg` resume, confirm modes are off while suspended and re-enabled after resume; smoke Ctrl-C quit and Meta b/f/d word movement with enhanced modes on.

## 19. Observability
None.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` | pure helpers; `_read_meta_key` CSI/paste/Esc+Enter; `_composer_newline`; handle_key burst check; mode enable/disable | Core feature | Medium (key path) | home-composer-keys-test.py, home-actions-test.py |
| `scripts/tests/home-composer-keys-test.py` | new | Verify behaviors | Low | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-1, SB-9 | SI-5 | uncle_tui.py | home-actions-test.py:396 + new, new test: parameterized over bytes 10 and 13, lone Enter submits; Enter with 0 or 1 pending keys submits; Enter with 2+ pending keys is a newline | Enter submits |
| AC-2 | SB-2, SB-3 | SI-1 | _read_meta_key | new test (13;5u and 27;5;13~ newline; 13;2u and 13;3u submit as plain Enter; unknown CSI pushed back unchanged), new test: Ctrl+Enter/Esc+Enter sequences outside plain composing state (picker, slash menu or edit mode active) are swallowed with no insert and no submit, new test: Esc+CR/LF inserts newline only with plain composer focus; with picker/slash menu/edit mode open, Esc then Enter keeps legacy behavior | Ctrl+Enter in capable terminal |
| AC-3 | SB-4, SB-5 | SI-1, SI-2, SI-4 | _read_meta_key, handle_key | new test (fake-screen burst peek: queued key -> newline plus pushback; empty queue -> submit), new test: paste in picker/slash menu/edit mode is fully consumed and discarded, with no insert and no submit, new test: oversize paste — payload exceeding remaining capacity is truncated in characters, remainder drained and discarded through ESC[201~ (or timeout), no insert, submit not called, no overflow bytes dispatched as keys, new test: unterminated paste `[200~a\nb` then timeout; Enter arriving within the 100 ms idle window inserts a newline and does not submit; Enter after the 100 ms idle window submits | 3-line paste, paste while picker open is ignored |
| AC-4 | SB-7 | SI-5 | uncle_tui.py | full Python suite, new test: with modifyOtherKeys level 1, Ctrl-C and Meta b/f/d (including any 27;mod;code~ / CSI-u forms) resolve to the legacy keycodes and unknown CSI is pushed back, new test: Esc then Enter in picker/edit mode behaves as before (no newline inserted) | smoke |
| AC-5 | SB-6, SB-8 | SI-3 | `_run_loop` teardown | new test: injected writer receives disable strings on normal exit, exception, simulated SIGTERM/SIGHUP handler and SIGTSTP; re-enable on SIGCONT; nothing written when gating is off | copy, clean exit, kill -TERM/-HUP leaves shell clean, suspend/resume restores modes |

Esc+Enter rule (AR-012): Esc followed by Enter (10/13) inserts a newline only when the plain composer has focus. When a picker, slash menu or edit mode is open, the legacy behavior stays: Esc is handled as before and the following Enter is dispatched as a normal key (pushback preserved).

No bug regression test applies beyond: multi-line paste does not submit (fails before, passes after).

## Implementation sequence

1. Pure helpers `sanitize_paste`, `classify_escape` and tests for them
   Owns: `scripts/tests/home-composer-keys-test.py`
2. Key-reader and handle_key integration, `_composer_newline`, burst detection (builds on step 1's helpers in the same file as step 3)
   Owns: `uncle_tui.py`
   Depends on: 1
3. Terminal mode enable/disable in `_run_loop` and teardown (same file `uncle_tui.py` as step 2; edits distinct regions, applied after step 2). Implements exactly the strings fixed in D-2 as named constants, through an injectable writer and enable predicate, with the idempotent finally/atexit/SIGTERM/SIGHUP/SIGTSTP-SIGCONT handling; the exact strings are asserted by the step 1 test file.
   Owns: `uncle_tui.py`
   Depends on: 2
4. Run Python and shell suites; fix only product code
   
   Defect-injection evidence for new tests is recorded in `.uncle/docs/IMPLEMENTATION_NOTES.md`
   (step 4)
   Owns: `uncle_tui.py`, `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 3

## 21. Scope cuts under time pressure

Cut first: Esc+Enter (SB-3), then burst detection (SB-5). Keep modifyOtherKeys level 1 (Ctrl+Enter) as long as possible; if AC-4 key regressions appear, drop mode emission entirely and rely on Esc+Enter/backslash-Enter. Never cut: bracketed paste, plain Enter preservation, mode teardown.

## 22. Risks and unresolved questions
- Enhanced-key mode could change how some terminals report other modified keys (Ctrl-Backspace etc.); mitigated by `UNCLE_ENHANCED_KEYS=0` and manual smoke. Not blocking.
- Burst heuristic may treat rapid double Enter as newline; accepted, low frequency.
- Copy relies on terminal selection with mouse capture ON by default (needs Ctrl-G or bypass modifier); documented, not changed.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Plain Enter may arrive as byte 10 or 13, and key 10 must still submit per the protected test, so the plan must state when each byte is a newline trigger. | Edited s1.1 and R-1 to state that burst detection and Esc+Enter apply equally to 10 and 13, and that a lone 10/13 with no pending input and no preceding Esc always submits. |
| AR-002 | Accepted | Paste/Ctrl+Enter behavior outside the plain composer was unspecified; swallowing them is the safe choice that avoids unintended picker/edit-mode submits. | Extended D-3 with a state-gating rule and updated AC-2/AC-3 traceability tests to cover the non-composing swallow case. |
| AR-003 | Accepted | Overflow handling was ambiguous; leftover paste bytes dispatched as keys could submit on Enter, so the reader must drain to the end marker and truncate by characters. | Rewrote s12.1 (Error and recovery) with drain-and-discard overflow rule and updated AC-3 test expectation. |
| AR-004 | Accepted | After a paste read timeout, remaining pasted lines would arrive as plain Enters and submit, violating SI-1/AC-3; a paste-tail mode closes the gap. | Added paste-tail rule block to s12, extended R-2 mechanism, and added a paste-tail test to AC-3. |
| AR-005 | Accepted | D-2 and the approach text contradict on kitty flags; the exact emitted strings must be fixed so tests and checklists share one oracle. | Rewrote s1.1 mode strings and D-2: startup emits exactly ESC[?2004h and ESC[>4;2m, no kitty; teardown emits ESC[?2004l and ESC[>4;0m. |
| AR-006 | Accepted | Modifier handling for CSI-u/modifyOtherKeys Enter and unknown CSI was unspecified; a simple explicit rule closes the gap. | Added modifier-handling rule block to section 1, extended R-4 (property/mechanism) and AC-2 tests to cover non-Ctrl modifiers and unknown CSI pushback. |
| AR-007 | Accepted | A single pending byte (key repeat, fast typing) must not turn Enter into a newline; requiring at least 2 pending bytes keeps plain Enter submitting. | Edit s1.1 and s3.1: burst detection fires only when at least 2 further keys are already pending (peeked and pushed back); otherwise Enter submits. |
| AR-008 | Accepted | Level 2 modifyOtherKeys would re-encode Ctrl-C and Meta b/f/d and risk AC-4; using level 1 avoids this because it only reports otherwise-unencodable modified keys. | D-2 decides on modifyOtherKeys level 1 (ESC[>4;1m) with no kitty; s1.1 and AC-4 updated, plus a CSI 27/CSI-u mapping fallback for Ctrl-C and Meta b/f/d. |
| AR-009 | Accepted | D-2 and s1 contradict on kitty flags while teardown pops unconditionally; dropping kitty entirely removes the ambiguity and the unmatched pop. | Rewrote D-2 and s1.1 to emit only ESC[?2004h and ESC[>4;2m at startup and ESC[?2004l and ESC[>4;0m at teardown, with no kitty sequences. |
| AR-010 | Accepted | Paste and Ctrl+Enter were unconditional while only burst detection was gated, leaving picker, slash-menu and edit-mode behavior undefined. | Added decision D-6 (swallow outside plain composing), tightened D-3, and extended AC-2/AC-3 tests and manual checks. |
| AR-011 | Accepted | Over-limit or timed-out paste leftovers could be dispatched as keys and submit; the reader must drain to the end marker and keep newlines in the burst as newlines. | Replaced s12.1 with paste overflow/timeout rules: drain past limit discarding excess; after timeout LF/CR in the same burst stay newlines. |
| AR-012 | Accepted | Esc+Enter changing meaning must be limited to the plain composer so picker and edit-mode Esc-then-Enter behavior is preserved (SB-7). | Traceability: added Esc+Enter focus rule block, AC-2 test for plain-composer-only newline, AC-4 test for picker/edit-mode Esc then Enter preserved. |
| AR-013 | Accepted | Burst detection must be explicitly gated on bracketed paste being inactive and must only ever insert a newline, never submit. | Edited D-3 to state burst detection applies only when bracketed paste is not active and never submits. |
| AR-014 | Accepted | ESC/C0-only sanitization leaves DEL, C1 controls (incl. 8-bit CSI 0x9B) and bidi controls able to inject or spoof; extending the drop set is cheap and safe. | D-4 now drops DEL, C1 (U+0080-009F) and bidi controls U+202A-202E, U+2066-2069 in addition to ESC/C0; s1 helper description updated. |
| AR-015 | Accepted | A fake paste-end marker inside a payload was unspecified; a fixed rule prevents trailing bytes being parsed as keys. | Section 12 (s10) gains a paste-terminator rule: first ESC[201~ ends the paste, nested ESC[200~ dropped as data. |
| AR-016 | Accepted | Overflow/timeout handling was unspecified, letting leftover paste bytes be dispatched as keystrokes including submitting Enter. | Section 12 now says overflow bytes are truncated by characters and discarded until ESC[201~ or timeout, never dispatched as keys; AC-3 test row updated. |
| AR-017 | Accepted | Mode teardown must cover signal exits and suspend/resume, and test-mode gating needs a defined, injectable rule. | Edited R-3, s12.1 and AC-5 to name finally/atexit/SIGTERM/SIGHUP disable paths, SIGTSTP/SIGCONT re-emit, and injectable writer gating. |
| AR-018 | Accepted | Burst detection needed a precise, testable contract: a nodelay getch peek with pushback and no timing window. | Added a burst-detection contract block to section 1 and aligned AC-3 tests to a fake-screen peek contract. |
| AR-019 | Accepted | D-2 and s1 contradicted each other on kitty flags, leaving no oracle for the emitted strings. | Fix D-2, s1.1 and s13.1: start emits exactly ESC[?2004h and ESC[>4;2m (no kitty); teardown emits ESC[?2004l and ESC[>4;0m. |
| AR-020 | Accepted | A byte cap on the read and a character limit in edit_insert conflict; reading to the end marker and truncating by remaining characters resolves it. | Section 12 Containment gains an overflow rule: read to ESC[201~, truncate to remaining capacity in characters, discard the rest. |
| AR-021 | Accepted | Paste and Ctrl+Enter behavior outside plain composing state was undefined; swallowing them is safe and preserves picker/edit Enter semantics. | Edited D-3 to state the state gate and AC-2/AC-3 to require swallow outside plain composing. |
| AR-022 | Accepted | After a paste read timeout the remaining pasted lines would arrive as plain Enters and submit, violating SI-1; an idle-window rule closes this. | Section 12 (s12.1) adds a post-timeout paste-tail mode: Enter is a newline until input is idle 100 ms; AC-3 tests updated. |
| AR-023 | Accepted | Teardown test needs a defined gating rule and an injectable writer to be testable without a real tty. | R-3 mechanism and s15.1 now state disable strings are written iff enable strings were written, via an injectable writer; s5.1 R-3 updated accordingly. |
