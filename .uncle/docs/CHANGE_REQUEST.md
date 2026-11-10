# Change Request

Issue 226

Seeded from [unclehq/uncle#226](https://github.com/unclehq/uncle/issues/226).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

One unknown supervision key (e.g. supervision.base_url) turns off all supervision corrections for an unattended run

## Motivation

## What happened

A hosted, unattended build's log began with:

```
[supervision] Supervision corrections disabled: unknown supervision key: supervision.base_url. Fix .uncle/config.
```

The build script had written `supervision.base_url` into `.uncle/config`. Uncle doesn't recognize that key, so it turned off **all** supervision corrections for the whole run. Nobody saw the message: in an unattended hosted run there is no operator watching the log. The build went on, failed later, and had no supervisor to diagnose or correct the failing stage.

## Where (main `4c23afac10`)

- `scripts/lib/supervisor.py:108-111` `parse_value`: an unknown key raises `unknown supervision key: supervision.<key>`.
- `scripts/lib/supervisor.py:203-212` `load_config` collects that into `errors`. `:192-196` `disabled_reason` then disables corrections whenever `errors` is non-empty.
- `scripts/lib/supervisor.py:57-72` `CONTROLS`: the supported keys. There is no `base_url` or `api_key`.
- `scripts/lib/supervisor.py:227-242` `_hosted_defaults`: in hosted mode (`UNCLE_HOSTED=1`), supervision already uses the self-hosted runner and the hosted model, with the address and key from `OPENAI_BASE_URL` / `OPENAI_API_KEY` (`scripts/lib/hosted.py:18-23`). So a hosted script never needs `supervision.base_url`.

## What's needed

1. **One bad key shouldn't switch off the safety net.** Ignore an unknown `supervision.*` key with a warning, and keep supervision on with the remaining valid settings. Keep disabling only when a recognized key has an invalid value that makes supervision unsafe.
2. **In unattended runs, make configuration errors visible before spending.** Either stop before the first paid stage with the message, or print it to stderr where the host's failure report will pick it up.
3. **Say it in the docs.** `.uncle/config.example` and `README.md` should state that in hosted mode supervision reads `OPENAI_BASE_URL`, `OPENAI_API_KEY` and `SEREN_MODEL`/`UNCLE_MODEL`, so no `supervision.base_url` is needed.
4. **Build script:** stop writing `supervision.base_url` to `.uncle/config`, and rely on hosted mode.

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
