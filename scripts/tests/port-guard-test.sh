#!/usr/bin/env bash
# port_guard.py stops this project's leftover servers on ports the checks bind,
# and only names (never kills) a listener that belongs to something else.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
GUARD="$HERE/../lib/port_guard.py"
TMP="$(mktemp -d)"
PIDS=()
cleanup() { for p in ${PIDS[@]+"${PIDS[@]}"}; do kill "$p" 2>/dev/null; done; rm -rf "$TMP"; }
trap cleanup EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); if [[ "$2" == "$3" ]]; then :; else FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; fi; }
free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }
up() { local i; for i in $(seq 50); do lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 && return 0; sleep .1; done; return 1; }

mkdir -p "$TMP/project" "$TMP/elsewhere" "$HOME/.port-guard-test-$$"
ELSE="$HOME/.port-guard-test-$$"
trap 'cleanup; rm -rf "$ELSE"' EXIT
A="$(free_port)"; B="$(free_port)"
(cd "$TMP/project" && exec python3 -m http.server "$A" --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
(cd "$ELSE" && exec python3 -m http.server "$B" --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
up "$A"; up "$B"
printf 'npx playwright test\n' > "$TMP/cmds"
printf 'export default { webServer: { url: "http://127.0.0.1:%s" }, use: { baseURL: "http://localhost:%s" } }\n' "$A" "$B" > "$TMP/project/playwright.config.js"

out="$(python3 -B "$GUARD" "$TMP/cmds" "$TMP/project")"
sleep .3
check "a leftover server inside the project is stopped" "free" "$(lsof -nP -iTCP:$A -sTCP:LISTEN >/dev/null 2>&1 && echo busy || echo free)"
check "the stop is reported" "yes" "$([[ "$out" == *"port $A: stopped leftover"* ]] && echo yes || echo no)"
check "a server outside the project is left running" "busy" "$(lsof -nP -iTCP:$B -sTCP:LISTEN >/dev/null 2>&1 && echo busy || echo free)"
check "a foreign holder is named" "yes" "$([[ "$out" == *"port $B: held by pid"*"not stopped"* ]] && echo yes || echo no)"

S="$(free_port)"; mkdir -p /tmp/port-guard-scratch-$$
(cd /tmp/port-guard-scratch-$$ && exec python3 -m http.server "$S" --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
up "$S"
printf 'x http://127.0.0.1:%s\n' "$S" >> "$TMP/cmds"
python3 -B "$GUARD" "$TMP/cmds" "$TMP/project" >/dev/null; sleep .3
check "a server run from a temp copy is stopped" "free" "$(lsof -nP -iTCP:$S -sTCP:LISTEN >/dev/null 2>&1 && echo busy || echo free)"
rm -rf /tmp/port-guard-scratch-$$
check "a clean tree prints nothing" "" "$(python3 -B "$GUARD" "$TMP/cmds" "$TMP/project" | grep "port $A")"

# A background verification run executes from an isolated copy of the
# project, not the operator's own checkout -- so a leftover server still
# running from that original checkout (an earlier attended run, a hung
# webServer, `npm run dev` the operator left open) has a cwd under the
# original root, not the copy. Passing that original root as a third
# argument must make it recognized as this project's own leftover too.
# Neither side of this scenario may live under a directory scratch()
# already treats as disposable (mktemp's $TMP resolves under
# /var/folders on macOS) -- that would stop the leftover for an
# unrelated reason and never exercise the original-root argument at
# all, the same way the real project and its isolated copy are both
# ordinary, non-tmp directories.
ORIG="$HOME/.port-guard-test-orig-$$"
COPY="$HOME/.port-guard-test-copy-$$"
mkdir -p "$ORIG" "$COPY"
trap 'cleanup; rm -rf "$ELSE" "$ORIG" "$COPY"' EXIT
C="$(free_port)"
(cd "$ORIG" && exec python3 -m http.server "$C" --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
up "$C"
printf 'npx playwright test\n' > "$TMP/copy-cmds"
printf 'export default { webServer: { url: "http://127.0.0.1:%s" } }\n' "$C" > "$COPY/playwright.config.js"

out="$(python3 -B "$GUARD" "$TMP/copy-cmds" "$COPY" "$ORIG")"
sleep .3
check "a leftover in the original (non-isolated) checkout is recognized with the original root" "yes" \
    "$([[ "$out" == *"port $C: stopped leftover"* ]] && echo yes || echo no)"
check "...and actually stopped" "free" "$(lsof -nP -iTCP:$C -sTCP:LISTEN >/dev/null 2>&1 && echo busy || echo free)"

D="$(free_port)"
(cd "$ORIG" && exec python3 -m http.server "$D" --bind 127.0.0.1 >/dev/null 2>&1) & PIDS+=($!)
up "$D"
printf 'npx playwright test\n' > "$TMP/copy-cmds2"
printf 'export default { webServer: { url: "http://127.0.0.1:%s" } }\n' "$D" > "$COPY/playwright.config.js"
out="$(python3 -B "$GUARD" "$TMP/copy-cmds2" "$COPY")"
check "without the original root, the same leftover is only named, not stopped" "yes" \
    "$([[ "$out" == *"port $D: held by pid"*"not stopped"* ]] && echo yes || echo no)"
check "...and is left running" "busy" "$(lsof -nP -iTCP:$D -sTCP:LISTEN >/dev/null 2>&1 && echo busy || echo free)"

if [[ "$FAILED" -ne 0 ]]; then echo "port-guard-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "port-guard-test.sh: $COUNT checks passed"
