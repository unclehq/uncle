# Implementation order

Steps are designed to run in parallel where possible. Steps 1-3 are independent and can run concurrently. Step 4 (scaffold) must run first. Step 5 (defect injections) reads from the plan's interfaces and spec names, so it can be written alongside the others.

**Step 0: Scaffold** — Owns: `package.json`, `vite.config.js`, `playwright.config.js`, `index.html`, `.gitignore`
- Create Vite React project structure
- `package.json` with react, react-dom, vite, @vitejs/plugin-react, vitest, @playwright/test
- `vite.config.js` with React plugin
- `playwright.config.js` with base URL `http://127.0.0.1:5173`, webServer config to start Vite dev server
- `index.html` with root div and script tag
- `.gitignore` already updated

**Step 1: Arithmetic core** — Owns: `src/calc.js`, `tests/calc.test.js`
- `src/calc.js`: exports `evaluateExpression`, `validateAndAppend`, `handleBackspace`, `handleClear`, `handleDecimal`, `handleNegate`, `isValidExpression`
- `tests/calc.test.js`: unit tests for all exported functions

**Step 2: UI components** — Owns: `src/App.jsx`, `src/Calculator.jsx`, `src/Display.jsx`, `src/Keypad.jsx`, `src/Button.jsx`, `src/index.css`
- React components as described in Components table
- `src/index.css`: groovy 1970s theme with specified palette, font stack, background pattern
- `Calculator.jsx`: state management, keyboard handler, action dispatch

**Step 3: Browser tests** — Owns: `tests/calculator.spec.js`
- Playwright test file covering B-1 through B-13
- Uses `data-testid` selectors matching those in UI components

**Step 4: Defect injection runner** — Owns: `tests/defect-injections/mutations.json`, `tests/defect-injections/apply-mutation.js`, `tests/run-defect-injections.js`
- Mutation definitions
- Apply-mutation helper
- Parallel runner

