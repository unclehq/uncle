#!/usr/bin/env node
// Defect-injection runner, supplied by the driver (scripts/lib/mutation_runner.mjs) so that no model has to write it.
//
// Run from the project root.  Reads the list of defects, injects each one into its own scratch copy of the project, runs the
// spec that must reject it, and reports which defects the tests caught.  A plan names this file as one implementation step; the
// driver copies this script to that path instead of asking a model to write 190 lines blind against a list file another step is
// writing at the same moment (noinit: 53 s, then a runner that did not run).
//
//   node <this file> [list-module] [--only DI-3] [--keep]
//
// The list is a module next to this file (list|mutations|injections|defects .mjs|.js) or the path given.  Its default export
// (or `list`, `mutations`, `injections`, `defects`, or the first array it exports) is an array of
//   { id, file, find, replace, spec, expected?, command? }
// with the usual aliases accepted (name, path/target, search/pattern/from, replacement/to, specs/test/tests).  `find` must occur
// exactly once in `file`.  `spec` is a path or an array of paths; the test command is derived from the project (Playwright for an
// e2e spec, after a build; else Vitest, Jest or `node --test`) unless the entry gives `command`.  `expected` is a substring of the
// failing test's name; a mutant counts as caught when its run fails, and with MUTATION_STRICT=1 only when `expected` appears too.
//
// Every mutant gets its own copy (node_modules is linked, not copied) and its own port: the port found in the project's
// Playwright, Vite and package.json files is replaced by a distinct one in the copy.  An unmutated control run per command must
// pass first, or no result is trustworthy.  Exit 0 when every defect was caught and every control passed, else 1.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = process.cwd();
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'uncle-mutation-'));     // outside the project: a directory cannot be copied into itself
const SKIP = new Set(['node_modules', '.git', '.uncle', '.mutation-scratch', '.test-out', 'coverage', 'test-results', 'playwright-report']);
const args = process.argv.slice(2);
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const keep = args.includes('--keep') || process.env.MUTATION_KEEP === '1';
const explicit = args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--only');
const strict = process.env.MUTATION_STRICT === '1';
const timeoutMs = Number(process.env.MUTATION_TIMEOUT_MS || 180000);
const jobs = Math.max(1, Number(process.env.MUTATION_JOBS || Math.min(8, os.cpus().length)));

const exists = (p) => fs.existsSync(p);
const read = (p) => fs.readFileSync(p, 'utf8');
const first = (...values) => values.find((v) => v !== undefined && v !== null);

async function loadList() {
  const names = ['list', 'mutations', 'injections', 'defects'];
  const dirs = [HERE, path.join(ROOT, 'tests', 'mutations'), path.join(ROOT, 'tests'), path.join(ROOT, 'scripts'), path.join(ROOT, 'tools')];
  const candidates = explicit ? [path.resolve(ROOT, explicit)]
    : dirs.flatMap((d) => names.flatMap((n) => [path.join(d, `${n}.mjs`), path.join(d, `${n}.js`)]));
  const file = candidates.find((c) => exists(c) && path.resolve(c) !== fileURLToPath(import.meta.url));
  if (!file) throw new Error(`no defect list found next to the runner (looked for ${names.join('|')}.mjs|.js); pass its path`);
  const mod = await import(pathToFileURL(file).href);
  const found = first(mod.default, mod.list, mod.mutations, mod.injections, mod.defects,
    Object.values(mod).find((v) => Array.isArray(v)));
  if (!Array.isArray(found) || found.length === 0) throw new Error(`${path.relative(ROOT, file)} does not export a non-empty array of defects`);
  return { file, entries: found.map(normalize) };
}

function normalize(e, i) {
  const specs = first(e.specs, e.spec, e.tests, e.test);
  return {
    id: String(first(e.id, e.name, `DI-${i + 1}`)),
    file: first(e.file, e.path, e.target),
    find: first(e.find, e.search, e.pattern, e.from),
    replace: String(first(e.replace, e.replacement, e.to, e.with, '')),
    specs: specs === undefined ? [] : (Array.isArray(specs) ? specs : [specs]).map(String),
    expected: first(e.expected, e.expectedTest, e.title, e.failsIn),
    command: e.command,
  };
}

