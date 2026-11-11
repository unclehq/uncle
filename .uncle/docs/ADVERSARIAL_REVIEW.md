## AR-001: The announcement deadline conflicts with deferral during partial driver lines.

- Severity: HIGH
- References: CHANGE_SPEC.json SB-1 requires output within about 1 s while the build runs; SI-3 and CHANGE_PLAN.json §1 prohibit emission during a partial line until final flush. A driver that leaves a partial line open for several seconds makes both requirements impossible to satisfy.
- Failure: The announcement deadline conflicts with deferral during partial driver lines. Add: "The approximately one-second deadline applies only at a driver line boundary; while a partial line is pending, defer announcements until the next boundary or final flush."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: A single remembered app URL cannot enforce distinct-URL deduplication across two active sources.

- Severity: MEDIUM
- References: CHANGE_SPEC.json SB-3 requires an App line once per distinct URL from either source; CHANGE_PLAN.json §7 permits only seen = {preview: url, app: url} and launch_printed. Two live sources with different URLs can repeatedly replace the single app value and cause duplicate announcements.
- Failure: A single remembered app URL cannot enforce distinct-URL deduplication across two active sources. Add: "Scan app-server then preview-vite, announce each valid app URL once per run, and retain the set of emitted app URLs independently of the last preview URL."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Final launch output is unspecified for a webpage launch containing both a command and URL.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 specifies App: launch <command|page|none>, and CHANGE_SPEC.json SB-4 specifies command, page path, or none. The supplied launch-metadata contract also allows webpage launches with command and url but no path; neither artifact selects their output or defines unambiguous argument rendering.
- Failure: Final launch output is unspecified for a webpage launch containing both a command and URL. Add: "For webpage launches with a command, print the argument array as JSON followed by the URL; for static webpages print the path, for command launches print the argument array as JSON, and for none print none."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The scope-cut instructions permit removing required acceptance behavior.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §21 says to cut SB-4 first and then SB-3 under time pressure. CHANGE_SPEC.json AC-3 requires both live app URL announcements and a final launch-status line, so following the plan's scope cuts would violate the approved acceptance criterion.
- Failure: The scope-cut instructions permit removing required acceptance behavior. Add: "SB-3 and SB-4 remain mandatory for this change; removing either requires an explicitly approved revision to AC-3 before implementation can be considered complete."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The announcement path can regress escape filtering: the URL regex accepts ESC in paths, and redaction does not establish

- Severity: HIGH
- References: CHANGE_PLAN.json §6 specifies only redact before _Writer.emit; §12 permits /\S*, which accepts ESC characters. CHANGE_SPEC.json SI-2 and AC-5 require escape-free output; untrusted state or launch text could otherwise introduce terminal controls.
- Failure: The announcement path can regress escape filtering: the URL regex accepts ESC in paths, and redaction does not establish escape removal. Add: "Reject control characters in URLs and pass all announcement text, including launch metadata, through escape filtering and redaction before emission."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: A driver that leaves a partial line open makes timely preview output incompatible with preserving line framing.

- Severity: MEDIUM
- References: CHANGE_SPEC.json SB-1 requires output within about one second while the build runs, whereas SI-3 and CHANGE_PLAN.json §1 defer emission until writer.at_start, allowing a forced newline only at final flush. A partial line lasting until exit leaves implementers choosing between the timing promise and existing output framing.
- Failure: A driver that leaves a partial line open makes timely preview output incompatible with preserving line framing. Add: "While a driver line is incomplete, defer announcements without inserting a newline until that line ends or final flush; the one-second announcement target excludes this interval."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Announcement sanitization is unspecified: the URL regex accepts terminal control characters, while the output path menti

- Severity: MEDIUM
- References: CHANGE_PLAN.json §6 specifies poll -> redact -> _Writer.emit; §12 permits /\S*, which can contain ESC and other non-whitespace controls. CHANGE_SPEC.json AC-5 and SI-2 prohibit escape sequences, so independently implemented watcher output could violate terminal-output safety.
- Failure: Announcement sanitization is unspecified: the URL regex accepts terminal control characters, while the output path mentions only redaction. Add: "Sanitize every URL and launch-status announcement to one line, removing terminal escape sequences and control characters before redaction and emission."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Malformed state files can block streaming or exhaust memory unless reads are bounded before validation.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 reads state files inside the select loop; §12 specifies exception handling and a URL size validator but no bounded or nonblocking read. CHANGE_SPEC.json §8 rejects oversized state files and SI-4 forbids watcher failures from aborting streaming; reading a FIFO or an arbitrarily large file before validation defeats those guarantees.
- Failure: Malformed state files can block streaming or exhaust memory unless reads are bounded before validation. Add: "Read state files nonblockingly, reject nonregular files, and read at most 2049 bytes per pid or URL file, silently rejecting content over 2048 bytes."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The announcement deadline conflicts with indefinite deferral during partial driver lines, leaving timing tests without a

- Severity: MEDIUM
- References: CHANGE_SPEC.json SB-1 requires output within about one second while the build runs; SI-3 and CHANGE_PLAN.json §1 defer announcements during partial lines until a boundary or final flush. A driver that writes a partial line and then waits several seconds cannot satisfy both; explicitly qualify the deadline and test this case.
- Failure: The announcement deadline conflicts with indefinite deferral during partial driver lines, leaving timing tests without a consistent oracle. Add: "The one-second announcement target applies only at a driver line boundary; otherwise defer until the next boundary or final flush."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Two app URL sources share one remembered URL, but simultaneous sources and URL recurrence have no defined test oracle.

- Severity: MEDIUM
- References: CHANGE_SPEC.json SB-3 requires an App line once per distinct URL from either source, while CHANGE_PLAN.json §7 allows only seen = {preview: url, app: url} and launch_printed. With two different live app URLs, a last-value implementation can reannounce both on every scan; replace the app scalar with a set and test simultaneous sources and A→B→A recurrence.
- Failure: Two app URL sources share one remembered URL, but simultaneous sources and URL recurrence have no defined test oracle. Add: "Process app-server before preview-vite, emit each distinct valid app URL once per run, and retain a set of emitted app URLs."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
