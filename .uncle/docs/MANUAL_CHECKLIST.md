# Manual checklist

### MC-101
- Exclusive resources: none
- Depends on: none
- Exact action: Observe a local application build using `--noui` with both hosted flags unset and preview enabled, including the live preview and finished-application handoff. Open the announced local URL in the browser.
- Expected result: The loopback address is announced as `Local preview: http://127.0.0.1:P/`, and the browser displays the application. Any final server lifetime message starts with `Local preview:` and includes its duration and stop instruction.
- Actual result: 
- Status: NOT RUN
