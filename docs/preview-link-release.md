# Preview link release handoff (issue #251)

This document lists work that is **not done in this repository**. It must be done
by a human with access to the release definition, the build-script repo and hosted
Daytona. Nothing below has been performed or verified here.

## 1. Release grant (external, not done here)

The release definition must contain a grant object with:

- `publisher`: `daytona`
- `method`: `GET`
- `path`: `/sandbox/{sandboxId}/ports/{port}/signed-preview-url`
- `require_approval`: JSON boolean `false` (only boolean false qualifies)

The grant may be a top-level object or nested in a grants list.

### Pre-publish check

Run before publishing the release:

```
python3 -B scripts/lib/check_release_grants.py <release-definition.json>
```

- Exit 0, stdout `OK`: a qualifying grant is present.
- Exit 1: valid JSON, no qualifying grant.
- Exit 2: malformed JSON, missing/unreadable file, or usage error.

Failures print a one-line reason on stderr that contains no input values. Do not
publish unless the checker prints `OK`.

## 2. Build-script requirements (external, not done here)

The build script (in the build-script repo) must:

- print `Preview: <url> (works until HH:MM UTC)` using the signed preview URL;
- use an expiry of at most 3600 seconds;
- keep the sandbox running (not delete it) after the build.

## 3. Live checks (not done here)

Issue checks 1-5 must be run by a human against hosted Daytona, and the results
posted on issue #251. No live check has been executed as part of this change.

## 4. Unchanged

`UNCLE_PREVIEW_HOST` default behavior is unchanged; `host_preview.py` is not edited.
