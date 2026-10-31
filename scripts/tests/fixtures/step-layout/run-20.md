# Implementation order

**Step 0: Scaffold** — Owns: `package.json`, `vite.config.js`, `playwright.config.js`, `index.html`, `.gitignore`

**Step 1: Arithmetic core** — Owns: `src/calc.js`, `tests/calc.test.js`

**Step 2: UI components** — Owns: `src/App.jsx`, `src/Calculator.jsx`, `src/Display.jsx`, `src/Keypad.jsx`, `src/Button.jsx`, `src/index.css`

**Step 3: Browser tests** — Owns: `tests/calculator.spec.js`

**Step 4: Defect injection runner** — Owns: `tests/defect-injections/mutations.json`, `tests/defect-injections/apply-mutation.js`, `tests/run-defect-injections.js`
