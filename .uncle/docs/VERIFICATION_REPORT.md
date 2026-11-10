# Verification report

## Findings

### MC-101

- **Action:** Built a temp UNCLE_RUNTIME_ROOT with a copy of scripts/reviewer-self-hosted.sh, the real scripts/lib/reviewer-prompt.sh and a recording fake scripts/lib/self_hosted.py. Using a harness that mirrors the stagegate.sh launch block (lines ~2360-2375: reviewer_prompt_kind, python3 override, reviewer_prompt_guard, prompt_args), launched the wrapper with a 200000-byte prompt. The harness replicates the block rather than executing stagegate.sh itself.
- **Expected result:** Fake receives --prompt-file <path>, no argument exceeds 120000 bytes, no 'prompt is N bytes' refusal.
- **Actual result:** prompt_kind=file; the fake received 'reviewer exec --ephemeral --prompt-file <path>'; max argument length 78 bytes; no guard refusal printed; rc=0.
- **Defects:** None

### MC-102

- **Action:** Repeated the 200000-byte launch with the same temp runtime root and recording fake, through a harness mirroring the change-workflow.sh launch block (lines ~2596-2604: reviewer_prompt_kind, reviewer_prompt_guard, prompt_args). The harness replicates the block rather than executing change-workflow.sh itself.
- **Expected result:** Fake receives --prompt-file <path>, no argument exceeds 120000 bytes, no guard refusal.
- **Actual result:** prompt_kind=file; guard returned 0; the fake received 'reviewer --prompt-file <path>'; max argument length 78 bytes; no refusal message; rc=0.
- **Defects:** None

### MC-103

- **Action:** Sourced the real scripts/lib/reviewer-prompt.sh and replayed each driver's launch block (reviewer_prompt_kind, stagegate's python3 override, reviewer_prompt_guard, prompt_args, launch; copied from stagegate.sh ~2358-2385 and change-workflow.sh ~2595-2606) with a fake argv-only `codex` script that logs invocations. Prompts of 120000, 120001 and 200000 bytes, for both drivers. The full drivers were not started; only the launch logic was replayed.
- **Expected result:** 120000 bytes passed as an argument; 120001 and 200000 refused with 'prompt is N bytes' and exit 1; client never launched.
- **Actual result:** Both drivers: 120000 -> kind=argv, client invoked with 2 args (exec + prompt), exit 0. 120001 -> 'Reviewer rv: prompt is 120001 bytes, over Linux's 131,072-byte per-argument limit...' exit 1, client log empty. 200000 -> 'prompt is 200000 bytes...' exit 1, client log empty.
- **Defects:** None

### MC-104

- **Action:** Same replayed launch logic for both drivers with a 200000-byte prompt, for (a) `<fake codex> exec reviewer-self-hosted.sh` (allowlisted basename only as a later argument) and (b) a reviewer-self-hosted.sh copy in a temp dir outside UNCLE_RUNTIME_ROOT/scripts.
- **Expected result:** Both treated as argv: guard refuses the oversize prompt and --prompt-file is not supplied.
- **Actual result:** All four combinations (2 commands x 2 drivers): kind=argv, 'prompt is 200000 bytes' guard message, exit 1, client never invoked (empty log). With kind=argv, --prompt-file was not added.
- **Defects:** None

### MC-105

