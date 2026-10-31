#!/usr/bin/env bash
# The Python regression suites (scripts/tests/*-test.py), each in its own process, several at once. run-shell-tests.sh does
# not run these. Use this, not `python3 -m unittest discover`, which runs the same files serially in one process.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$ROOT"
jobs="${WORKFLOW_VERIFY_JOBS:-4}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-root) project="$2"; shift 2 ;;
        --jobs) jobs="$2"; shift 2 ;;
        --) shift; break ;;
        *) echo "Usage: bash scripts/run-python-tests.sh [--jobs 1-16] [--project-root path] [-- suite ...]" >&2; exit 2 ;;
    esac
done
cd "$project"
exec python3 -B "$ROOT/scripts/lib/python_suites.py" "$jobs" "$@"
