# AWS Bedrock runner

`aws-bedrock` is a profile of the Self Hosted runner class. It uses the Bedrock
Converse API for every model, with a bearer token, and never sends a
`temperature` field. Endpoints are derived from the Region (always https):
`https://bedrock.<region>.amazonaws.com` (model discovery) and
`https://bedrock-runtime.<region>.amazonaws.com` (Converse).

## Configure

In the TUI Configure menu, choose **AWS Bedrock** and set:

- **Region**: a lowercase AWS region such as `us-east-1`. There is no URL or
  API Compatibility field.
- **AWS Bedrock Token**: a single line of printable ASCII, stored in `.uncle/aws-bedrock-keys.json` (mode 0600).
  The save is refused if the file cannot be added to `.gitignore`.

Then set a stage runner, e.g. `<stage>.runner aws-bedrock`.

## Fallback (shell) configure path

When the TUI is unavailable, `uncle` -> Configure uses a shell fallback. Its
runner prompt lists the installed runners followed by `aws-bedrock` last, and
accepts `aws-bedrock` case-insensitively (stored lowercase). It works even when
no runner binaries are on `PATH`. The fallback offers Region/token setup
with the same validation and 0600 key file as the TUI. Self Hosted model
discovery (stages-menu `m`) on a Bedrock stage prints a pointer to per-stage
Configure and writes nothing.

Switching a stage's runner to or from `aws-bedrock` keeps its existing
`<stage>.model` unchanged and unvalidated, so a Self Hosted model name may sit
on a Bedrock stage (or vice versa) until you run `m`, which validates against
the key store of the stage's current runner.

## Settings

| Config key | Environment variable |
|---|---|
| `aws-bedrock.model` / `<stage>.model` | `UNCLE_AWS_BEDROCK_MODEL` |
| `<stage>.region` / `aws-bedrock.region` | `UNCLE_AWS_BEDROCK_REGION` |
| (token) | `UNCLE_AWS_BEDROCK_API_KEY` |

Model lookup order for a Bedrock stage: `UNCLE_AWS_BEDROCK_MODEL`,
`<stage>.model`, `aws-bedrock.model`. `UNCLE_SELF_HOSTED_MODEL` and
`self-hosted.model` are never read.

Other `WORKFLOW_SELF_HOSTED_*` settings (except temperature) apply to Bedrock.
Temperature env/config values and any `temperature` key in
`<stage>.request-options` are ignored for Bedrock.

## Isolation from Self Hosted

Bedrock uses its own key file and model sources. Missing Region, model or token
raises a Bedrock-worded error; it never falls back to Self Hosted credentials.
Self Hosted state is not rewritten by this feature.

## Legacy configuration

An existing config with `base_url` but no region derives the region from the
URL only when its host is exactly `bedrock[-runtime].<region>.amazonaws.com`
over https; otherwise set Region in Configure → AWS Bedrock.

## Limitations

Live compatibility with a real Bedrock endpoint has not been verified here.
