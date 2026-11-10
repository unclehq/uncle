# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a temp UNCLE_RUNTIME_ROOT containing a copy of scripts/reviewer-self-hosted.sh and a recording fake scripts/lib/self_hosted.py, run the stagegate.sh reviewer launch with client_cmd set to the wrapper and a 200000-byte prompt.
- Expected result: The fake receives `--prompt-file <path>`, no argument exceeds 120000 bytes, and no `prompt is N bytes` refusal message is printed.
- Evidence to capture: Recorded argv from the fake reviewer, max argument length, and captured stderr/stdout of the launch.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat the 200000-byte wrapper launch through the change-workflow.sh reviewer launch block using the same temp runtime root and recording fake.
- Expected result: The fake receives `--prompt-file <path>`, no argument exceeds 120000 bytes, and no guard refusal message appears.
- Evidence to capture: Recorded argv, max argument length, and launch output.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch an argv-only client (e.g. a fake `codex` script) through each driver's launch block with a prompt of 120000 bytes, then 120001 bytes, then 200000 bytes.
- Expected result: The 120000-byte prompt is passed as an argument; the 120001 and 200000-byte prompts are refused with the existing `prompt is N bytes` message and exit status 1, and the client is never launched.
- Evidence to capture: Exit statuses, guard messages, and whether the fake client recorded an invocation, for each size and driver.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch an argv-only client carrying an allowlisted basename only as a later argument (e.g. `codex exec reviewer-self-hosted.sh`) and a wrapper-named script located outside UNCLE_RUNTIME_ROOT/scripts, each with a 200000-byte prompt, through both drivers.
- Expected result: Both are treated as argv: the guard refuses the oversize prompt and `--prompt-file` is not supplied.
- Evidence to capture: Exit status, guard message, and client invocation record for each command and driver.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch a `python3 other.py` client (non-allowlisted script) with a 200000-byte prompt through the stagegate block and then through the change-workflow block.
- Expected result: Stagegate sends it as file (`--prompt-file`, no refusal); change-workflow classifies it argv and the guard refuses it.
- Evidence to capture: Argv recorded by the fake and guard output for each driver.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run both drivers' launch blocks under bash `set -u` with an empty or unset client_cmd, and a two-candidate list of the wrapper plus an argv-only client with a 200000-byte prompt.
- Expected result: The empty command does not abort with an unbound-variable error and classifies argv; in the mixed list the wrapper candidate launches with `--prompt-file` while the argv-only candidate is classified argv and guarded.
- Evidence to capture: Exit statuses, stderr, and recorded launch forms for each candidate.
- Actual result: 
- Status: NOT RUN

### MC-108
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With UNCLE_HOSTED=1 and an empty .uncle/config, source scripts/lib/stage-config.sh offline, resolve the reviewer command, and run reviewer_prompt_kind on it.
- Expected result: The resolved command ends in reviewer-self-hosted.sh and is classified `file`; the check fails rather than skips if the wrapper is not resolved.
- Evidence to capture: Resolved command string and helper output.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch shell, source scripts/lib/reviewer-prompt.sh and run reviewer_prompt_guard against an argv-kind client with a prompt file of exactly 120000 bytes, then 120001 bytes, then 200000 bytes, noting the exit status and any message each time.
- Expected result: 120000 bytes returns 0 with no message; 120001 and 200000 bytes return 1 with the existing 'prompt is N bytes' refusal message (I1).
- Evidence to capture: Terminal transcript showing the three sizes, their exit codes and messages.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch shell, source scripts/lib/reviewer-prompt.sh and run reviewer_prompt_kind for these commands: none; an empty string; codex; claude; reviewer-kimi.sh; 'codex --config self_hosted.py'; 'claude reviewer-self-hosted.sh'; 'python3 other.py native_stage.py'. Check the output and exit status of each.
- Expected result: Every one prints 'argv' with exit status 0, so the argv guard still applies and an allowlisted name in a later argument is never matched (I3).
- Evidence to capture: Transcript listing each command, printed kind and exit status.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch shell with UNCLE_RUNTIME_ROOT set to this checkout, run reviewer_prompt_kind for: python3 .../self_hosted.py; python3 .../native_stage.py; bash .../reviewer-self-hosted.sh; $UNCLE_RUNTIME_ROOT/scripts/reviewer-self-hosted.sh. Then run it on a copy of a script named reviewer-self-hosted.sh placed in a temp dir outside $UNCLE_RUNTIME_ROOT/scripts.
- Expected result: The first four print 'file'. The same-named wrapper outside the runtime scripts directory prints 'argv'.
- Evidence to capture: Transcript with each command and its printed kind.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Do the same as MC-203 for the change-workflow.sh launch path (wrapper, 200000-byte prompt). Then run a 'python3 other.py' client with a 200000-byte prompt through both the stagegate path and the change-workflow path.
- Expected result: The wrapper run uses --prompt-file with no guard message. The 'python3 other.py' client is sent as a file by stagegate. change-workflow classifies it argv and the guard refuses with the existing message, exit 1 (I3 divergence).
- Evidence to capture: Transcripts of the four launches showing argv or file form, guard messages and exit statuses.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the race path with self-hosted.candidates 2, with one candidate being the wrapper and the other an argv-only client, using a 200000-byte prompt. Also run both drivers' launch blocks under 'set -u' with an empty or unset client_cmd.
- Expected result: The wrapper candidate is launched with --prompt-file. The argv-only candidate is refused by the guard, independently of the wrapper. The empty-client_cmd runs do not abort with an unbound-variable error.
- Evidence to capture: Transcript showing each candidate's launch form, the guard message for the argv candidate, and the empty-command runs with their exit statuses.
- Actual result: 
- Status: NOT RUN

