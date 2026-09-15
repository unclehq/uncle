# Shared stage evidence index

The prompt builder uses `scripts/lib/evidence_index.py` to generate bounded
stage-specific input packets. It replaces the separate packet injections;
standalone helpers remain available for compatibility and document validation.

Each invocation hashes the selected files again. Parsed excerpts are stored by
content hash under `.uncle/workflow/evidence-index/objects`. Atomic per-stage
snapshots in `stages` contain paths, hashes, sizes, changed inputs, missing files,
and excerpt-cache hit counts. Concurrent stages use separate snapshots and
atomic object writes. A changed or deleted file cannot reuse its old excerpt.

The base manual checklist reads only its frozen specification and plan. Other
stages receive relevant reports and project tooling metadata. Credentials and
private model configuration are not included. Packets are bounded to roughly
16 KB; the model must read omitted requirements and exact evidence directly.

The index caches navigation, not test outcomes, approvals, environment probes,
or reviewer conclusions. Existing check runners and result drafts still execute
and record their own evidence. Runtime changes must still be verified by those
runners. File hashing remains necessary; the cache saves excerpt processing and
repeated model discovery, not all disk reads. Performance gains need measurement
on an installed run.
