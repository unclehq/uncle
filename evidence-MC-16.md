# MC-16: Dev build: same clean release not offered as upgrade

**Result: FAIL**

## Evidence

### Test command
`bash scripts/tests/upgrade-test.sh` — full upgrade test suite (exit 0)

### Targeted verification
Direct call to `upgrade_available` with dev build and same clean release:

```
$ . scripts/lib/upgrade-check.sh && upgrade_available "0.0.1+gitabc" v0.0.1
exit code: 0 (UPGRADE_OFFERED)
```

### Root cause
`scripts/lib/upgrade-check.sh:24` — `[[ -n "${local_values[3]}" && -z "${latest_values[3]}" ]] && return 0`

- When local version has a suffix (`+gitabc`) and latest tag has no suffix, return 0 (upgrade offered)
- This means a dev build IS offered as upgrade to the clean release of the same base version

### Existing test coverage (lines 74–80 of upgrade-test.sh)
Tests only the "clean same-version" scenario (VERSION=`0.0.1`, GH_TAG=`v0.0.1`). Verifies no prompt. Passes. Does NOT cover the dev-build-same-version scenario.

### Conclusion
Implementation contradicts MC-16: dev build `X.Y.Z+gitabc` IS offered as upgrade to clean release `vX.Y.Z`.
