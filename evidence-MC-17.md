# MC-17: Lock prevents concurrent upgrade installs

**Result: PASS**

## Evidence

### Test command
`bash scripts/tests/upgrade-test.sh` — full upgrade test suite (exit 0)

### Lock subtests in upgrade-test.sh

**Lock acquire/release** (lines 48–53):
```bash
run() {
  . "$ROOT/scripts/lib/upgrade-check.sh"
  "$@"
}

run upgrade_acquire_lock   # Succeeds (creates lock dir)
if run upgrade_acquire_lock; then fail 'second lock acquire did not fail'; fi
                          # Fails as expected (lock already held)
run upgrade_release_lock   # Releases lock (removes dir)
```

**Concurrent startup with lock** (lines 55–72):
```bash
GH_DELAY=1 ... upgrade_check_and_run   # first checker (delays 1s)
GH_DELAY=0 ... upgrade_check_and_run   # second checker (no delay)
```
- Two concurrent processes check for upgrade; first holds the lock, second skips
- Expects `gh.log` to have exactly 1 line (only first called `gh`)
- Verifies: `[[ "$(wc -l < "$TMP/gh.log")" -eq 1 ]]`

### Test output
```
upgrade-test.sh: version, prompt, install/re-exec, safety skips, lock, checksum warning, PTY startup, and early exits passed
```

The `lock` subtest passed alongside all other subtests.
