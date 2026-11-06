#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$ROOT"
jobs="$(python3 -B "$ROOT/scripts/lib/cpu_jobs.py" tests)"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-root) project="$2"; shift 2 ;;
        --jobs) jobs="$2"; shift 2 ;;
        --all) export WORKFLOW_TEST_TIER=all; shift ;;
        --) shift; break ;;
        *) echo "Usage: bash scripts/run-shell-tests.sh [--all] [--jobs 1-64] [--project-root path] [-- suite ...]" >&2; exit 2 ;;
    esac
done
cd "$project"
exec python3 -B "$ROOT/scripts/lib/shell_suites.py" "$jobs" "$@"