- **Action:** Ran a temp bash probe (set -u, UNCLE_RUNTIME_ROOT=repo) that sources scripts/lib/reviewer-prompt.sh and replays the real prompt_kind/guard lines copied from stagegate.sh (2358-2370) and change-workflow.sh (2595-2603) for client_cmd=(python3 other.py) with a 200000-byte prompt file.
- **Expected result:** Stagegate sends it as file (--prompt-file, no refusal); change-workflow classifies it argv and the guard refuses it.
- **Actual result:** Stagegate: kind=file, args=--prompt-file, guard passed, rc=0. change-workflow: kind=argv, guard refused ('prompt is 200000 bytes, over Linux's 131,072-byte per-argument limit'), rc=1.
- **Defects:** None

### MC-106

- **Action:** Under bash set -u, replayed both drivers' launch lines with client_cmd empty (zero elements) and with a single empty string, and with two candidates: the wrapper scripts/reviewer-self-hosted.sh (under UNCLE_RUNTIME_ROOT/scripts) and an argv-only client 'mytool', each with a 200000-byte prompt.
- **Expected result:** The empty command does not abort with an unbound-variable error and classifies argv; in the mixed list the wrapper candidate launches with --prompt-file while the argv-only candidate is classified argv and guarded.
- **Actual result:** Empty/unset client_cmd: no unbound-variable error in either driver; kind=argv and the guard refused on size (rc=1, an intended guard result, not an abort). Wrapper candidate: kind=file with --prompt-file, rc=0 in both drivers. 'mytool': kind=argv, GUARD-REFUSED, rc=1 in both drivers.
- **Defects:** None

### MC-108

- **Action:** With UNCLE_HOSTED=1, an empty project .uncle/config (PROJECT_ROOT=temp dir, UNCLE_CONFIG unset), UNCLE_RUNTIME_ROOT and ROOT set to the repo, sourced scripts/lib/stage-config.sh and reviewer-prompt.sh, ran stage_reviewer_cmd adversarial-review and reviewer_prompt_kind on the result. An earlier attempt that let the repo's own non-empty .uncle/config leak in resolved reviewer-claude.sh (argv); that was a setup error, not the scenario under test.
- **Expected result:** Resolved command ends in reviewer-self-hosted.sh and is classified file.
- **Actual result:** Resolved command was /Users/brianwoods/src/unclehq/uncle-issue-232/scripts/reviewer-self-hosted.sh; reviewer_prompt_kind printed 'file'.
- **Defects:** None

### MC-200

- **Action:** Sourced scripts/lib/reviewer-prompt.sh and ran reviewer_prompt_guard r argv FILE for files of 120000, 120001 and 200000 bytes.
- **Expected result:** 120000 bytes returns 0 with no message; 120001 and 200000 return 1 with the 'prompt is N bytes' refusal.
- **Actual result:** 120000: exit=0, no message. 120001: exit=1 with 'Reviewer r: prompt is 120001 bytes, over Linux's 131,072-byte per-argument limit (guard 120000)...'. 200000: exit=1 with 'prompt is 200000 bytes' message.
- **Defects:** None

### MC-201

- **Action:** Sourced scripts/lib/reviewer-prompt.sh in a scratch bash and ran reviewer_prompt_kind with each command as separate argv elements: (none); ""; codex; claude; reviewer-kimi.sh; codex --config self_hosted.py; claude reviewer-self-hosted.sh; python3 other.py native_stage.py. Printed output and rc for each.
- **Expected result:** Every one prints 'argv' with exit status 0.
- **Actual result:** All 8 cases printed 'argv' with rc=0.
- **Defects:** None

### MC-202

- **Action:** With UNCLE_RUNTIME_ROOT set to the checkout, ran reviewer_prompt_kind (args as separate elements) for python3 $R/scripts/self_hosted.py; python3 $R/scripts/native_stage.py; bash $R/scripts/reviewer-self-hosted.sh; $R/scripts/reviewer-self-hosted.sh; then a copy of reviewer-self-hosted.sh in a mktemp dir, both directly and via bash.
- **Expected result:** First four print 'file'; same-named wrapper outside the runtime scripts dir prints 'argv'.
- **Actual result:** First four printed 'file' (rc=0). The temp-dir copy printed 'argv' both directly and via bash.
- **Defects:** None

### MC-204

- **Action:** Sourced scripts/lib/reviewer-prompt.sh (UNCLE_RUNTIME_ROOT set) in bash and ran reviewer_prompt_kind + reviewer_prompt_guard on a 200000-byte prompt for: the scripts/reviewer-self-hosted.sh wrapper, 'python3 other.py', 'python3 self_hosted.py', 'codex'. Replicated the stagegate.sh python3-first override (lines ~2360-2364) and read the change-workflow.sh launch block (lines ~2594-2602), which uses the helper alone. Did not run the full drivers or a real reviewer; the launch logic was exercised through the shared helper and code reading.
- **Expected result:** Wrapper uses --prompt-file with no guard message. 'python3 other.py' is sent as a file by stagegate. change-workflow classifies it argv and the guard refuses with the existing message, exit 1.
- **Actual result:** Wrapper: kind=file, guard exit 0, no message. 'python3 other.py': helper kind=argv, guard exit 1 with the existing message ('prompt is 200000 bytes, over Linux's 131,072-byte per-argument limit...'), which is the change-workflow path. The stagegate override turns python3-first argv into file, so --prompt-file is used there. 'python3 self_hosted.py' gives file, exit 0, and 'codex' gives argv, exit 1. Both drivers' code matches this. scripts/tests/reviewer-prompt-kind-test.py: 9 tests OK.
- **Defects:** None

### MC-205

- **Action:** Read race_self_hosted_reviewer_candidates in scripts/stagegate.sh (launch script generation, ~lines 2100-2160) to see how each candidate is launched. Ran the empty client_cmd case under 'set -u' using the same ${client_cmd[@]+...} expansion the drivers use: kind=argv, no unbound-variable error. Did not run a live race, because the race path has no per-candidate kind or guard to exercise.
- **Expected result:** The wrapper candidate is launched with --prompt-file. The argv-only candidate is refused by the guard, independently of the wrapper. Empty client_cmd runs do not abort with an unbound-variable error.
- **Actual result:** The race launch script hardcodes '--prompt-file "$CANDIDATE_DIR/prompt.md"' for every candidate. A source comment says candidates only ever run on self_hosted.py. The race path never calls reviewer_prompt_kind or reviewer_prompt_guard, so an argv-only candidate is not refused by the guard. It would be passed --prompt-file instead. Expected wrapper behaviour is only incidentally met. The empty client_cmd expansion under set -u gave kind=argv with no unbound error (guard exit 1 for the 200000-byte file, the normal refusal).
- **Defects:** Race path (race_self_hosted_reviewer_candidates) has no per-candidate guard, so the argv-only candidate refusal in MC-205 is not implemented. If self_hosted-only candidates are by design, the checklist or plan should be amended. Not yet recorded in DEFECTS.md.

### MC-300

- **Action:** Inspected the reviewer launch path in scripts/stagegate.sh (~2355-2380) and scripts/lib/reviewer-prompt.sh, and searched scripts/stagegate.sh, scripts/change-workflow.sh and scripts/lib/reviewer-prompt.sh for private-directory creation, 0600/chmod/umask handling and prompt-file cleanup. I did not run a live launch with a fake self_hosted.py.
- **Expected result:** The fake receives --prompt-file <path> with mode 0600 inside a private per-run directory; after the run exits the file and directory no longer exist.
- **Actual result:** The launcher passes --prompt-file for file-capable clients (reviewer-self-hosted.sh under UNCLE_RUNTIME_ROOT is classified 'file'). However the path passed is the existing driver prompt file ($STATE_DIR/<log>-delivery-prompt.md or similar). Nothing creates a private per-run directory, sets mode 0600, or removes the file or directory after exit. grep found no 0600/chmod/umask or prompt cleanup; the only mktemp -d calls are for verification snapshots and checklist-workers.
- **Defects:** Prompt-file lifecycle (private 0600 dir, cleanup after exit) not implemented in reviewer launch; no DEFECTS.md entry written by this worker

### MC-301

- **Action:** Inspected the change-workflow.sh reviewer launch (~2585-2640) and reviewer_prompt_guard / reviewer_prompt_kind in scripts/lib/reviewer-prompt.sh. I did not run a live launch with a failing fake reviewer.
- **Expected result:** Launch uses --prompt-file, no argument exceeds 120000 bytes, no 'prompt is N bytes' message appears, and the prompt file and its directory are removed even though the reviewer failed.
- **Actual result:** The first three parts hold by code reading. File-capable clients get --prompt-file, so the prompt is not in argv. reviewer_prompt_guard only emits 'prompt is N bytes' for the argv kind. The fourth part fails: change-workflow.sh never removes the prompt file or a directory after a non-zero reviewer exit. It continues to reportlaunch failure handling and retains the file in $STATE_DIR. No cleanup trap or rm of the prompt file exists.
- **Defects:** Prompt-file cleanup on reviewer failure not implemented; no DEFECTS.md entry written by this worker

### MC-302

- **Action:** Sourced the real scripts/lib/reviewer-prompt.sh and replicated the stagegate reviewer-block launch sequence (reviewer_prompt_kind, then reviewer_prompt_guard, then invoking the client with the prompt as one argv element) with a fake argv-only client named codex. Ran it with a 200000-byte prompt, then a 120000-byte prompt. The full stagegate.sh driver was not run end to end.
- **Expected result:** 200000 bytes refused with 'prompt is N bytes' and exit 1, client not launched. 120000 bytes passed as an argument and client launches.
- **Actual result:** 200000: printed 'Reviewer rv: prompt is 200000 bytes, over Linux's 131,072-byte per-argument limit (guard 120000)...', exit 1, fake client call count 0. 120000: guard passed, fake client launched (argc=4, exit 0), call count 1.
- **Defects:** None

### MC-401

- **Action:** Ran the same guard with a fake codex and a 200000-byte prompt (stagegate pattern, shown in the output above). For change-workflow.sh, inspected the source: line ~2597 calls reviewer_prompt_guard on the prompt file and returns 1 before building prompt_args or launching the client. The change-workflow block itself was not executed live. The reviewer-kimi.sh client was not run.
- **Expected result:** Launch refused with the existing 'prompt is N bytes' message and exit 1, with the reviewer never started.
- **Actual result:** The stagegate-pattern run refused with the 'prompt is 200000 bytes' message, exit 1, and zero client invocations. In change-workflow.sh the guard failure triggers 'return 1' before the client command, which is confirmed by source inspection only, not by a live run.
- **Defects:** None

### MC-402

- **Action:** Sourced scripts/lib/reviewer-prompt.sh and, with a fake argv-only client (records argc and last-arg length), classified with reviewer_prompt_kind, ran reviewer_prompt_guard, and launched on success, for prompts of exactly 120000 and 120001 bytes.
- **Expected result:** 120000 bytes launches with the prompt as a single argument; 120001 bytes is refused with the existing message and status 1.
- **Actual result:** 120000: kind=argv, guard=0, client launched with 2 args (exec + prompt), last-arg length 120000. 120001: kind=argv, guard=1, message 'Reviewer rv: prompt is 120001 bytes, over Linux's 131,072-byte per-argument limit (guard 120000)...', client not launched.
- **Defects:** None

### MC-403

- **Action:** Same fake-client harness: small 50-byte prompt via 'fake.sh exec'; 200000-byte prompts via 'fake.sh exec reviewer-self-hosted.sh', 'fake.sh exec self_hosted.py', and 'codex exec reviewer-self-hosted.sh' (no real codex launched since guard refused).
- **Expected result:** The small prompt is passed as argv unchanged; the look-alike client is still classified argv, receives no --prompt-file, and is refused by the guard when over 120000 bytes.
- **Actual result:** Small: kind=argv, guard=0, launched with 2 args, last-arg length 50. All three look-alike cases: kind=argv, guard=1 with 'prompt is 200000 bytes' message, not launched, so no --prompt-file was passed.
- **Defects:** None

### MC-404

- **Action:** Ran a narrow live probe that extracts the real prompt_kind lines from scripts/stagegate.sh (3 following lines) and scripts/change-workflow.sh (helper line alone), feeds client_cmd of python3 fake.py / python3 self_hosted.py / python3 native_stage.py, then runs reviewer_prompt_guard on a 200000-byte prompt.
- **Expected result:** Stagegate: python3 fake client gets file, no guard message. change-workflow: non-allowlisted python3 script stays argv and is guarded. python3 self_hosted.py / native_stage.py get file in both.
- **Actual result:** python3 fake.py: stagegate=file, guard rc 0 (no message); change-workflow=argv, guard rc 1 with 'prompt is 200000 bytes, over Linux's 131,072-byte...'. python3 self_hosted.py and native_stage.py: file in both drivers, guard rc 0.
- **Defects:** None

### MC-405

- **Action:** Read the self-hosted race path in scripts/stagegate.sh (race_self_hosted_reviewer_candidates, entered at ~line 2346 only when UNCLE_RESOLVED_RUNNER=self-hosted and candidate count > 1) to see how candidates get their prompt. Did not run a full live race: candidates all derive from the one client_cmd, so a two-candidate wrapper plus argv-only race cannot be configured.
- **Expected result:** Wrapper candidate receives --prompt-file; an argv-only candidate is classified separately and guarded; race path otherwise unchanged.
- **Actual result:** Every race candidate launch script is built from the same client_cmd and unconditionally appends --prompt-file "$CANDIDATE_DIR/prompt.md" (stagegate.sh ~line 2155-2160, comment: 'Candidates only ever run on self_hosted.py'). The race path never calls reviewer_prompt_kind or reviewer_prompt_guard, and there is no per-candidate classification. The wrapper-gets---prompt-file half holds by construction. The 'argv-only candidate classified separately and guarded' half cannot occur: a race has no mixed candidate kinds, and an argv-only client is not raced because the race is gated on the self-hosted runner.
- **Defects:** None recorded; likely a checklist/design mismatch: the checklist expects per-candidate classification the implementation does not provide. Needs a plan or checklist decision.

### MC-406

- **Action:** Under bash 3.2.57 with `set -u`, sourced scripts/lib/reviewer-prompt.sh and executed the exact classification lines used by both driver launch blocks (stagegate.sh ~2358-2363 and change-workflow.sh ~2595-2596, `reviewer_prompt_kind ${client_cmd[@]+"${client_cmd[@]}"}` plus the `${client_cmd[0]:-}` python3 test) with client_cmd declared-but-unset and with client_cmd=(). Replicated the lines in a temp script rather than running the full drivers.
- **Expected result:** No unbound-variable abort; command treated as argv and handled by existing path with no crash from classification.
- **Actual result:** Both cases printed kind=argv; script exit status 0; no unbound-variable error on stderr.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Recorded: ARGC=5 MAX=78 ARGV=['reviewer','exec','--ephemeral','--prompt-file','/var/folders/.../tmp.iOoLHIK']; launch output contained only 'kind=file rc=0'. |
| MC-102 | YES | PASS | Recorded: ARGC=3 MAX=78 ARGV=['reviewer','--prompt-file','/var/folders/.../tmp.iOoLHIK']; launch output contained only 'kind=file rc=0'. |
| MC-103 | YES | PASS | Harness output in the worker session: EXIT=0 with 'INVOKED 2 args first=exec' for 120000; EXIT=1 with the guard message and empty fake-client log for 120001 and 200000, in both the stage and change drivers. |
| MC-104 | YES | PASS | Harness output: EXIT=1 kind=argv plus the guard message for every MC-104 case, and an empty fake-client log. Drivers were replayed, not run end to end. |
| MC-105 | YES | PASS | Probe output: 'kind=file args=--prompt-file / sg rc=0' and 'Reviewer t: prompt is 200000 bytes ... kind=argv GUARD-REFUSED / cw rc=1'. Driver code replayed rather than the full drivers being launched. |
| MC-106 | YES | PASS | Probe output for sg/cw with empty and '' commands showed 'kind=argv GUARD-REFUSED' with no 'unbound variable' on stderr. Wrapper lines showed 'kind=file args=--prompt-file rc=0'. mytool lines showed 'kind=argv GUARD-REFUSED rc=1'. |
| MC-108 | YES | PASS | Transcript: CMD=[/Users/brianwoods/src/unclehq/uncle-issue-232/scripts/reviewer-self-hosted.sh] KIND=file |
| MC-200 | YES | PASS | Transcript: size=120000 exit=0; size=120001 exit=1 (prompt is 120001 bytes message); size=200000 exit=1 (prompt is 200000 bytes message). |
| MC-201 | YES | PASS | Transcript: ' -> argv rc=0' (none and empty), 'codex -> argv rc=0', 'claude -> argv rc=0', 'reviewer-kimi.sh -> argv rc=0', 'codex --config self_hosted.py -> argv rc=0', 'claude reviewer-self-hosted.sh -> argv rc=0', 'python3 other.py native_stage.py -> argv rc=0'. |
| MC-202 | YES | PASS | Transcript: python3 .../self_hosted.py -> file; python3 .../native_stage.py -> file; bash .../scripts/reviewer-self-hosted.sh -> file; .../scripts/reviewer-self-hosted.sh -> file; /var/folders/.../tmp.3zgCLhWsc3/reviewer-self-hosted.sh -> argv; bash <that> -> argv. (An earlier attempt passing the whole command as one quoted string gave argv for the bash case; that was my invocation error, since the function takes argv elements, and was corrected.) |
| MC-204 | YES | PASS | Transcript from /tmp/mc204/t.sh: 'cmd=[.../reviewer-self-hosted.sh] kind=file exit=0'; 'cmd=[python3 other.py] kind=argv exit=1 msg=Reviewer t: prompt is 200000 bytes...'; 'stagegate python3 other.py -> file'. Caveat: the full driver launches were not executed live. |
| MC-205 | YES | FAIL | stagegate.sh: 'Candidates only ever run on self_hosted.py, which reads the prompt from a file' followed by printf '--prompt-file ...'. No reviewer_prompt_guard call in race_self_hosted_reviewer_candidates (guard calls are at ~2368 in the non-race path). set -u transcript: 'empty kind=argv / guard exit=1 (no unbound)'. Caveat: no live two-candidate race was run, so this is based on code reading. |
| MC-300 | YES | FAIL | stagegate.sh lines ~2358-2366 (prompt_args=(--prompt-file "$prompt_file")); grep for 0600/chmod 600/umask/mktemp -d across the three scripts returned only unrelated mktemp -d calls (stagegate.sh 942, 4105, 4163, 5208; change-workflow.sh 1400, 1466). The prompt-lifecycle behavior is absent from the code. Static inspection plus grep only. |
| MC-301 | YES | FAIL | change-workflow.sh lines ~2597-2605 (prompt_args=(--prompt-file ...)) and the failure path at ~2606-2608 (reviewer_report_launch_failure) with no cleanup; reviewer-prompt.sh line 46 message is in the argv-only guard. Static inspection only; no live run. |
| MC-302 | YES | PASS | Terminal output of the harness run. Also read stagegate.sh lines ~2356-2380, which use this guard-then-argv sequence. scripts/tests/reviewer-prompt-kind-test.py: 9 tests OK. |
| MC-401 | YES | PASS | Harness output (exit 1, calls: 0). grep found 1 match for the 'reviewer_prompt_guard ... // return 1' line in scripts/change-workflow.sh. |
| MC-402 | YES | PASS | Live probe output in temp dir: guard=0 launched nargs=2 lastlen=120000; guard=1 with 'prompt is 120001 bytes' message, 'not launched'. |
| MC-403 | YES | PASS | Live probe output: kind=argv for all four cases; guard=1 and 'not launched' for the three 200000-byte look-alike cases. |
| MC-404 | YES | PASS | Probe output: '/x/fake.py stagegate file guard rc 0'; '/x/fake.py change argv guard rc 1 Reviewer r: prompt is 200000 bytes, over Linux's 131,072-byt'; self_hosted.py and native_stage.py file/rc0 for both stagegate and change. Source: scripts/stagegate.sh:2360-2366, scripts/change-workflow.sh:2596-2597. |
| MC-405 | YES | FAIL | grep of reviewer_prompt_kind/reviewer_prompt_guard/prompt_kind in scripts/stagegate.sh shows only lines 2358-2372, in the non-race branch; the race function (2067-2160) has no such calls. Not executed live. |
| MC-406 | YES | PASS | Output: 'unset: kind=argv', 'empty: kind=argv', exit=0, no stderr (temp script /tmp/mc406.sh). Limitation: the launch blocks were exercised as extracted lines, not by running the full stagegate.sh/change-workflow.sh functions. |
