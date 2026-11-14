# Change Request

Issue 268

Seeded from [unclehq/uncle#268](https://github.com/unclehq/uncle/issues/268).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Updated-plan edit schemas have 130+ optional fields, so Claude models can't enforce them and writers fail on format

## Motivation

## What happened

In the same hosted build as #267 (Claude Sonnet 5, OpenAI-compatible chat route backed by Amazon Bedrock), 3 of the 10 updated-plan edit writer calls returned packets that broke their schema, although each was sent with `response_format: {"type": "json_schema", ...}`:

```
cause: Model response violates the artifact schema (json_schema constraint): $.ops[4] matches none of the allowed forms ($.ops[4].fields.depends_on must be string; $.ops[4] is missing required field new; ...)
cause: Model response violates the artifact schema (json_schema constraint): $.ops[2] matches none of the allowed forms ($.ops[2].id must be one of 'R-1', 'R-2', 'R-3', 's10', ...)
cause: Model response violates the artifact schema (json_object constraint): $.ops[0] matches none of the allowed forms ($.ops[0].after must be one of '', 's10.4'; $.ops[0].target must be 's12')
```

A grammar-enforced reply could not contain an `id` outside its `enum` or an array where a string is required. The schema was not enforced.

## Cause

Claude models on Bedrock enforce a response schema only when it has at most 24 optional properties. This build's updated-plan edit schemas (`.uncle/workflow/updated-plan-edits/schemas/*.json`) have 133–159 each. Sending writer 2's schema to Bedrock's Converse API as `output_config.format` returns:

```
ValidationException: Schemas contains too many optional parameters (159), which would make grammar compilation inefficient. Reduce the number of optional parameters in your tool schemas (limit: 24).
```

129 of the 159 come from the generic op in [`scripts/lib/worker_schemas.py#L194-L201`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/worker_schemas.py#L194-L201): its `fields` and `new` objects list every `FIELD_NAMES` entry as optional. `set_step` fields ([`#L356`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/worker_schemas.py#L356)) and row `fields` ([`#L298-L303`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/worker_schemas.py#L298-L303)) are also all optional.

When a schema can't be enforced, the Seren route asks the model for any JSON object, passes the schema as an instruction, and says so in two response headers:

- `x-seren-schema-relaxed`: the schema rules it could not enforce (here including `optional parameters`).
- `x-seren-schema-check`: `failed; <first violation>` when its own check of those rules fails.

[`scripts/lib/self_hosted_http.py`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/self_hosted_http.py#L1524) does not read either header, so `http_agent.py` records the mode as `json_schema` and treats the reply as a model failure. Bounded updated-plan writers also skip the targeted repair step ([`http_agent.py#L1352-L1356`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/http_agent.py#L1352-L1356), [`#L1442-L1449`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/http_agent.py#L1442-L1449)), so each bad packet cost a full re-ask: about 2.5 minutes in this build.

The typed project-plan sections failed earlier in the same build on invalid JSON (`Unrepaired draft: Expecting ',' delimiter`). That fits the same unenforced format, but I did not test that schema.

## Requested fix

1. Keep each edit schema within 24 optional properties. For example, replace the optional `fields`/`new` objects in the generic op with a required array of `{"name": <enum of field names>, "value": <string>}` pairs, or drop the generic variant when the plan-model ops already cover the edit.
2. When a reply carries `x-seren-schema-relaxed`, treat it as unenforced: allow the targeted repair step for bounded writers instead of failing the writer.

Checked against `main` at `c5815a928b`; the cited lines are unchanged there.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
