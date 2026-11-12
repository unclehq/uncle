# Verifying a change (`uncle verify`)

`uncle verify` checks a change attestation against the Git tree it claims to describe. This page is the reference. The short version is in the [README](../README.md#verifiable-change-provenance).

## Usage

```sh
uncle verify                 # the attestation on the main branch (falls back to the current checkout when main has none)
uncle verify 123             # a pull request by number or URL (needs gh)
uncle verify --tree <commit> # a specific commit or tree
```

The verifier is also a single file with no dependencies beyond Python and `git`, so a change can be checked without installing Uncle:

```sh
curl -fsSLO https://raw.githubusercontent.com/unclehq/uncle/main/scripts/uncle-verify.py
python3 uncle-verify.py 123
```

Run it inside a clone of the repository. For a pull request it reads the attestation from the PR head commit, so that commit must already be fetched (`git fetch origin pull/123/head`). `gh` is required only to resolve a PR number.

Options: `--attestation PATH` (default `.uncle/attestation.json`), `--tree REF`, `--allowed-signers PATH` (default `.uncle/allowed_signers`), `--certificate-identity` and `--certificate-oidc-issuer` (for Sigstore signatures).

## What gets written

When a change completes, the driver writes two files into the change. A new-application build does the same at completion (`scripts/lib/build_attestation.py`), from its own approval records, review and plan documents, green-check results and audit verdict, so the local merge carries them to the source branch. A new-application build is attested for every completed build, including one that completed over an override or whose verification or audit did not pass. What it attests is that the procedure was followed, not that the build is correct or ready: the stage results, the audit verdict and any override are recorded and printed by `uncle verify`, never judged. A `VERIFIED` result on such a record means it is authentic and bound to the tree, not that the change should be released, so do not treat it as release approval. A change made through the change workflow is stricter, as check 5 describes.

* `.uncle/attestation.json`: an [in-toto](https://in-toto.io/) Statement (`https://in-toto.io/Statement/v1`) with predicate type `https://uncle.dev/attestation/v1`, serialized as RFC 8785 canonical JSON so its hash and signature are reproducible.
* `.uncle/attestation.sig`: a DSSE envelope (payload type `application/vnd.in-toto+json`) over those exact bytes. Present only when a signer was available.

The driver writes both from validator exit codes, gate records and its own hashing. No model writes an envelope or the attestation. Evidence that is missing or malformed is recorded as `unavailable`, never inferred.

Stages recorded: requirements, review, plan, implementation, verification, audit, release. Each result is `pass`, `fail` or `unavailable`. For review, verification and audit, both `fail` and `unavailable` block.

## Signing

Uncle creates no new key material. It signs with the first of these that is configured:

1. Sigstore: `cosign` on the PATH with git's `gpg.x509.program` set to `gitsign`.
2. SSH: git's own SSH signing (`gpg.format = ssh` and `user.signingkey`), through `ssh-keygen -Y sign` with the namespace `uncle-attestation`.

With neither, the attestation is written unsigned.

## What the checks do

In order, and stopping at the first failure:

| # | Check |
|---|---|
| 1 | The attestation is canonical JSON, an in-toto Statement, schema v1, and has a git-tree subject digest. |
| 2 | The signature, if any. A valid signature against a trust root you supply gives `VERIFIED`. With no signature, no trust root, or a missing `ssh-keygen`/`cosign`, the result is integrity only. A signature that is present but invalid fails. |
| 3 | Each approved document's SHA-256 matches the copy committed in the tree (or the copy embedded in the attestation). |
| 4 | The implementation, verification input and audit input all name the same Git tree as the release artifact. |
| 5 | For a change-workflow attestation, the review, verification and audit stages each recorded `pass`. For a new-application build (procedure attestation), every stage ran, each recorded `pass` or `fail`, and the build's procedure result is `pass`. Failed stage results, a `NOT_READY` verdict and an override are printed, not refused. |
| 6 | Every blocking review finding has a recorded disposition. |
| 7 | Every required gate was approved by a person, or was deliberately left to an unattended run. An `unattended` gate is reported (`○`, exit 3, not human verified) rather than refused; a gate approved by `supervisor:*` or `disabled:*` is refused. |
| 8 | The head tree, minus Uncle's own working files, equals the release artifact and the attestation subject. |

## Exit codes

| Exit | Meaning |
|---|---|
| 0 | `VERIFIED`: all checks passed and the signature is valid against a trust root you supplied. |
| 1 | `NOT VERIFIED`: a check failed or the change was refused. |
| 2 | Usage error, or a required tool (such as `git`) is missing. |
| 3 | Integrity only: all checks passed, but there is no signature, the signature is untrusted, or an optional tool is missing. |

## What each result does and does not tell you

These are different guarantees:

* **Artifact integrity.** The tree you have is the tree that was reviewed, verified, approved and released (checks 3, 4 and 8). An unsigned attestation lives in the same repository as the code, so someone who can change the code can also rewrite it. Integrity alone does not say who produced the attestation.
* **Signature authenticity.** The attestation was signed by a key you trust (check 2). This needs a trust root you provide (`.uncle/allowed_signers` or a Sigstore identity). Exit 0 requires it; exit 3 means you did not get it.
* **Review and verification evidence.** The stages recorded `pass` and the required people approved (checks 5 to 7). This records what Uncle observed, not whether the reviewer or the tests were any good.
* **Software correctness.** Not covered. A verified change can still contain bugs or security flaws.

## Limits

* A change built in the default unattended mode records its gates as delegated. Check 7 reports them as made unattended, and the result is `NOT HUMAN VERIFIED` (exit 3) instead of a failure. Use `--attended` when you want human approvals recorded.
* The attestation currently committed to this repository has no `.sig` file and the repository has no `allowed_signers` trust root, so verifying it can give at best exit 3.
