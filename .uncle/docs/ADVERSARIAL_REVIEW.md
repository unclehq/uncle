## AR-001: Plain Enter can arrive as byte 10 or 13 (ICRNL), and key 10 must submit per the protected test, yet the burst detector a

- Severity: HIGH
- References: CHANGE_PLAN s1 (Esc followed by 10/13; burst k in (10,13)) vs R-1 (_chat_key(10) submits). Plan should state: 'Burst detection and Esc+Enter apply to both 10 and 13; lone 10/13 with no pending input and no preceding Esc always submits.'
- Failure: Plain Enter can arrive as byte 10 or 13 (ICRNL), and key 10 must submit per the protected test, yet the burst detector and Esc+10/13 treat both bytes as newline triggers. Plan does not say whether a lone Esc then Enter(10) is newline or submit, or whether burst applies equally to 10 and 13.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Plan never states whether paste, Ctrl+Enter, or burst-Enter apply when the composer is not in plain composing state (pic

- Severity: HIGH
- References: CHANGE_SPEC SB-4 has no state qualifier; D-3 limits only burst. Plan should say: 'Outside plain composing state (picker, slash menu, edit mode), bracketed paste and Ctrl+Enter sequences are consumed and discarded; they never insert or submit.'
- Failure: Plan never states whether paste, Ctrl+Enter, or burst-Enter apply when the composer is not in plain composing state (picker/slash menu open, edit mode, empty composer). Burst detection is limited to 'composing' but SB-2/SB-4 are unconditional, and a paste in a picker is undefined.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Paste exceeding COMPOSER_LIMIT is ambiguous: plan caps the read at COMPOSER_LIMIT bytes, but it does not say whether the

- Severity: MEDIUM
- References: CHANGE_PLAN s12 'total cap COMPOSER_LIMIT bytes'; SI-2 limit on characters. Plan should say: 'The reader drains and discards all paste bytes through ESC[201~ (or timeout) after truncating the insert to the remaining capacity in characters.'
- Failure: Paste exceeding COMPOSER_LIMIT is ambiguous: plan caps the read at COMPOSER_LIMIT bytes, but it does not say whether the remainder is drained until ESC[201~ or left in the input stream, where it would be interpreted as keystrokes, including Enter submits. Bytes vs characters and the existing composer content also collide with the limit.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Timeout and truncated-paste behavior conflict: partial paste is inserted 'on timeout and continue', but the remaining pa

- Severity: MEDIUM
- References: CHANGE_PLAN s12 'on timeout insert partial and continue'; SI-1. Plan should say: 'After an unterminated paste times out, the composer stays in paste-tail mode so that Enter within the next burst is treated as newline per SB-5.'
- Failure: Timeout and truncated-paste behavior conflict: partial paste is inserted 'on timeout and continue', but the remaining paste bytes arriving later would then be handled as ordinary keys, where their newlines submit. This contradicts SI-1 and AC-3.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: D-2 is undecided: it contains conflicting text on kitty flags (1 vs 5, 'use ...

- Severity: MEDIUM
- References: CHANGE_PLAN s1 'ESC[>1u ... use ESC[>5u? see D-2'; D-2. Plan should say: 'Startup emits exactly ESC[?2004h and ESC[>4;2m; kitty protocol is not enabled; teardown emits ESC[?2004l and ESC[>4;0m.'
- Failure: D-2 is undecided: it contains conflicting text on kitty flags (1 vs 5, 'use ... choose ... or skip') and the code uses ESC[<u pop without a matching push guarantee. Implementers, tests and checklists cannot agree on which exact strings are emitted at start.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Control-character handling for pasted TAB and for modifiers other than Ctrl (e.g.

- Severity: LOW
- References: CHANGE_SPEC AC-2 lists only 13;5u and 27;5;13~. Plan should say: 'CSI-u/modifyOtherKeys Enter with any modifier other than Ctrl is treated as plain Enter (submit), and all other unknown CSI sequences are pushed back unchanged.'
- Failure: Control-character handling for pasted TAB and for modifiers other than Ctrl (e.g. Shift+Enter ESC[13;2u, Alt+Enter ESC[13;3u) is unspecified. Modifyotherkeys level 2 will also report these for other keys, and the plan states only the 5-modifier cases.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Burst detection (Enter with any pending input becomes newline) conflicts with SB-1/SI-5 'plain Enter unchanged' and AC-1

- Severity: HIGH
- References: CHANGE_PLAN s1 (handle_key burst check) vs s3 'byte-for-byte unchanged'; risk s22 accepts rapid double Enter as newline.
- Failure: Burst detection (Enter with any pending input becomes newline) conflicts with SB-1/SI-5 'plain Enter unchanged' and AC-1: key-repeat or fast typing submits as newline. Settle: 'Burst detection applies only when at least 2 further bytes are already pending; otherwise Enter submits.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: modifyOtherKeys level 2 makes Ctrl-C, Meta b/f/d and other modified keys arrive as CSI 27;..~ sequences that are only 'p

- Severity: HIGH
- References: CHANGE_PLAN D-2 and risk s22 item 1 ('Not blocking'); AC-4 lists Ctrl-C quit and Meta b/f/d.
- Failure: modifyOtherKeys level 2 makes Ctrl-C, Meta b/f/d and other modified keys arrive as CSI 27;..~ sequences that are only 'pushed back as unknown', risking AC-4 regressions. Settle: 'Map 27;mod;code~ and CSI-u for Ctrl-C and Meta-b/f/d to legacy keycodes, or use level 1 only.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: D-2 is self-contradictory on whether kitty flags are emitted (ESC[>1u vs ESC[>5u vs none), yet teardown writes ESC[<u un

- Severity: MEDIUM
- References: CHANGE_PLAN s1 ('use ESC[>5u? see D-2') and D-2 text; teardown list includes ESC[<u.
- Failure: D-2 is self-contradictory on whether kitty flags are emitted (ESC[>1u vs ESC[>5u vs none), yet teardown writes ESC[<u unconditionally. Settle: 'Emit only ESC[>4;2m and ESC[?2004h; no kitty sequences; teardown writes ESC[>4;0m and ESC[?2004l only.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Paste and Ctrl+Enter behavior is unspecified when the composer isn't in plain composing state (picker/slash menu, edit m

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 gates burst only; SB-2/SB-4 triggers carry no state qualifier; AC-4 preserves picker/edit Enter.
- Failure: Paste and Ctrl+Enter behavior is unspecified when the composer isn't in plain composing state (picker/slash menu, edit mode). Only burst detection is gated on composing. Settle: 'Paste and Ctrl+Enter/Esc+Enter are consumed with no insert and no submit unless the plain composer has focus.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Over-limit or timed-out paste is ambiguous: leftover bytes and the ESC[201~ marker may be read as keystrokes, including

- Severity: MEDIUM
- References: CHANGE_PLAN s12 (total cap COMPOSER_LIMIT bytes; on timeout insert partial and continue) vs SI-1.
- Failure: Over-limit or timed-out paste is ambiguous: leftover bytes and the ESC[201~ marker may be read as keystrokes, including Enter that submits. Settle: 'Read to the end marker even past the limit, discarding excess; after a timeout, LF/CR within the same burst remain newlines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Esc followed by Enter changes meaning to newline, but behavior with a picker or edit mode open is unspecified.

- Severity: LOW
- References: CHANGE_SPEC SB-3 vs SB-7 (Esc+other key pushback preserved).
- Failure: Esc followed by Enter changes meaning to newline, but behavior with a picker or edit mode open is unspecified. Settle: 'Esc+Enter inserts a newline only when the plain composer has focus; otherwise old Esc then Enter behavior stays.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Burst detection turns any Enter with queued input into a newline, so behavior depends on timing, and it is unspecified w

- Severity: HIGH
- References: CHANGE_PLAN D-3 and section 1 (handle_key peek via nodelay getch+ungetch); SB-5 says only 'further input already queued'.
- Failure: Burst detection turns any Enter with queued input into a newline, so behavior depends on timing, and it is unspecified whether it applies during an active bracketed paste. Plan should say: 'Burst detection applies only when bracketed paste is not active, and never submits.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Sanitization drops ESC and C0 only.

- Severity: HIGH
- References: CHANGE_PLAN D-4; CHANGE_SPEC section 10 and AC-3 list only ESC and C0.
- Failure: Sanitization drops ESC and C0 only. C1 controls (including 8-bit CSI 0x9B), DEL and Unicode bidi/format characters are unspecified. Plan should say: 'sanitize_paste also drops DEL, C1 controls and U+202A-202E, U+2066-2069.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The plan does not say how a fake paste-end marker inside a payload is handled.

- Severity: MEDIUM
- References: CHANGE_SPEC section 10 ('fake paste-end markers'); CHANGE_PLAN section 12 says only 'read until ESC[201~ or timeout/limit'.
- Failure: The plan does not say how a fake paste-end marker inside a payload is handled. Bytes after an early ESC[201~ could be parsed as keys, including Enter. Plan should say: 'The reader returns at the first ESC[201~. Nested ESC[200~ is dropped as data.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Paste overflow and timeout behavior is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN section 12 ('total cap COMPOSER_LIMIT bytes; on timeout insert partial and continue'); SB-4.
- Failure: Paste overflow and timeout behavior is unspecified. After COMPOSER_LIMIT is reached, the remaining bytes may be dispatched as keystrokes (including Enter, which submits). Plan should say: 'On overflow, discard remaining bytes until ESC[201~ or timeout; never dispatch them as keys.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Mode teardown does not name signal exits (SIGTERM, SIGHUP) or suspend/resume (SIGTSTP).

- Severity: MEDIUM
- References: CHANGE_PLAN R-3, section 15 and SI-3 ('every exit path') against only 'teardown (~9102)'.
- Failure: Mode teardown does not name signal exits (SIGTERM, SIGHUP) or suspend/resume (SIGTSTP). 'Not in test' detection is also undefined. Plan should say: 'Disable strings are emitted from finally, atexit and SIGTERM/SIGHUP handlers, and modes are re-emitted on resume from SIGTSTP.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Burst detection is untestable as written: 'input pending' has no stated window and no fake-screen contract.

- Severity: HIGH
- References: CHANGE_PLAN s1 'peek (nodelay getch + ungetch)'; SB-5 'further input already queued'.
- Failure: Burst detection is untestable as written: 'input pending' has no stated window and no fake-screen contract. Say: 'Enter is a newline iff a nodelay getch immediately returns a key, which is pushed back; otherwise Enter submits.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: D-2 and the approach text contradict each other (ESC[>1u vs ESC[>5u vs skip kitty), so the exact startup and teardown st

- Severity: HIGH
- References: CHANGE_PLAN s1 and D-2; section 16 'teardown emits disable strings'.
- Failure: D-2 and the approach text contradict each other (ESC[>1u vs ESC[>5u vs skip kitty), so the exact startup and teardown strings have no oracle. Say: 'Startup writes exactly ESC[?2004h and ESC[>4;2m, no kitty; teardown writes ESC[?2004l and ESC[>4;0m.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Paste overflow is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s12 'total cap COMPOSER_LIMIT bytes' vs SI-2 and AC-3.
- Failure: Paste overflow is unspecified. A byte cap on the read and a character limit in edit_insert coexist, and nothing says whether the excess is truncated or drained. Say: 'Paste is read to ESC[201~, truncated to remaining composer capacity, and the rest is discarded.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Paste and Ctrl+Enter in non-composing states (picker, menu, edit mode) are undefined.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 'composing state'; SB-2 and SB-4 have no state qualifier; AC-1 excludes picker/menu/edit.
- Failure: Paste and Ctrl+Enter in non-composing states (picker, menu, edit mode) are undefined. Say: 'Outside plain composing, paste and Ctrl+Enter are swallowed and never reach picker or edit-mode Enter handlers.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: After a paste read timeout, 'insert partial and continue' lets the remaining pasted lines arrive as plain Enters and sub

- Severity: MEDIUM
- References: CHANGE_PLAN s12 'per-read timeout ~50 ms'; CHANGE_SPEC s8; SI-1.
- Failure: After a paste read timeout, 'insert partial and continue' lets the remaining pasted lines arrive as plain Enters and submit, violating SI-1. Say: 'After a paste timeout, Enter is a newline until input has been idle for N ms.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: The UNCLE_ENHANCED_KEYS=0 and 'not in test' gating is undefined for the teardown test.

- Severity: LOW
- References: CHANGE_PLAN s15 vs R-3 and s16.
- Failure: The UNCLE_ENHANCED_KEYS=0 and 'not in test' gating is undefined for the teardown test. Say: 'Disable strings are written iff enable strings were written, and the writer is injectable.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
