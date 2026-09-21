#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $1" >&2; exit 1; }

mkdir -p "$TMP/root/scripts/lib" "$TMP/bin" "$TMP/marker"
cp "$ROOT/scripts/lib/upgrade-check.sh" "$TMP/root/scripts/lib/upgrade-check.sh"
cp "$ROOT/scripts/lib/running-workflow.sh" "$TMP/root/scripts/lib/running-workflow.sh"
printf '0.0.1\n' > "$TMP/root/VERSION"
printf '%s\n' '#!/usr/bin/env bash' "printf '%s:%s\\n' \"\$*\" \"\${UNCLE_ALLOW_LIVE_INSTALL:-}\" > \"\$TEST_MARKER/install\"" > "$TMP/root/install.sh"
printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' \"\$*\" > \"\$TEST_MARKER/reexec\"" > "$TMP/root/uncle"
chmod +x "$TMP/root/install.sh" "$TMP/root/uncle"
printf '%s\n' '#!/usr/bin/env bash' \
  'if [[ "$1 $2" == "release view" ]]; then' \
  '  [[ -z "${GH_LOG:-}" ]] || printf "gh\\n" >> "$GH_LOG"' \
  '  [[ -z "${GH_DELAY:-}" ]] || sleep "$GH_DELAY"' \
  '  [[ "${GH_MODE:-online}" != offline ]] || exit 1' \
  '  printf "%s\\n" "${GH_TAG:-v9.9.9}"; exit 0' \
  'fi' \
  'if [[ "$1 $2" == "release download" ]]; then' \
  '  while [[ $# -gt 0 ]]; do [[ "$1" == --dir ]] && { shift; target="$1"; break; }; shift; done' \
  '  mkdir -p "$target/uncle-v9.9.9"' \
  '  tar -czf "$target/uncle-v9.9.9.tar.gz" -C "$target" uncle-v9.9.9' \
  '  rm -rf "$target/uncle-v9.9.9"' \
  'fi' > "$TMP/bin/gh"
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "$TMP/bin/curl"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$TMP/bin/ps"
chmod +x "$TMP/bin/gh" "$TMP/bin/curl" "$TMP/bin/ps"

run() { TEST_MARKER="$TMP/marker" GH_LOG="$TMP/gh.log" ROOT="$TMP/root" UNCLE_UPGRADE_LOCK_DIR="${UNCLE_UPGRADE_LOCK_DIR:-}" PATH="$TMP/bin:$PATH" bash -c '. "$ROOT/scripts/lib/upgrade-check.sh"; "$@"' -- "$@"; }
run upgrade_available '0.2.0+gitabc' v0.2.0 || fail 'dev build was not older than the clean release'
if run upgrade_available 0.2.0 v0.2.0; then fail 'same version was offered'; fi
if run upgrade_available 9.0.0 v0.2.0; then fail 'newer local version was offered'; fi
run upgrade_fetch_latest_tag | grep -qx v9.9.9 || fail 'release lookup did not use gh tag'
if GH_MODE=offline run upgrade_fetch_latest_tag; then fail 'offline lookup returned a release'; fi
timeout_start=$SECONDS
if run upgrade_run_with_timeout bash -c 'sleep 6'; then fail 'slow release lookup did not time out'; fi
(( SECONDS - timeout_start <= 6 )) || fail 'release lookup exceeded five-second timeout'

# A missing optional checksum warns but does not prevent installation.
mkdir -p "$TMP/no-checksum"
run upgrade_verify_checksum "$TMP/no-checksum" v9.9.9 > "$TMP/no-checksum.out" 2>&1 || fail 'missing checksum blocked upgrade'
grep -qx 'Warning: no checksum file for v9.9.9; skipping verification' "$TMP/no-checksum.out" || fail 'missing checksum did not warn on stderr'

# The startup lock admits one checker and makes a concurrent checker skip.
export UNCLE_UPGRADE_LOCK_DIR="$TMP/upgrade.lock"
run upgrade_acquire_lock || fail 'first upgrade lock acquisition failed'
if run upgrade_acquire_lock; then fail 'second upgrade lock acquisition succeeded'; fi
run upgrade_release_lock
unset UNCLE_UPGRADE_LOCK_DIR
[[ ! -e "$TMP/upgrade.lock" ]] || fail 'upgrade lock was not released'

# A second startup skips the release fetch while the first owns the lock.
concurrent_lock="$TMP/concurrent-upgrade.lock"
rm -f "$TMP/gh.log"
GH_DELAY=1 GH_LOG="$TMP/gh.log" TEST_MARKER="$TMP/marker" ROOT="$TMP/root" UNCLE_UPGRADE_LOCK_DIR="$concurrent_lock" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_should_check() { return 0; }
  upgrade_check_and_run <<< n
' >/dev/null &
first_checker=$!
for _ in {1..100}; do [[ -e "$TMP/gh.log" ]] && break; sleep 0.05; done
[[ -e "$TMP/gh.log" ]] || fail 'first concurrent startup did not begin its release fetch'
GH_LOG="$TMP/gh.log" TEST_MARKER="$TMP/marker" ROOT="$TMP/root" UNCLE_UPGRADE_LOCK_DIR="$concurrent_lock" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_should_check() { return 0; }
  upgrade_check_and_run <<< n
' >/dev/null
wait "$first_checker"
[[ "$(wc -l < "$TMP/gh.log")" -eq 1 ]] || fail 'concurrent startup performed more than one release fetch'

# Same versions do not prompt, while a declined newer version leaves installation untouched.
same_output="$(printf 'n\n' | GH_TAG=v0.0.1 TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_should_check() { return 0; }
  upgrade_check_and_run
