# Change plan: Issue 246

Seeded from [unclehq/uncle#246](https://github.com/unclehq/uncle/issues/246).

Omitted sections: Schema (none); Migration (none); Concurrency (single-thread poll); Feature flag (none)

Issue 246

## 1. Selected technical approach
Add a read-only watcher to `uncle_headless._stream`. A pure helper `_scan_announcements(root, seen)` reads `<root>/.uncle/workflow/{preview-server,app-server,preview-vite}.{pid,url}` and returns new `Preview:`/`App:` lines. The select loop calls it at most every 0.5 s and emits through `_Writer` only when `writer.at_start` is true (otherwise defers). After the driver is reaped, a final call runs, preceded by a forced newline if a partial line is pending, then a launch-status line from `.uncle/launch.json` (via `completion_preview.launch_spec`, guarded by try/except) is emitted, before the finished-build block.

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| Reuse TUI `_poll_early_preview` / start own `PreviewServer` | Rejected: imports 9.6k-line curses module, would open a second server and browser |
| Have driver shell scripts print the URL to stdout | Rejected: touches driver and TUI-visible output, wider change surface |
| Poll state files from headless (selected) | Chosen |

## 3. Why preferred
Smallest surface; driver already owns servers and publishes URL files; no curses, no new processes, no exit-code impact.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`uncle_tui.py`, `preview_server.py`, `preview-build.sh`, `completion_preview.py`, launcher `uncle`, existing tests and `critical-suites.txt`.

## 6. Data flow

State files (driver-written) -> headless poll -> validate (reject any URL containing a control character: C0, DEL, C1, or other non-printable byte) -> sanitize every announcement (URL and launch-status text, including launch metadata) to one line by stripping terminal escape sequences and control characters -> redact -> `_Writer.emit` -> stdout.

## 7. State transitions

Watcher keeps `seen_preview` (last preview URL), `emitted_app_urls` (set of every app URL already announced this run; scan app-server before preview-vite) and a `launch_printed` flag; no other state.

## 8. Interface changes

None to `run()` signature. New output lines `Preview: <url>`, `App: <url>`, `App: launch ...`. Launch rendering: command launch prints the argument array as JSON; static webpage prints the path; webpage with a command prints the JSON argument array followed by the URL; kind none prints `none`. Missing or malformed launch.json prints no launch line.

## 10. Compatibility
Additive lines only; exit classification untouched; `completed`/`gates` detection runs only on driver lines (announcements are not fed to `handle_line`).

## 12. Error and recovery
All watcher IO wrapped in try/except (OSError, ValueError, UnicodeError); failure yields no line. URL validator: single line, <=2048 bytes, regex `^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/\S*)?$`; pid must satisfy `os.kill(pid,0)`.

## 14. Rollback plan
Revert the three files; no persisted state or migration.

## 16. Automated-test strategy

New `scripts/tests/headless-preview-test.py` using fake driver scripts in a temp root (signing disabled irrelevant; no git): each AC-1..AC-5, AC-7. Fake driver writes pid (its own) and url files, sleeps, prints lines. Required cases: (a) timing oracle: record Preview arrival time versus driver exit and file write, asserting it appears while the driver is still alive and within tolerance at a line boundary; (b) partial-line case: driver prints a partial line, publishes the URL, waits several seconds, then completes the line; assert no mid-line insertion and the Preview line follows the boundary (or final flush after a forced newline); (c) framing: driver output byte-for-byte equals output without announcements apart from added whole lines, and SI-3 takes precedence over the 1 s target while a line is incomplete; (d) parametrized launch.json shapes (command, static webpage, webpage with command and url, none, plus missing/malformed) asserting exact `App: launch ...` text; (e) sanitization over ESC, CSI, NUL, CR, BEL and Unicode line separators in url and launch fields yielding single-line control-free output, with control-bearing URLs rejected; (f) FIFO, over-2048-byte file and directory at url/pid paths: stream finishes within a timeout, exit code unchanged, no announcement; (g) simultaneous app-server/preview-vite and A->B->A recurrence emit one App line per distinct URL. The AC-3 tests for SB-3 and SB-4 must exist and pass for completion; removing them requires an approved AC-3 revision.

## 17. Regression strategy
Existing `headless-run`, `launcher-noui` suites via the two runner commands; run new suite explicitly (not in critical tier).

## 18. Manual verification
Run a `--noui --application` build of a small web app; observe `Preview:` line appears during the build and `App:` at the end; exit code unchanged.

## 19. Observability
The new lines are the observability.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Notes | SB-6, SI-2 | No curses; exit codes unchanged | stdlib-only watcher, no change to `classify_exit`; every announcement (URL and launch-status text) is sanitized to one line with escape sequences and control characters removed before redaction and emission | issue constraint | CAP-PY | CODING |
| R-4 | DESIGN | AR-005 | SI-2 | Announcements are escape-free single lines | URL validator rejects control characters; all announcement text (URLs and launch metadata) goes through the existing escape filter then redaction before `_Writer.emit` | untrusted state/launch text must not inject terminal controls | CAP-PY | CODING |
| R-2 | DESIGN | plan | SI-3 | No split lines; the ~1 s announcement target applies only at a driver line boundary | emit only at `writer.at_start`; while a driver line is incomplete, defer announcements without inserting a newline until that line ends or final flush (forced newline only at final flush); the ~1 s announcement target excludes this deferral interval | keeps framing; the ~1 s announcement target applies only at a driver line boundary, and announcements are deferred (no newline inserted) while a partial line is pending, until the line ends or final flush | CAP-PY | CODING |
| R-3 | DESIGN | plan | SI-5 | Only live loopback URLs | pid check + regex | avoid stale/foreign URLs | CAP-PY | CODING |

Timing rule (AR-001): the approximately one-second announcement target (SB-1) applies only while driver output is at a line boundary (`writer.at_start`). While a driver line is incomplete, announcements are deferred without inserting a newline until that line ends or the final flush (after the forced newline); that interval is excluded from the target. Test oracle: a fake driver writes the URL file, then a partial line with no newline and waits several seconds; the Preview line must not appear mid-line, and must appear right after the line ends (or at final flush).

CAP-PY = python3 and the repo test runners, feasibility: `scripts/run-python-tests.sh` exists (inspected). No live-authentication prerequisites; LIVE_VERIFICATION check is manual strategy in 18 only.

## Implementation sequence
1. Add watcher helpers and loop/final-flush hooks (Decision D-1: poll files, not start servers; D-2: poll interval 0.5 s) — Owns: `scripts/lib/uncle_headless.py`
2. Add test suite `headless-preview-test.py` covering AC-1..AC-5 (independent of step 1 file; uses documented line format) — Owns: `scripts/tests/headless-preview-test.py`
3. Document lines in noui doc (independent) — Owns: `docs/noui.md`
4. Run verification commands and reconcile — Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md` — Depends on: 1, 2, 3

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/uncle_headless.py` | Watcher + hooks in `_stream` | Surface preview/app | Medium: select loop, line framing | headless-run, headless-preview |
| `scripts/tests/headless-preview-test.py` | New suite | Prove ACs | Low | itself |
| `docs/noui.md` | Document lines | AC-7 | Low | headless-preview |
| `.uncle/docs/IMPLEMENTATION_NOTES.md` | Deviations | Workflow | None | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 (timing qualified): the Preview line appears within about 1 s of the URL file becoming valid, measured at a driver line boundary. While a driver line is incomplete, the announcement is deferred without inserting a newline until the next line boundary or final flush; the ~1 s target excludes that deferral interval. Tests include a driver that holds a partial line open and assert deferral with no inserted newline. | SB-1 | SI-3 | uncle_headless.py | headless-preview (boundary case: Preview within ~1 s; partial-line case: deferred until line end or final flush) | build shows Preview line |
| AC-2 (timing qualified): announcements never split a driver line; they are deferred while a partial line is pending, and the ~1 s target excludes that interval. | SB-2 | SI-3 | uncle_headless.py | headless-preview | n/a |
| AC-3: App-server URLs are announced once each (deduplicated via the `emitted_app_urls` set, app-server processed before preview-vite), and the launch status line is rendered as `App: launch ...` per the launch-status rendering rule in the traceability notes, printed once at the end. | SB-3, SB-4 | SI-4 | uncle_headless.py | headless-preview: simultaneous app-server and preview-vite with different URLs each announced once across repeated scans; A->B->A recurrence emits no repeat; final launch-status line rendered per launch kind | App line at end |
| AC-4: Watcher state-file reads are bounded and non-blocking: open nonblockingly, reject non-regular files (e.g. FIFOs), read at most 2049 bytes per pid or URL file, and silently reject content over 2048 bytes; any failure yields no line and never aborts streaming. | SB-5 | SI-5, SI-4 | uncle_headless.py | headless-preview (oversized file, FIFO, and non-regular file cases produce no line and streaming continues) | n/a |
| AC-5 (timing qualified): with a partial driver line open, no announcement is emitted until the line completes or final flush, where a forced newline precedes it; the ~1 s target does not apply during the partial interval. | SB-1 | SI-2, SI-3 | uncle_headless.py | headless-preview: URL file with ESC/control characters in path is rejected; state file URL or launch metadata containing ESC/control characters is emitted escape-free; output contains no ESC byte | n/a |
| AC-6 | SB-6, SB-7 | SI-1, SI-2 | uncle_headless.py | headless-run, launcher-noui | exit code check |
| AC-7 | SB-8 | none | docs/noui.md | headless-preview | n/a |

AC-3 dedup rule (AR-010): the watcher processes app-server before preview-vite and keeps `emitted_app_urls` as a set of every app URL already announced this run; state in section 7 is therefore `seen_preview` (last preview URL), `emitted_app_urls` (set) and `launch_printed`.

Launch-status rendering (SB-4, `App: launch ...`): command launch prints the argument array as JSON (e.g. `App: launch command ["python3","app.py"]`); static webpage prints the path (`App: launch page index.html`); webpage with a command prints the argument array as JSON followed by the URL (`App: launch page ["npm","run","start"] http://127.0.0.1:3000`); kind none prints `App: launch none`. All launch text passes through the same sanitization and redaction as other announcements.

## Verification commands
```
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- headless-preview
```
Protected verification paths: `scripts/tests/headless-run-test.py`, `scripts/tests/launcher-noui-test.sh`, `scripts/tests/critical-suites.txt`, `scripts/run-python-tests.sh`, `scripts/run-shell-tests.sh`.

## 21. Scope cuts under time pressure

SB-3 (App URL announcements) and SB-4 (final launch-status line) are mandatory for this change: they are required by AC-3, and removing either requires an explicitly approved revision to AC-3 before implementation can be considered complete. Under time pressure, cut only non-AC items first (e.g. docs polish beyond AC-7 minimum wording); keep SB-1 Preview line, SB-3 and SB-4. The per-run set of emitted app URLs (scan app-server then preview-vite) is part of SB-3 and must not be dropped. The ~1 s timing target (SB-1) is a line-boundary target only and may never be met by breaking line framing (SI-3).

## 22. Risks and unresolved questions
- Change-request runs have no driver preview, so show nothing (accepted, A3).
- Preview server writes URL only when `WORKFLOW_PREVIEW_OPEN_BROWSER` is not 0; accepted.
- No blocking decisions.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The ~1 s target and deferral during a partial driver line genuinely conflict; qualifying the deadline to line boundaries resolves it without breaking framing. | R-2, AC-1, AC-2, AC-5 and a new s16 note qualify the ~1 s deadline to driver line boundaries; defer to next boundary or final flush. |
| AR-002 | Accepted | A single remembered app URL cannot deduplicate across two live sources; a set of emitted app URLs can. | AC-3 traceability row and s21 now require scan order app-server then preview-vite and a per-run set of emitted app URLs. |
| AR-003 | Accepted | Webpage launches with command and url (no path) had no defined rendering; an explicit per-kind rendering rule removes the ambiguity. | Added launch-line rendering rule block to s19 and set AC-3 requirement text to match it. |
| AR-004 | Accepted | AC-3 requires both app URL announcements and the launch-status line, so the plan's scope cuts must not allow removing SB-3 or SB-4. | Rewrote s21.1 so SB-3/SB-4 are mandatory and cuttable only via approved AC-3 revision; AC-3 requirement notes this. |
| AR-005 | Accepted | The URL regex /\S* admits ESC and other controls, and redaction alone does not strip escapes, so SI-2/AC-5 could regress. | Edit s6.1 data flow, R-1 restriction and AC-5 row to require control-character rejection and escape filtering plus redaction of all announcement text, and add a restriction row R-4. |
| AR-006 | Accepted | Real conflict: the ~1 s target (SB-1) cannot hold while a driver line is partial and SI-3 forbids splitting it, so the target must exclude that interval. | R-2 mechanism and AC-1 requirement state: defer without inserting a newline while a driver line is incomplete; the ~1 s target excludes that interval. |
| AR-007 | Accepted | The URL regex permits control characters and the data flow names only redaction, so escape-free output (SI-2, AC-5) is not guaranteed. | Data flow s6.1 adds a sanitize step; R-1 mechanism and AC-5 require control-character rejection and sanitization of every announcement. |
| AR-008 | Accepted | State-file reads were unbounded and could block on a FIFO or exhaust memory, contradicting the spec's oversized-file rejection and SI-4. | Traceability AC-4 now requires nonblocking, regular-file-only reads of at most 2049 bytes, silently rejecting content over 2048 bytes. |
| AR-009 | Accepted | The ~1 s target conflicts with deferral during a partial driver line; qualifying the deadline gives tests a consistent oracle. | Restrictions (s16) states the 1 s target applies only at a line boundary; R-2 rationale and AC-1 tests add a partial-line case. |
| AR-010 | Accepted | A single remembered app URL cannot deduplicate across two live sources, so a set of emitted app URLs is required. | AC-3 requirement and tests updated; s19 gains a note on app-server-before-preview-vite order and the emitted-URL set. |
