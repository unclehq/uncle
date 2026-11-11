# Change Request

Issue 253

Seeded from [unclehq/uncle#253](https://github.com/unclehq/uncle/issues/253).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

--noui prints its own Preview: lines with 127.0.0.1 links in hosted builds, and the chat rules tell the agent to relay them

## Motivation

## Summary

Since #246 (PR #247) and `e3b0967`, both merged on 2026-11-11, a `--noui` build prints its own `Preview:` lines. One holds a local `http://127.0.0.1:<port>/` address; another reads "the server (pid N) keeps running …; stop it earlier with: kill N". Neither checks hosted mode.

In a hosted build, `Preview:` is the line the chat agent relays to the person. `skills/uncle-build/SKILL.md` rule 1 says to relay every `Preview:` line, and rule 5 allows any `http` link. So if a hosted `--noui` build's output reaches the chat, the person gets a `127.0.0.1` link that can't open on their computer, next to (or instead of) the real signed link. The same check also starts a second preview server, besides the one host mode already left running.

## How it happens

1. Hosted mode sets `UNCLE_PREVIEW_MODE=host` (`scripts/lib/stage-config.sh:47-51`). The finished app is served by `host_preview.py serve`, and the build script asks the host for a signed link to that port (#206, #207).
2. With `--noui`, `uncle_headless.py` polls the driver's state files and turns the preview server's URL into `Preview: <url>` (`scripts/lib/uncle_headless.py:204-224`). The only URLs it accepts are loopback ones: `_URL_RE` is `^https?://(127\.0\.0\.1|localhost|\[::1\])…` (`:144`).
3. When the build finishes, `HeadlessPreview.finish()` (`scripts/lib/headless_preview.py:175-190`) starts another preview server, unless the driver's own `preview-server` is still alive. That check doesn't look at `.uncle/preview.json`, where host mode records its app. It then prints `Preview: the server (pid N) keeps running for M minutes; stop it earlier with: kill N`.
4. `enabled()` (`scripts/lib/headless_preview.py:39-42`) turns this off only through `UNCLE_NOUI_PREVIEW` or `WORKFLOW_PREVIEW_OPEN_BROWSER`, not in hosted mode. `host_preview_hook.sh` sets `WORKFLOW_PREVIEW_OPEN_BROWSER=0` only inside its own subshell (`scripts/lib/host_preview_hook.sh:12-15`), so the `--noui` runner never sees it.
5. Chat rules: "When the output has a Preview: line, copy its URL … If there are several Preview: lines, relay all of them" (`skills/uncle-build/SKILL.md:12`). "Relay only http or https links" (`:16`).

## Code paths (main `b27e23c`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/uncle_headless.py:144` | `_URL_RE` accepts only `127.0.0.1`, `localhost` and `[::1]` URLs. | `140a309` 2026-11-11 (#246, PR #247) |
| `scripts/lib/uncle_headless.py:204-224` (`_scan_announcements`) | Prints `Preview: <loopback url>` for the preview server and `App: <url>` for app servers. | `140a309` 2026-11-11 (#246, PR #247) |
| `scripts/lib/uncle_headless.py:490-501` | After a completed build, runs `preview.finish()` and prints the final `Preview:`/`App:` lines. | `e3b0967` 2026-11-11 (`:490-494`), `140a309` 2026-11-11 (`:495-501`) |
| `scripts/lib/headless_preview.py:39-42` (`enabled`) | Off switches: `UNCLE_NOUI_PREVIEW`, `WORKFLOW_PREVIEW_OPEN_BROWSER`. No hosted-mode check. | `e3b0967` 2026-11-11 |
| `scripts/lib/headless_preview.py:175-190` (`finish`) | Starts a second preview server and prints `Preview: the server (pid N) … kill N`. | `e3b0967` 2026-11-11 |
| `scripts/lib/host_preview_hook.sh:12-15` | Sets `WORKFLOW_PREVIEW_OPEN_BROWSER=0` only in a subshell around `host_preview.py serve`. | `bd3cde0` 2026-11-09 (#206) |
| `skills/uncle-build/SKILL.md:12`, `:16` | Relay every `Preview:` line; allow any http/https link. | `274a636` 2026-11-09 (#210, PR #220) |

## Fix

1. **In hosted mode, `--noui` prints no `Preview:` lines and starts no preview server.** Have `headless_preview.enabled()` return False, and `_scan_announcements` skip `Preview:`, when `host_preview.is_host_mode()` is true (or `UNCLE_HOSTED=1`). Host mode already serves the finished app. In hosted runs, `Preview:` is reserved for the host's signed link.
2. **Say local addresses plainly.** Outside hosted mode, label the local address `Local preview:` rather than `Preview:`, so the two meanings never share a prefix.
3. **Chat rule.** In `skills/uncle-build/SKILL.md` rule 5, relay only `https` links and never a `localhost`, `127.0.0.1` or `[::1]` address. If the only `Preview:` lines are local, say no link was provided.

## Tests

- `uncle_headless` with `UNCLE_PREVIEW_MODE=host` and a live `preview-server` state file: no `Preview:` line is printed, and `HeadlessPreview.finish()` starts nothing.
- Without host mode: the local address prints as `Local preview: http://127.0.0.1:…/`, unchanged otherwise.
- `scripts/tests/chat-skill-test.py`: a pattern requiring the rule against local addresses, and a bad variant that fails without it.

## Checks after the fix

1. A hosted `--noui` build of a small web app prints exactly one `Preview:` line, the host's `https://` signed link, and the chat relays only that one.
2. A local `--noui` build still shows its local preview, as `Local preview:`.

## Related

#206, #207, #210, #235, #246, #251; PR #247.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
