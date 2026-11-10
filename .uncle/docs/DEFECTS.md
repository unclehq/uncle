# Defects

## Race path (race_self_hosted_reviewer_candidates) has no per-candidate guard, so the argv-only candidate refusal in MC-205 is not implemented. If self_hosted-only candidates are by design, the checklist or plan should be amended. Not yet recorded in DEFECTS.md.

- **Status:** FAIL
- **Evidence:** stagegate.sh: 'Candidates only ever run on self_hosted.py, which reads the prompt from a file' followed by printf '--prompt-file ...'. No reviewer_prompt_guard call in race_self_hosted_reviewer_candidates (guard calls are at ~2368 in the non-race path). set -u transcript: 'empty kind=argv / guard exit=1 (no unbound)'. Caveat: no live two-candidate race was run, so this is based on code reading.
- **Expected result:** The wrapper candidate is launched with --prompt-file. The argv-only candidate is refused by the guard, independently of the wrapper. Empty client_cmd runs do not abort with an unbound-variable error.
- **Actual result:** The race launch script hardcodes '--prompt-file "$CANDIDATE_DIR/prompt.md"' for every candidate. A source comment says candidates only ever run on self_hosted.py. The race path never calls reviewer_prompt_kind or reviewer_prompt_guard, so an argv-only candidate is not refused by the guard. It would be passed --prompt-file instead. Expected wrapper behaviour is only incidentally met. The empty client_cmd expansion under set -u gave kind=argv with no unbound error (guard exit 1 for the 200000-byte file, the normal refusal).

## Prompt-file lifecycle (private 0600 dir, cleanup after exit) not implemented in reviewer launch; no DEFECTS.md entry written by this worker

- **Status:** FAIL
- **Evidence:** stagegate.sh lines ~2358-2366 (prompt_args=(--prompt-file "$prompt_file")); grep for 0600|chmod 600|umask|mktemp -d across the three scripts returned only unrelated mktemp -d calls (stagegate.sh 942, 4105, 4163, 5208; change-workflow.sh 1400, 1466). The prompt-lifecycle behavior is absent from the code. Static inspection plus grep only.
- **Expected result:** The fake receives --prompt-file <path> with mode 0600 inside a private per-run directory; after the run exits the file and directory no longer exist.
- **Actual result:** The launcher passes --prompt-file for file-capable clients (reviewer-self-hosted.sh under UNCLE_RUNTIME_ROOT is classified 'file'). However the path passed is the existing driver prompt file ($STATE_DIR/<log>-delivery-prompt.md or similar). Nothing creates a private per-run directory, sets mode 0600, or removes the file or directory after exit. grep found no 0600/chmod/umask or prompt cleanup; the only mktemp -d calls are for verification snapshots and checklist-workers.

## Prompt-file cleanup on reviewer failure not implemented; no DEFECTS.md entry written by this worker

- **Status:** FAIL
- **Evidence:** change-workflow.sh lines ~2597-2605 (prompt_args=(--prompt-file ...)) and the failure path at ~2606-2608 (reviewer_report_launch_failure) with no cleanup; reviewer-prompt.sh line 46 message is in the argv-only guard. Static inspection only; no live run.
- **Expected result:** Launch uses --prompt-file, no argument exceeds 120000 bytes, no 'prompt is N bytes' message appears, and the prompt file and its directory are removed even though the reviewer failed.
- **Actual result:** The first three parts hold by code reading. File-capable clients get --prompt-file, so the prompt is not in argv. reviewer_prompt_guard only emits 'prompt is N bytes' for the argv kind. The fourth part fails: change-workflow.sh never removes the prompt file or a directory after a non-zero reviewer exit. It continues to reportlaunch failure handling and retains the file in $STATE_DIR. No cleanup trap or rm of the prompt file exists.

## None recorded; likely a checklist/design mismatch: the checklist expects per-candidate classification the implementation does not provide. Needs a plan or checklist decision.

- **Status:** FAIL
- **Evidence:** grep of reviewer_prompt_kind/reviewer_prompt_guard/prompt_kind in scripts/stagegate.sh shows only lines 2358-2372, in the non-race branch; the race function (2067-2160) has no such calls. Not executed live.
- **Expected result:** Wrapper candidate receives --prompt-file; an argv-only candidate is classified separately and guarded; race path otherwise unchanged.
- **Actual result:** Every race candidate launch script is built from the same client_cmd and unconditionally appends --prompt-file "$CANDIDATE_DIR/prompt.md" (stagegate.sh ~line 2155-2160, comment: 'Candidates only ever run on self_hosted.py'). The race path never calls reviewer_prompt_kind or reviewer_prompt_guard, and there is no per-candidate classification. The wrapper-gets---prompt-file half holds by construction. The 'argv-only candidate classified separately and guarded' half cannot occur: a race has no mixed candidate kinds, and an argv-only client is not raced because the race is gated on the self-hosted runner.
