# Change Plan (Issue 168)

Seeded from [unclehq/uncle#168](https://github.com/unclehq/uncle/issues/168).

Issue 168

Omitted sections: Schema, Migration, Feature flag, Concurrency, Observability (none apply)

## 1. Selected approach

In `slash()` of `scripts/lib/uncle_repl.py`, after computing `name` (already lowercased by the existing `parts[0][1:].lower()`, so `/Q` behaves as `/q`), and BEFORE the existing quit/exit branch, if `len(name) == 1` and `name` is an ASCII letter a-z: collect candidates whose names start with it. Decision D1: the candidate set is the keys of `USAGE` in definition order followed by `quit` and `exit`, de-duplicated, so the set is fixed whether or not USAGE contains those two (no separate alias table). One match: set `name` to it, so /q -> quit, /e -> exit, /h -> help, /m -> mode, /i -> issue, /c -> clear, /t -> triage, /d -> do, /r -> resume, and all existing branches, arg validation and quit/exit handling then apply unchanged. Several: `self.refuse` with exactly `ambiguous command: /<c> (matches: /<a>, /<b>)`, e.g. `ambiguous command: /s (matches: /stop, /settings)`: matches are prefixed with `/`, listed in candidate order (USAGE definition order, then quit/exit) and joined by `, `; return None (rc 2). None: fall through to the existing unknown-command refusal (rc 2). A bare `/` (empty name) and any one-character name that is not ASCII a-z (digits, punctuation, control, non-ASCII or multibyte characters) or matches no command (e.g. `/x`, `/?`, `/1`) is never expanded and takes the unknown-command refusal unchanged; nothing is executed.

Ordering: ambiguity is decided on the name alone, before any argument validation, so `/s foo` -> ambiguity refusal (rc 2). A uniquely expanded name then runs the existing branches, so `/q x` prints `usage: /quit` via complain and does not quit, `/c x`, `/r x`, `/t x` print `usage: /clear`, `usage: /resume`, `usage: /triage`, while a bare `/q` quits.

Dispatch: shortcut-invoked commands go through the same `self.execute` path and attended-mode behavior as the full names (/c -> clear_build, /r -> resume_build, /i N -> github_issue), with the original typed line passed unchanged to execute; /t and /d print the TUI-needed message.

Decision D2: HELP is unchanged (no one-letter shortcut mention is added) and no test asserts that HELP mentions shortcuts; the existing HELP assertions and the unknown-command message, which prints `HELP.strip().splitlines()[-1]`, are unaffected.

Decision D3: tests pin the fixed letter-to-command map (h->help, m->mode, i->issue, c->clear, t->triage, d->do, e->exit, r->resume, q->quit, and /s ambiguous between settings and stop), so any new USAGE key that makes a shortcut ambiguous or changes its target fails the suite.

Ordering and validation (AR-013): one-character expansion runs first, immediately after `name` is lowercased and before the existing quit/exit branch. `name` is then rebound to the full command, so `/q foo` and `/e foo` hit the existing 'args present => usage error' check (`self.complain(USAGE[name])`) and do not quit; bare `/q` and `/e` return "quit". Expansion never bypasses argument validation.

Session flow and case (AR-009, AR-010): the ambiguous refusal is emitted through `self.refuse`, exactly as the unknown-command refusal is, so it uses the same stream, rc 2, and session continuation (the REPL keeps reading subsequent lines, nothing is executed). Matching is case-insensitive because it runs on the already-lowercased `name`, so `/Q` expands like `/q`. A bare `/` (empty name) and any single character that matches no command (for example `/x`, `/1`, `/?`) keep the existing unknown-command refusal, rc 2, unchanged.

Output safety (AR-014): the ambiguous message is emitted only via `self.refuse` (which writes through the escape-filtered `Out`), and is built only when the typed name is a single non-control character, validated before interpolation; it interpolates only that character and the candidate command names taken from USAGE. Any other typed text, control or multibyte characters included, takes the existing unknown-command refusal path, which also goes through `self.refuse`. Nothing is written outside `self.refuse`/`self.say`/`self.complain`.

## 2-3. Alternatives
A separate alias table: duplicates names and can drift. Rejected; deriving from USAGE is smaller.

## 4. Components
See table.

## 5. Not to modify
TUI slash handling, other scripts, USAGE contents.

## 8. Interface
No API change; stdin/stdout behavior only.

## 10. Compatibility

Full names and unmatched refusals unchanged. Single-character names only. A usage error from an expanded command behaves exactly as the full-name command (same stream, same rc, same usage text, e.g. `/i` prints `usage: /issue`). The original typed line (e.g. `/i 12`) is passed unchanged to `self.execute`; only the local `name` is rewritten. Any HELP change only appends a one-letter shortcut note and keeps existing assertions valid; the last line of HELP stays the Commands line, since the unknown-command refusal prints it.

## 12. Error behavior
Ambiguous and unmatched: refuse, rc 2, nothing executed.

## 14. Rollback
Revert the two files; no state or persistence involved.

## 16-17. Test strategy

Add to `repl-session-test.py` (no existing test changed; the `/frob` check is the regression guard). Checks: (1) Map pin: `/h`,`/m`,`/i`,`/c`,`/t`,`/d`,`/e`,`/r`,`/q` each resolve to help, mode, issue, clear, triage, do, exit, resume, quit, and `/s` is ambiguous, so any USAGE change altering the map fails. (2) `/q` and `/e` each quit, with a following line NOT processed; `/e` is neither ambiguous nor unknown; `/Q` quits. (3) `/q now`, `/e foo`, `/q foo` print `usage: /quit` (and exit usage for /e), do not quit, and a following line IS processed. (4) `/s`: exact stderr `ambiguous command: /s (matches: /stop, /settings)` (USAGE insertion order, `, ` joined), not containing `unknown command`, rc 2, a following valid line still processed, same stream as the `/frob` refusal; `/s foo` gives the same ambiguity refusal. (5) `/qu`, bare `/`, `/?`, `/1`, and a non-ASCII single character give `unknown command` rc 2 with no crash and no raw ESC bytes in output; the ambiguity and unknown messages contain no raw ESC bytes. The unknown-command output still ends with the Commands line (HELP is unchanged and asserted byte-identical). (6) `/m unattended`, `/h`, `/i` without arg prints `usage: /issue`; paired `/i` vs `/issue` assert identical stderr and rc. (7) `/q x`, `/c x`, `/r x`, `/t x` emit the same usage text and rc as their full-name forms. (8) `/t` and `/d` print the full-name `needs the TUI` message. (9) With a stubbed execute, `/c` and `/clear` produce identical payloads (clear_build), `/r` and `/resume` identical payloads (resume_build), and the original typed line (e.g. `/r`, `/i 12`) is passed unchanged.

## 18. Manual verification
Run `uncle --noui` and type `/q`, `/s`.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/uncle_repl.py` | one-char prefix expansion in slash(); optional HELP tweak | feature | Low: quit/exit/unknown paths | repl-session-test.py |
| `scripts/tests/repl-session-test.py` | add new checks | AC-1..4 | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: /q quits the session; /q with arguments (e.g. /q now) prints usage for /quit and does not quit. | S1 | V2 | uncle_repl.py | repl-session-test.py | /q |
| AC-2: fixed unique one-letter shortcuts h,m,i,c,t,d,e,r (and q) resolve to help, mode, issue, clear, triage, do, exit, resume, quit; a test asserts this complete map so USAGE changes that alter it fail the suite. Case-insensitive (/Q = /q); non-ASCII-letter single characters are unknown commands. | S2, S5, S6 | V2 | uncle_repl.py | repl-session-test.py | /m unattended |
| AC-3: an ambiguous one-character command such as `/s` is refused via the refusal path with rc 2 and nothing executed; the message is `ambiguous command: /<c> (matches: /<a>, /<b>)`, listing every candidate (USAGE keys plus quit and exit, de-duplicated) in USAGE insertion order with quit/exit appended last, each prefixed with `/` and joined by `, `. | S3 | V1, V2 | uncle_repl.py | repl-session-test.py | /s |
| AC-4 | S4 | V1, V2 | uncle_repl.py | repl-session-test.py | /qu |
| AC-5 | S7 | V1 | both | baseline commands | none |

## Restrictions

| ID | Source | Reqs | Property | Mechanism | Phase |
|---|---|---|---|---|---|
| R-1 | USER (CHANGE_REQUEST Details) | AC-4 | Only one-char names expand | `len(name)==1` guard | CODING |
| R-2 | USER | AC-3 | Ambiguous refused with rc 2 via self.refuse, message exactly `ambiguous command: /s (matches: /settings, /stop)`, candidates sorted alphabetically, comma-space separated, each prefixed with /; no unfiltered terminal escapes in the message | `self.refuse` only (escape-filtered Out); message built only for a validated single non-control character, interpolating just that character and USAGE-derived names | CODING |
| R-3 | USER | AC-5 | TUI untouched | no edits outside table | CODING |

Feasibility: inspected uncle_repl.py:212-223 (`refuse` already used for rc 2). No external capabilities needed (CAP: none).

## Implementation sequence

1. Implement prefix expansion in slash() restricted to a single ASCII a-z character (after lowercasing; /Q expands like /q; anything else takes the unknown-command refusal), and optional HELP tweak. Candidate set = USAGE keys plus quit and exit (de-duplicated). Expansion runs immediately after lowercasing the name and BEFORE the quit/exit branch, so /q -> quit and /e -> exit; after expansion all existing branches run unchanged, so /q foo or /e foo prints USAGE['quit'] / USAGE['exit'] via complain and does not quit. Rewrite only the local `name`; pass the original `line` unchanged to `self.execute`, keeping execute-type shortcuts on the same self.execute path with the same attended-mode behavior. Usage errors from expanded commands go through the same branches as full names (rc unchanged). The ambiguous refusal is emitted only via `self.refuse`, after validating that the typed name is a single non-control character; it starts `ambiguous command: /<c>` and lists candidates in USAGE insertion order joined by `, `. Any HELP tweak must only append a shortcut note on or before the Commands line and keep the last HELP line as the Commands line. Tests (step 2) must pin the fixed letter-to-command map per D3 and the /s ambiguity.
   Owns: `scripts/lib/uncle_repl.py`
2. **Pin argument and case edge cases in tests** — Add checks in repl-session-test.py: `/s foo` -> ambiguity refusal rc 2; `/q now` -> usage for /quit and session continues; `/Q` quits; bare `/` and `/?` -> unknown command rc 2.
   Owns: `scripts/tests/repl-session-test.py`
3. Add tests for AC-1..4 (independent of step 1's file; written against the specified behavior).
   
   Steps are independent and can proceed in parallel.
   Owns: `scripts/tests/repl-session-test.py`

## Scope cuts

No HELP change is planned. If time expires, cut the extra argument-handling tests for `/c`, `/r`, `/t` and `/d` first; keep AC-1..4 core tests.

## Risks

quit and exit are handled before the USAGE lookup and may not be USAGE keys; the candidate set is therefore always USAGE keys plus quit and exit, de-duplicated, and expansion runs before the quit/exit branch. Ambiguous message wording must not contain the text `unknown command`.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Code handles quit/exit before the USAGE lookup, so they may not be USAGE keys; the candidate set must be fixed, not conditional. | s1.1 and s16.1 now fix candidates as USAGE keys plus quit and exit (de-duplicated), expanded before the quit/exit branch. |
| AR-002 | Accepted | Message order and format must be deterministic so tests are stable. | s1.1 fixes the ambiguous message format and USAGE-definition order (quit/exit appended last); AC-3 and R-2 agree. |
| AR-003 | Accepted | Ordering of ambiguity versus argument validation was unspecified; settling it avoids divergent implementations. | s1.1 gains an ordering rule: ambiguity first, then expansion and existing arg validation (/q now -> usage, /s foo -> ambiguity). |
| AR-004 | Accepted | slash() already lowercases the name; the plan must state case-insensitivity and the fall-through for empty or non-matching names. | s1.1 gains a rule: matching is on the lowercased name, /Q quits, bare / or any no-match character is refused as unknown command, rc 2. |
| AR-005 | Accepted | Expansion precedes dispatch, so usage errors for shortcuts must match the full-name command exactly. | s6.1 (Compatibility) states usage errors from expanded commands behave identically to the full name, rc unchanged. |
| AR-006 | Accepted | The line passed to execute should stay the original typed text, and a HELP edit must not break the unknown-command message. | s6.1 and step-1 state the original line is passed unchanged and any HELP change only appends a shortcut note, keeping the Commands line last. |
| AR-007 | Accepted | Code handles quit/exit before the USAGE lookup, so the candidate set must be fixed rather than conditional. | Step 1 and Risks now fix candidates as USAGE keys plus quit and exit, with expansion before the quit/exit branch. |
| AR-008 | Accepted | Expansion-then-existing-branches gives /q now the same usage error as /quit now; this needs to be explicit and traceable. | AC-1 and step 1 now specify that /q with args prints usage for /quit and does not quit. |
| AR-009 | Accepted | Real gap: the plan did not state that the ambiguous refusal matches unknown-command session flow. | s1.1 now states the ambiguous refusal uses self.refuse, so same stream, rc 2 and session continuation as unknown command. |
| AR-010 | Accepted | Real gap: case, bare slash and non-letter one-character names were unspecified. | s1.1 now states matching is case-insensitive after lowercasing, and bare / or unmatched single characters keep the unknown-command refusal. |
| AR-011 | Accepted | The unknown-command refusal prints HELP's last line, so any HELP edit must keep the Commands line last. | Edit s1.1 D2 to say any shortcut note goes on or before the Commands line and the last HELP line stays the Commands line. |
| AR-012 | Accepted | Candidate order and wording must be fixed so AC-3 and its test are deterministic. | Edit s1.1 and AC-3 to list candidates in USAGE insertion order joined by ', ', message starting 'ambiguous command: /<c>'. |
| AR-013 | Accepted | Real ordering gap: quit/exit are handled before the USAGE lookup, so expansion must run first for /q foo to hit the usage check. | Add a block to s1 fixing order: expansion first, then existing quit/exit branch, so /q foo and /e foo print usage and do not quit. |
| AR-014 | Accepted | Refusal text interpolates typed input; it must go only through self.refuse (Out escape filter) and only for a validated single character. | Add a block to s1 requiring emission only via self.refuse with a validated single non-control character, and tighten R-2's mechanism. |
| AR-015 | Accepted | Real gap: the guard only checks length, so control/non-ASCII single characters and case behavior are unspecified. | s1.1 now states expansion applies only to a single ASCII a-z name after lowercasing (/Q expands like /q); others take the unknown-command refusal. |
| AR-016 | Accepted | Dynamic derivation from USAGE means future keys could silently change shortcuts; a pinned map test catches that. | s1.1 (D3) and AC-2 now require tests asserting the fixed letter-to-command map and /s ambiguity; step-1 text notes it. |
| AR-017 | Accepted | Real gap; shortcuts resolve to the full name, so they should share the full-name execute path and confirmation behavior. | Add to s1.1 that shortcut commands use the same self.execute path and attended-mode behavior, with the original line passed unchanged. |
| AR-018 | Accepted | quit/exit are handled before the USAGE lookup and may not be USAGE keys, so the candidate set must be fixed, not conditional. | Edit s1.1 D1 so candidates are USAGE keys plus quit and exit (de-duplicated), expansion runs before the quit/exit branch, and update Risks s16. |
| AR-019 | Accepted | A fixed message format makes AC-3 testable; sorted order is deterministic and independent of dict order. | s1.1 now fixes the message as `ambiguous command: /s (matches: /settings, /stop)`, sorted alphabetically, via self.refuse, rc 2; AC-3 and R-2 aligned. |
| AR-020 | Accepted | name is already lowercased at line 214, so case-insensitivity and unmatched single characters just need to be stated. | s1.1 states expansion follows lowercasing (/Q quits) and any unmatched one-character name, including bare `/`, takes the unknown-command refusal, rc 2. |
| AR-021 | Accepted | Expansion precedes dispatch, so argument handling and usage text are identical to full-name form; this needs stating and testing. | Added argument-handling rule to s1.1 and extra-arg tests (/q x, /c x, /r x, /t x) to s9.1. |
| AR-022 | Accepted | Expected outputs for /t, /d, /c, /r are determinable from existing code and must be asserted. | s9.1 now asserts /t and /d TUI-needed messages and /c and /r invoking clear_build and resume_build. |
| AR-023 | Accepted | An optional, untested HELP edit is ambiguous and could alter the unknown-command message, which prints HELP's last line; leaving HELP unchanged removes the ambiguity. | s1.1 D2 now states HELP is unchanged and no test asserts one-letter shortcuts in HELP; s15.1 no longer lists a HELP tweak as a cut. |
