You are deriving one shared interface contract from an approved implementation plan, before any code is written.

The plan below will be implemented by several agents running at the same time, each in its own isolated sandbox, each writing a different set of files, and none of them able to see what the others write. Where one file imports from another (a reducer another file dispatches into, a key-mapping function a component calls, a formatter a test imports), every one of those isolated workers must agree on the *exact* exported name, its kind, and its call signature -- not just the general idea of what it does. Left to guess independently, two workers reliably disagree on small things: whether a shared initial-state value is a plain object or a function to call, whether an action field is named `op` or `operator`, whether a mapping function takes a raw string or a full event object. That disagreement is not a logic bug either worker could have caught alone; it only shows up once their separately-written files are merged together, and by then it reads as "the application doesn't build."

Your job is only to name those interfaces precisely, once, for everyone to implement against -- not to write any code, and not to decide anything the plan does not already decide.

Read `.uncle/docs/UPDATED_PROJECT_PLAN.md`, included in full below. Find every source file (not test file, not config file) that the plan's file-ownership table or its behavior/invariant sections describe as exporting something another file is expected to import, call, or dispatch into. For each such file, list every export another file depends on: its exact name, what kind of thing it is (function, const, class, type), and its exact call signature or shape -- parameter names, what each returns, and the literal field names of any object it takes or returns. Resolve every such interface the plan is specific enough to resolve; where the plan genuinely leaves a detail open (and only then), make the single most natural, conventional choice for the stack the plan describes, state it plainly, and do not hedge or offer options -- an implementing worker needs one exact answer, not a judgment call to make again alone.

Do not include files whose contents nothing else imports (e.g. a leaf UI component nothing else calls into, a standalone config file). Do not include internal/private helpers the plan does not expose across files. Do not guess at files or exports the plan does not mention.

The same disagreement happens one level lower, in the page itself. A component sets `className="keypad"`, a stylesheet written by a different worker styles `.key-grid`, and a test selects `[data-testid="display"]` that a third worker named `screen`. Nothing fails to build; the merged page just renders unstyled or the test cannot find its element. So also list, as `ui_contract`, every name that two or more of the plan's files must agree on by string: the CSS `class` names a component sets and a stylesheet styles, the `data-attribute`s (such as `data-key`), `test-id`s, element `id`s and `aria` labels a component sets and a test selects, and the keyboard `key` values a handler maps and a test presses. For each, give the `kind`, the exact `name` (the literal text), the `element` it is on, the `used_by` files from the plan's file-ownership table, and an optional `note` for the one requirement that matters (for example `4-column grid`). Choose each name once, from the plan if it names it and otherwise the most conventional one; the plan's own selectors, class names and test ids win. Leave `ui_contract` out when the plan has no page, or when no file shares such a name with another.

Write exactly one JSON object, as your one and only output, to this exact absolute path: {{CANONICAL_PATH}}

Use your file-write tool to create or overwrite that exact path -- do not invent a different path, do not place it in a different directory (including any scratch or working directory related to this task), and do not print the JSON as chat text instead of writing the file. The JSON object must match this shape:

```json
{
  "schema": "uncle.artifact/v1",
  "kind": "module-interfaces",
  "modules": [
    {
      "file": "src/engine.js",
      "exports": [
        {"name": "initialState", "kind": "function", "signature": "initialState(): State -- returns a fresh initial state object"},
        {"name": "reduce", "kind": "function", "signature": "reduce(state: State, action: Action): State -- pure, returns a new state"}
      ]
    }
  ],
  "ui_contract": [
    {"kind": "class", "name": "keypad", "element": "the div around every key", "used_by": ["src/App.jsx", "src/styles.css"], "note": "4-column grid"},
    {"kind": "data-attribute", "name": "data-key", "element": "every key button, value is the key's id", "used_by": ["src/App.jsx", "e2e/keyboard.spec.js"]}
  ]
}
```

Every `file` path matches exactly what the plan's file-ownership table names. Every export needs a non-empty `name`, `kind`, and one-sentence `signature` precise enough that two independent implementers would write interchangeable code from it alone.

## Approved plan (binding)

Use current stable test tooling resolved at install time (`latest` or a `^` range
based on the current release), including Playwright, Vite and Vitest when used;
never pin an old Playwright or an old Node. Keep the installed Node: do not
install or switch Node versions. If `package.json` sets `engines.node`, its
range must accept the installed Node major. Record resolved versions in the
lockfile; reuse a compatible installation. If an approved plan conflicts,
report it through the existing review/repair path; do not silently edit it.
