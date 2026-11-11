# Verification report

## Findings

### MC-101

- **Action:** I did not run a full agent-driven `uncle --noui` build. I ran a narrow live probe in a throwaway app project: family=app, with a root index.html. Hosted flags UNCLE_HOSTED and UNCLE_PREVIEW_MODE were unset, preview was enabled, and UNCLE_NOUI_PREVIEW_SECONDS=120. I called HeadlessPreview.finish() from scripts/lib/headless_preview.py, which starts the real preview_server.py detached. I then called uncle_headless._scan_announcements(), which produces the announced Local preview line, and fetched the announced URL over HTTP. I did not open it in a real browser; WORKFLOW_PREVIEW_OPEN_BROWSER was set so no tab opened. Afterwards I killed the server.
- **Expected result:** The loopback address is announced as `Local preview: http://127.0.0.1:P/`, and the browser displays the application. Any final server lifetime message starts with `Local preview:` and includes its duration and stop instruction.
- **Actual result:** The final lifetime message matches: `Local preview: the server (pid 98724) keeps running for 2 minutes; stop it earlier with: kill 98724`. The server served the application's HTML (`MC101 hello`) over HTTP, plus the reload script. The announced address does NOT match the expected form: it was `Local preview: http://127.0.0.1:53137/index.html`, with an `/index.html` path suffix rather than a bare `/`. My check that the line fully matches `Local preview: http://127.0.0.1:\d+/` returned False. The loopback prefix is correct and the page is served, but the announced URL's exact form deviates from the expected text.
- **Defects:** Announced local preview URL includes the `/index.html` suffix instead of the bare `http://127.0.0.1:P/` the check expects. Not yet logged in DEFECTS.md (workers may not edit it); the driver or reconciler should record it.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | FAIL | Probe stdout: `finish: ['Local preview: the server (pid 98724) keeps running for 2 minutes; stop it earlier with: kill 98724\n']`, `scan: ['Local preview: http://127.0.0.1:53137/index.html\n']`, `re match False`. urlopen of the announced URL returned `<html><body><h1>MC101 hello</h1></body></html>` plus the preview reload script. The announcement comes from the preview-server.url file via scripts/lib/uncle_headless.py (_scan_announcements, around line 223). Limits: this was a library-level probe, not a full build, and no real browser rendering was observed. |
