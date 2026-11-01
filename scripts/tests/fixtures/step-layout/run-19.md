# Implementation order

## Step 1: Scaffold — Owns: `package.json`, `playwright.config.js`, `tests/calculator.test.js`, `tests/injections/run.js`, `tests/injections/mutations.js`, `.gitignore`

## Step 2: Calculator logic — Owns: `src/calc.js`

## Step 3: UI components — Owns: `src/ui.js`, `index.html`

## Step 3b: Test suite and injection runner — Owns: `tests/calculator.test.js`, `tests/injections/run.js`, `tests/injections/mutations.js`

## Step 4: Launch metadata — Owns: `.uncle/launch.json`
