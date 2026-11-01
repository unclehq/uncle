# Runner schema enforcement

When the workflow supplies `UNCLE_OUTPUT_SCHEMA_FILE`, Codex receives a strict
schema for its final answer: `codex exec --output-schema` in the CLI shim, or
`turn/start.outputSchema` in native steering sessions. The final object is
restored to the workflow's original shape, checked locally, and saved to
`UNCLE_STRUCTURED_OUTPUT_PATH`. Existing artifact validators still run.

Enforcement defaults to on. Set `<stage>.schema-enforce off` in `.uncle/config`
or `WORKFLOW_RUNNER_SCHEMA_ENFORCE=0` to retain file delivery. Environment
settings take precedence over config: stage, parent stage, then global.
For example, `WORKFLOW_RUNNER_SCHEMA_ENFORCE_UPDATED_PLAN=0` disables it for
updated-plan workers too. `runner.schema-enforce` is the global config key.

The strict copy closes objects and requires every property. Optional fields
accept null; synthetic nulls are removed before delivery. Originally nullable
fields retain null. Constants become enums. Length, count, and numeric bounds
are checked locally rather than sent to providers with narrower schema support.
Unsupported schema constructs (including references and open-ended maps) use
the existing file contract with a one-line diagnostic. The CLI shim also falls
back when its installed CLI does not advertise the required flags.

Native sessions retain live steering and runner reuse. Claude and self-hosted
schema handling is unchanged.