function copyProject(dest) {
  fs.rmSync(dest, { recursive: true, force: true });
  fs.cpSync(ROOT, dest, { recursive: true, filter: (src) => !SKIP.has(path.basename(src)) || src === ROOT });
  if (exists(path.join(ROOT, 'node_modules'))) fs.symlinkSync(path.join(ROOT, 'node_modules'), path.join(dest, 'node_modules'), 'dir');
}

const CONFIGS = ['playwright.config.js', 'playwright.config.mjs', 'playwright.config.cjs', 'playwright.config.ts',
  'vite.config.js', 'vite.config.mjs', 'vite.config.ts', 'package.json'];

function basePort() {
  const counts = new Map();
  for (const name of CONFIGS) {
    const file = path.join(ROOT, name);
    if (!exists(file)) continue;
    for (const m of read(file).matchAll(/(?:--port[ =]|port['"]?\s*[:=]\s*|(?:localhost|127\.0\.0\.1|0\.0\.0\.0):)(\d{4,5})\b/g)) {
      const port = Number(m[1]);
      if (port >= 1024 && port <= 65535) counts.set(port, (counts.get(port) || 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

function rewritePort(dir, from, to) {
  if (!from) return;
  const pattern = new RegExp(`\\b${from}\\b`, 'g');
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (SKIP.has(entry.name) || entry.isSymbolicLink()) continue;
      const file = path.join(current, entry.name);
      if (entry.isDirectory()) { if (entry.name !== 'src') visit(file); continue; }
      if (!/\.(c|m)?(j|t)sx?$|\.json$|\.html$/.test(entry.name) || fs.statSync(file).size > 1e6) continue;
      const rel = path.relative(dir, file);
      if (!CONFIGS.includes(rel) && !rel.startsWith(`tests${path.sep}`) && !rel.startsWith(`e2e${path.sep}`)) continue;
      const text = read(file);
      if (pattern.test(text)) { pattern.lastIndex = 0; fs.writeFileSync(file, text.replace(pattern, String(to))); }
    }
  };
  visit(dir);
}

function commandFor(entry) {
  if (entry.command) return entry.command;
  if (entry.specs.length === 0) throw new Error('no spec and no command');
  const list = entry.specs.join(' ');
  const pkg = exists(path.join(ROOT, 'package.json')) ? JSON.parse(read(path.join(ROOT, 'package.json'))) : {};
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  const e2e = entry.specs.some((s) => /\.spec\.|[\\/]e2e[\\/]/.test(s)) && CONFIGS.slice(0, 4).some((c) => exists(path.join(ROOT, c)));
  if (e2e) return `${pkg.scripts?.build ? 'npm run build && ' : ''}npx playwright test ${list}`;
  if (deps.vitest) return `npx vitest run ${list}`;
  if (deps.jest) return `npx jest ${list}`;
  return `node --test ${list}`;
}

function run(command, cwd) {
  return new Promise((resolve) => {
    const started = Date.now();
    const child = spawn('bash', ['-c', command], { cwd, detached: true, env: { ...process.env, CI: '1', FORCE_COLOR: '0' } });
    let output = '';
    let timedOut = false;
    const collect = (d) => { if (output.length < 400000) output += d; };
    child.stdout.on('data', collect);
    child.stderr.on('data', collect);
    const timer = setTimeout(() => { timedOut = true; try { process.kill(-child.pid, 'SIGKILL'); } catch {} }, timeoutMs);
    child.on('close', (code) => { clearTimeout(timer); resolve({ code: timedOut ? 124 : code, output, timedOut, seconds: (Date.now() - started) / 1000 }); });
    child.on('error', (error) => { clearTimeout(timer); resolve({ code: 127, output: String(error), timedOut: false, seconds: 0 }); });
  });
}

async function pool(items, worker) {
  const results = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(jobs, items.length) }, async () => {
    while (next < items.length) { const i = next++; results[i] = await worker(items[i], i); }
  }));
  return results;
}

const log = (line) => console.log(line);
let { entries, file: listFile } = await loadList();
if (only) entries = entries.filter((e) => e.id === only);
const base = basePort();
const results = [];

// Controls first: the unmutated project must pass each command, or a "caught" mutant proves nothing.
const commands = [];
const invalid = new Map();
for (const e of entries) {
  try { e.cmd = commandFor(e); } catch (error) { invalid.set(e.id, String(error.message)); continue; }
  if (!commands.includes(e.cmd)) commands.push(e.cmd);
}
const controls = await pool(commands, async (command, i) => {
  const dir = path.join(SCRATCH, `control-${i}`);
  copyProject(dir);
  rewritePort(dir, base, base ? base + 900 + i : null);
  const r = await run(command, dir);
  log(`${r.code === 0 ? 'CONTROL OK  ' : 'CONTROL FAIL'}  ${command}  (${r.seconds.toFixed(1)}s)`);
  if (r.code !== 0) log(r.output.split('\n').slice(-12).join('\n'));
  return { command, ok: r.code === 0 };
});
const badControls = new Set(controls.filter((c) => !c.ok).map((c) => c.command));

await pool(entries, async (e, i) => {
  const finish = (status, detail, seconds = 0) => {
    results.push({ id: e.id, file: e.file, status, detail });
    log(`${status.padEnd(10)}  ${e.id}  ${e.file ?? ''}${detail ? `  ${detail}` : ''}${seconds ? `  (${seconds.toFixed(1)}s)` : ''}`);
  };
  if (invalid.has(e.id)) return finish('INVALID', invalid.get(e.id));
  if (typeof e.file !== 'string' || (typeof e.find !== 'string' && !(e.find instanceof RegExp))) return finish('INVALID', 'needs file and find');
  if (badControls.has(e.cmd)) return finish('UNRELIABLE', 'its unmutated control failed');
  const dir = path.join(SCRATCH, e.id.replace(/[^\w.-]/g, '_'));
  copyProject(dir);
  const target = path.join(dir, e.file);
  const resolved = path.resolve(target);
  if (!resolved.startsWith(path.resolve(dir) + path.sep) || resolved.includes(`${path.sep}node_modules${path.sep}`)) return finish('INVALID', 'file is outside the project');
  if (!exists(target)) return finish('INVALID', `${e.file} does not exist`);
  const text = read(target);
  const count = e.find instanceof RegExp ? (text.match(new RegExp(e.find.source, `${e.find.flags.replace('g', '')}g`)) || []).length : text.split(e.find).length - 1;
  if (count !== 1) return finish('INVALID', `find occurs ${count} times in ${e.file}, not once`);
  fs.writeFileSync(target, e.find instanceof RegExp ? text.replace(e.find, e.replace) : text.replace(e.find, () => e.replace));
  rewritePort(dir, base, base ? base + 1 + i : null);
  const r = await run(e.cmd, dir);
  const named = e.expected === undefined || r.output.includes(String(e.expected));
  if (r.code === 0) return finish('SURVIVED', 'the tests still pass with this defect in', r.seconds);
  if (strict && !named) return finish('SURVIVED', `failed, but not in the expected test (${e.expected})`, r.seconds);
  return finish('CAUGHT', r.timedOut ? 'timed out' : '', r.seconds);
});

if (!keep) fs.rmSync(SCRATCH, { recursive: true, force: true });
const count = (s) => results.filter((r) => r.status === s).length;
const summary = { list: path.relative(ROOT, listFile), caught: count('CAUGHT'), survived: count('SURVIVED'), invalid: count('INVALID'),
  unreliable: count('UNRELIABLE'), controlsFailed: badControls.size, results };
fs.mkdirSync(path.join(ROOT, '.test-out'), { recursive: true });
fs.writeFileSync(path.join(ROOT, '.test-out', 'mutations.json'), JSON.stringify(summary, null, 2));
log(`Mutations: ${summary.caught} caught, ${summary.survived} survived, ${summary.invalid} invalid, ${summary.unreliable} unreliable; ` +
  `controls ${controls.length - badControls.size}/${controls.length} passed.`);
process.exit(summary.survived || summary.invalid || summary.unreliable || badControls.size ? 1 : 0);
