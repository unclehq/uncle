#!/usr/bin/env bash
# Two ways an upgrade used to break a run in progress.
#
# Observed: uncle was reinstalled while a workflow was running. `brew reinstall`
# deletes and recreates the versioned keg, and the launcher pointed at that
# versioned path, so the live driver's scripts vanished under it and it began
# failing on files that no longer existed -- hours into a run, after a human
# had already approved the plan.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/running-workflow.sh"
fail() { echo "FAIL: $1" >&2; exit 1; }

# --- the launcher must not resolve through the versioned keg ----------------
grep -q 'write_env_script opt_libexec/"uncle"' "$ROOT/Formula/uncle.rb" \
    || fail "the launcher must exec through opt_libexec, not the versioned keg"
grep -q 'write_env_script libexec/"uncle"' "$ROOT/Formula/uncle.rb" \
    && fail "the versioned keg path is back in the launcher"

# The installed formula is generated from this template, so one check covers
# both the repository copy and what an install writes.
grep -q 'Formula/uncle.rb' "$ROOT/scripts/install/build-package.py" \
    || fail "the generator no longer derives its formula from Formula/uncle.rb"

# --- a running driver is detected ------------------------------------------
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
[ -z "$(running_workflow_pids | tr -d ' ')" ] \
    || fail "no workflow should be detected before one is started"

# A process whose command line looks like a driver, which is all the detector
# can see from outside. A script, not a copied binary: macOS kills a copy of a
# signed system binary outright.
printf '#!/bin/sh\nsleep 30\n' > "$work/stagegate.sh"
chmod +x "$work/stagegate.sh"
"$work/stagegate.sh" &
fake=$!
# Give the process table a moment to show it.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    case " $(running_workflow_pids) " in *" $fake "*) break ;; esac
    sleep 0.2
done
case " $(running_workflow_pids) " in
    *" $fake "*) ;;
    *) kill "$fake" 2>/dev/null; fail "a running driver was not detected" ;;
esac
running_workflow_report 2> "$work/report.txt" || { kill "$fake" 2>/dev/null; fail "it must report a running workflow"; }
grep -q "mid-run" "$work/report.txt" || { kill "$fake" 2>/dev/null; fail "the report must say why this matters"; }
grep -q -- "--force-live" "$work/report.txt" || { kill "$fake" 2>/dev/null; fail "the report must name the override"; }

kill "$fake" 2>/dev/null || true
wait "$fake" 2>/dev/null || true

# --- and the installer honours it ------------------------------------------
grep -q "running_workflow_report" "$ROOT/install.sh" \
    || fail "install.sh must check for a running workflow"
grep -q -- "--force-live" "$ROOT/install.sh" \
    || fail "install.sh must offer the documented override"

echo 'install-safety-test.sh: launcher uses the stable path, and a live run blocks an install'
