## 12. Implementation order

### Step 1: Project scaffold and theme

**Owns:** `package.json`, `vite.config.js`, `playwright.config.js`, `index.html`, `src/main.jsx`, `src/index.css`, `src/theme.css`, `.gitignore`

**Owns (additional):** `.eslintrc.cjs`

### Step 2: Calculator logic (reducer)

**Owns:** `src/calcReducer.js`, `src/calcReducer.test.js`

### Step 3: UI components

**Owns:** `src/Display.jsx`, `src/CalcButton.jsx`, `src/Keypad.jsx`, `src/Calculator.jsx`, `src/App.jsx`, `src/App.test.jsx`

### Step 4: Browser tests

**Owns:** `tests/theme.spec.js`, `tests/calculator.spec.js`

### Step 5: Defect injection runner

**Owns:** `tests/injections/manifest.json`, `tests/injections/run.js`

### Step 6: Launch metadata

**Owns:** `.uncle/launch.json`, `.github/workflows/ci.yml`
