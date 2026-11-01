#!/usr/bin/env bash
# The suite runners (baseline, green check) execute inside a live run, beside the planning stage. A suite that reaches a browser opener must
# not open a tab on the operator's machine.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

project="$TMP/p"; mkdir -p "$project/scripts/tests" "$TMP/bin"
# An `open` and an `xdg-open` that would be the real thing: if either runs, a tab would have opened.
for opener in open xdg-open; do
    printf '#!/bin/sh\necho "$0 $*" >> "%s/opened"\n' "$TMP" > "$TMP/bin/$opener"
    chmod +x "$TMP/bin/$opener"
done
# A shell suite and a Python suite that do what the preview does: ask for a page, and note what the environment says.
cat > "$project/scripts/tests/env-test.sh" <<SH
#!/usr/bin/env bash
echo "open_browser=\${WORKFLOW_PREVIEW_OPEN_BROWSER-unset}" > "$TMP/shell-env"
python3 -c 'import webbrowser; print(webbrowser.open("http://127.0.0.1:9/"))' > "$TMP/shell-open"
SH
cat > "$project/scripts/tests/env-test.py" <<PY
import os, webbrowser
open("$TMP/python-env", "w").write("open_browser=%s\n" % os.environ.get("WORKFLOW_PREVIEW_OPEN_BROWSER", "unset"))
open("$TMP/python-open", "w").write(str(webbrowser.open("http://127.0.0.1:9/")))
PY

# What a launching run carries: its own opt-in to opening, and a real browser.
export PATH="$TMP/bin:$PATH" WORKFLOW_PREVIEW_OPEN_BROWSER=1 BROWSER="$TMP/bin/open"

bash "$ROOT/scripts/run-shell-tests.sh" --project-root "$project" > "$TMP/shell.out" 2>&1
check "the shell suite ran" test -s "$TMP/shell-env"
check "shell suite: preview opening is switched off" grep -qx 'open_browser=0' "$TMP/shell-env"
check "shell suite: asking for a page reports success without a real opener" grep -qx 'True' "$TMP/shell-open"

bash "$ROOT/scripts/run-python-tests.sh" --project-root "$project" > "$TMP/python.out" 2>&1
check "the python suite ran" test -s "$TMP/python-env"
check "python suite: preview opening is switched off" grep -qx 'open_browser=0' "$TMP/python-env"
check "python suite: asking for a page reports success without a real opener" grep -qx 'True' "$TMP/python-open"

check "no browser was opened by either runner" test ! -e "$TMP/opened"
check "the change driver switches preview opening off for everything it starts" grep -q '^export WORKFLOW_PREVIEW_OPEN_BROWSER=0$' "$ROOT/scripts/change-workflow.sh"
[[ $fails == 0 ]] && echo "suites-never-open-a-browser-test.sh: ok"
exit $fails