## Resources: prompt file lifecycle

### MC-300
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a temp UNCLE_RUNTIME_ROOT holding a copy of scripts/reviewer-self-hosted.sh and a recording fake scripts/lib/self_hosted.py that stats the --prompt-file path, run the stagegate reviewer launch with a 200000-byte prompt and the wrapper as the reviewer client.
- Expected result: The fake receives `--prompt-file <path>` where the file has mode 0600 inside a private per-run directory, and after the run exits the file and directory no longer exist.
- Evidence to capture: Recorded argv, stat mode of the prompt file during the run, and a directory listing after exit.
- Actual result: 
- Status: NOT RUN

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat the MC-300 setup for the change-workflow launch, with the fake reviewer made to exit non-zero.
- Expected result: The launch uses `--prompt-file`, no argument exceeds 120000 bytes, no `prompt is N bytes` message appears, and the prompt file and its directory are removed even though the reviewer failed.
- Evidence to capture: Captured argv lengths, launcher output, and a post-exit listing of the temp directory.
- Actual result: 
- Status: NOT RUN

## Resources: argv-only guard

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the stagegate reviewer block with an argv-only client (a fake named codex) and a 200000-byte prompt, then again with a 120000-byte prompt.
- Expected result: The 200000-byte prompt is refused with the existing `prompt is N bytes` message and exit 1 without launching the client. The 120000-byte prompt is passed as an argument and the client launches.
- Evidence to capture: Exit codes, the guard message text, and whether the fake client recorded an invocation for each run.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a reviewer launch (stagegate and change-workflow blocks) with an argv-only client such as a fake `codex` or `reviewer-kimi.sh` and a prompt of 200000 bytes.
- Expected result: The launch is refused with the existing `prompt is N bytes` guard message and exit status 1; the reviewer is never started.
- Evidence to capture: Captured stderr/stdout and exit code for each driver.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch an argv-only client with prompts of exactly 120000 bytes and then 120001 bytes through the guard.
- Expected result: 120000 bytes launches with the prompt as a single argument; 120001 bytes is refused with the existing message and status 1.
- Evidence to capture: Exit codes, guard message text and recorded argv for both sizes.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch an argv-only client with a small prompt, and also with a client whose later argument is named `reviewer-self-hosted.sh` or `self_hosted.py` (e.g. `codex exec reviewer-self-hosted.sh`), with a 200000-byte prompt.
- Expected result: The small prompt is passed as argv unchanged; the look-alike client is still classified argv, receives no `--prompt-file`, and is refused by the guard when over 120000 bytes.
- Evidence to capture: Recorded argv of the fake client and guard output for each case.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch a `python3 <fake>.py` client through the stagegate block and then through the change-workflow block with a 200000-byte prompt.
- Expected result: Stagegate passes `--prompt-file` with no guard message (existing behavior); change-workflow for a non-allowlisted python3 script stays argv and is guarded. A python3 client running native_stage.py or self_hosted.py gets `--prompt-file` in both.
- Evidence to capture: Recorded argv and guard output per driver.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a self-hosted race with two candidates (the real wrapper plus an argv-only client) using a large prompt.
- Expected result: The wrapper candidate receives `--prompt-file`; the argv-only candidate is classified separately and guarded; the race path otherwise behaves as before.
- Evidence to capture: Per-candidate recorded argv and driver output.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run both driver launch blocks under bash with `set -u` and an empty or unset client command.
- Expected result: No unbound-variable abort; the command is treated as argv and handled by the existing path with no crash from classification.
- Evidence to capture: Exit status and stderr from each run.
- Actual result: 
- Status: NOT RUN
