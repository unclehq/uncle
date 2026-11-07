# AWS Bedrock runner

`aws-bedrock` is a profile of the Self Hosted runner class. It talks to an
OpenAI-compatible Bedrock endpoint with a bearer token and never sends a
`temperature` field.

## Configure

In the TUI Configure menu, choose **AWS Bedrock** and set:

- **Bedrock URL**: the endpoint base URL. URLs containing userinfo, a query or
  a fragment are rejected.
- **AWS Bedrock Token**: stored in `.uncle/aws-bedrock-keys.json` (mode 0600).
  The save is refused if the file cannot be added to `.gitignore`.

Then set a stage runner, e.g. `<stage>.runner aws-bedrock`.

## Settings

| Config key | Environment variable |
|---|---|
| `aws-bedrock.model` / `<stage>.model` | `UNCLE_AWS_BEDROCK_MODEL` |
| `aws-bedrock.base_url` | `UNCLE_AWS_BEDROCK_BASE_URL` |
| (token) | `UNCLE_AWS_BEDROCK_API_KEY` |

Model lookup order for a Bedrock stage: `UNCLE_AWS_BEDROCK_MODEL`,
`<stage>.model`, `aws-bedrock.model`. `UNCLE_SELF_HOSTED_MODEL` and
`self-hosted.model` are never read.

Other `WORKFLOW_SELF_HOSTED_*` settings (except temperature) apply to Bedrock.
Temperature env/config values and any `temperature` key in
`<stage>.request-options` are ignored for Bedrock.

## Isolation from Self Hosted

Bedrock uses its own key file and model sources. Missing URL, model or token
raises a Bedrock-worded error; it never falls back to Self Hosted credentials.
Self Hosted state is not rewritten by this feature.

## Limitations

Live compatibility with a real Bedrock endpoint has not been verified here.
