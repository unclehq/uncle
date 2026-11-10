#!/usr/bin/env bash
# The defect-injection runner's unmutated controls must pass on a project that (1) lists vitest but writes its specs for
# node:test, and (2) declares two ports (dev and preview). Both made every control fail on a real build.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$HERE/../lib/mutation_runner.mjs"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else FAILED=1; echo "FAIL $1: expected [$2] got [$3]"; fi; }
command -v node >/dev/null || { echo "skip: node not installed"; exit 0; }

P="$TMP/project"; mkdir -p "$P/src" "$P/tests/mutations" "$P/node_modules"
cat > "$P/package.json" <<'JSON'
{ "name": "fixture", "type": "module",
  "scripts": { "dev": "vite --port 5173 --strictPort", "preview": "vite preview --port 4173 --strictPort" },
  "devDependencies": { "vitest": "latest" } }
JSON
echo 'export const add = (a, b) => a + b;' > "$P/src/math.js"
cat > "$P/tests/math.test.js" <<'JS'
import test from 'node:test';
import assert from 'node:assert/strict';
import { add } from '../src/math.js';
test('add', () => assert.equal(add(2, 3), 5));
JS
# A second spec whose command must see both ports rewritten in its own copy of package.json.
cat > "$P/tests/ports.check.js" <<'JS'
import fs from 'node:fs';
const text = fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8');
// The ports are built at run time: the runner rewrites literals under tests/, this file's own included.
const ports = ['41' + '73', '51' + '73'];
process.exit(ports.some((p) => new RegExp('\\b' + p + '\\b').test(text)) ? 1 : 0);
JS
cat > "$P/tests/mutations/list.mjs" <<'JS'
export default [
  { id: 'DI-1', file: 'src/math.js', find: 'a + b', replace: 'a - b', spec: 'tests/math.test.js' },
  { id: 'DI-2', file: 'src/math.js', find: 'a + b', replace: 'a * b', spec: 'tests/math.test.js',
    command: 'node tests/ports.check.js && node --test tests/math.test.js' },
];
JS
out="$(cd "$P" && node "$RUNNER" 2>&1)"; status=$?
check "the runner exits 0 when every control passes and every defect is caught" 0 "$status"
check "a node:test spec is run with node --test, not vitest" yes "$([[ "$out" == *"CONTROL OK"*"node --test"* && "$out" != *"CONTROL FAIL"* ]] && echo yes || echo no)"
check "both declared ports are rewritten in the copy" yes "$([[ "$out" == *"CAUGHT"*"DI-2"* ]] && echo yes || echo no)"
check "no control failed" 0 "$(printf '%s' "$out" | grep -c 'CONTROL FAIL')"
exit "$FAILED"
