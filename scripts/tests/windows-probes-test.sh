#!/usr/bin/env bash
set -Eeuo pipefail
trap 'status=$?; printf "FAIL: %s:%s: %s (exit %s)\n" "${BASH_SOURCE[0]}" "$LINENO" "$BASH_COMMAND" "$status" >&2; exit "$status"' ERR
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/project"
printf '#!/bin/sh\nexit 49\n' > "$work/bin/python3"
chmod +x "$work/bin/python3"
cd "$work/project"
printf 'x\n' > fixture
printf 'fixture\n' > scopes
# A Store-style executable alias must select the shell manifest fallback.
PATH="$work/bin:$PATH" bash -c '. "$1/scripts/lib/verification-integrity.sh"; verification_manifest scopes' _ "$ROOT" > actual
bash -c '. "$1/scripts/lib/verification-integrity.sh"; WORKFLOW_HASH_BACKEND=shell verification_manifest scopes' _ "$ROOT" > expected
cmp actual expected
# Unavailable process inspection must refuse installation, not report idle.
. "$ROOT/scripts/lib/running-workflow.sh"
ps() { return 2; }
OSTYPE=linux-gnu running_workflow_report 2> error
grep -q 'Cannot determine' error
unset -f ps
# The Windows branch consumes native command lines and strips CRLF.
powershell.exe() { printf '123\r\n'; }
OSTYPE=msys running_workflow_pids > ids
[[ "$(tr -d '[:space:]' < ids)" == 123 ]]
powershell.exe() { return 2; }
if OSTYPE=msys running_workflow_pids > /dev/null; then exit 1; fi
OSTYPE=msys running_workflow_report 2> error
grep -q 'refusing' error
echo 'windows-probes-test: Store alias fallback and fail-closed process checks passed'
# MSYS can report success from ln -s after copying the target. Verification
# tests must not mistake a real directory for a forbidden symlink.
mkdir -p "$work/links"
cat > "$work/links/ln" <<'LN'
#!/usr/bin/env bash
[[ "${LINK_MODE:-copy}" != refuse ]] || exit 1
[[ "$1" == -s ]] || exit 2
target="$2"
case "$target" in /*) ;; *) target="$(dirname "$3")/$target" ;; esac
cp -R "$target" "$3"
LN
chmod +x "$work/links/ln"
for mode in copy refuse; do
    PATH="$work/links:$PATH" LINK_MODE="$mode" \
        bash "$ROOT/scripts/tests/verification-integrity-test.sh" > "$work/symlink-$mode.log"
    [[ "$(grep -c '^SKIP: real symlinks unavailable' "$work/symlink-$mode.log")" == 4 ]]
    grep -q 'checks passed' "$work/symlink-$mode.log"
done
echo 'windows-probes-test: copied and unavailable symlink fixtures skip only symlink cases'