')"
[[ "$same_output" != *'Install? [y/N]'* ]] || fail 'same version showed an upgrade prompt'
decline_output="$(printf 'n\n' | TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_should_check() { return 0; }
  upgrade_check_and_run
')"
[[ "$decline_output" == *'A new version 9.9.9 is available (you have 0.0.1). Install? [y/N]'* ]] || fail 'newer version did not show the upgrade prompt'
[[ ! -e "$TMP/marker/install" ]] || fail 'decline invoked installation'

# Acceptance invokes install.sh and replaces the process with the launcher.
UNCLE_UPGRADE_LOCK_DIR="$TMP/reexec.lock"
mkdir "$UNCLE_UPGRADE_LOCK_DIR"
TEST_MARKER="$TMP/marker" ROOT="$TMP/root" UNCLE_UPGRADE_LOCK_DIR="$UNCLE_UPGRADE_LOCK_DIR" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  UNCLE_ORIGINAL_ARGS=(--unattended)
  upgrade_download_and_install 0.0.1 v9.9.9
'
grep -q '^--source-dir ' "$TMP/marker/install" || fail 'accept did not invoke install.sh --source-dir'
grep -q ':1$' "$TMP/marker/install" || fail 'install did not bypass its self-detection after the workflow guard'
grep -qx -- '--unattended' "$TMP/marker/reexec" || fail 'accept did not re-exec with original arguments'
[[ ! -e "$UNCLE_UPGRADE_LOCK_DIR" ]] || fail 'successful install left the startup lock behind'
unset UNCLE_UPGRADE_LOCK_DIR

rm -f "$TMP/marker/reexec"
if TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  gh() { return 1; }
  upgrade_download_and_install 0.0.1 v9.9.9
' > "$TMP/install-failure.out" 2>&1; then fail 'failed download reported success'; fi
grep -q 'Upgrade download failed' "$TMP/install-failure.out" || fail 'failed download did not report an error'
[[ ! -e "$TMP/marker/reexec" ]] || fail 'failed install re-execed'

if TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  tar() { return 1; }
  upgrade_download_and_install 0.0.1 v9.9.9
' > "$TMP/extract-failure.out" 2>&1; then fail 'failed extraction reported success'; fi
grep -q 'Upgrade extraction failed' "$TMP/extract-failure.out" || fail 'failed extraction did not report an error'

printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "$TMP/root/install.sh"
chmod +x "$TMP/root/install.sh"
if TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_download_and_install 0.0.1 v9.9.9
' > "$TMP/install-script-failure.out" 2>&1; then fail 'failed installer reported success'; fi
grep -q 'Upgrade installation failed' "$TMP/install-script-failure.out" || fail 'failed installer did not report an error'

TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" UNCLE_SKIP_UPGRADE=1 bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  upgrade_should_check
' && fail 'UNCLE_SKIP_UPGRADE did not disable checks'
TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  UNCLE_ARGS=(--unattended)
  upgrade_should_check
' && fail 'unattended mode did not disable checks'
if script -q "$TMP/running-workflow.out" env TEST_MARKER="$TMP/marker" ROOT="$TMP/root" PATH="$TMP/bin:$PATH" bash -c '
  . "$ROOT/scripts/lib/upgrade-check.sh"
  running_workflow_pids() { printf "%s " 12345; }
  upgrade_should_check
'; then fail 'running workflow did not disable checks'; fi

rm -f "$TMP/gh.log"
GH_LOG="$TMP/gh.log" PATH="$TMP/bin:$PATH" bash "$ROOT/uncle" --help > "$TMP/help.out"
grep -q 'Usage: uncle' "$TMP/help.out" || fail 'help did not print usage'
[[ ! -e "$TMP/gh.log" ]] || fail 'help checked for upgrades'
for early in --runs verify --performance; do
  rm -f "$TMP/gh.log"
  GH_LOG="$TMP/gh.log" PATH="$TMP/bin:$PATH" bash "$ROOT/uncle" "$early" >/dev/null 2>&1 || true
  [[ ! -e "$TMP/gh.log" ]] || fail "$early checked for upgrades"
done
GH_LOG="$TMP/gh.log" PATH="$TMP/bin:$PATH" bash "$ROOT/uncle" --help > "$TMP/help.out"
grep -q 'UNCLE_SKIP_UPGRADE=1 skips the interactive startup upgrade check' "$TMP/help.out" || fail 'help did not document UNCLE_SKIP_UPGRADE'

# A pseudoterminal reaches the startup prompt before the TUI; a fake Python
# exits immediately after a declined prompt so this test remains noninteractive.
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$TMP/bin/python3"
chmod +x "$TMP/bin/python3"
rm -f "$TMP/gh.log"
if ! printf 'n\n' | script -q "$TMP/pty.out" env GH_LOG="$TMP/gh.log" PATH="$TMP/bin:$PATH" bash "$ROOT/uncle" >/dev/null 2>&1; then
  fail 'interactive startup under a pseudoterminal failed'
fi
grep -q 'Install? \[y/N\]' "$TMP/pty.out" || fail 'pseudoterminal startup did not show upgrade prompt'
rm -f "$TMP/gh.log"
PATH="$TMP/bin:$PATH" bash "$ROOT/uncle" --help > /dev/null
[[ ! -e "$TMP/gh.log" ]] || fail 'help checked for upgrades under pty coverage'
echo 'upgrade-test.sh: version, prompt, install/re-exec, safety skips, lock, checksum warning, PTY startup, and early exits passed'
