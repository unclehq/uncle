#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source="$ROOT/scripts/stagegate.sh"

grep -q 'checklist_acceptance=.*VERIFICATION_REPORT.json' "$source" \
    || { echo 'missing canonical checklist acceptance classification' >&2; exit 1; }
grep -q 'Checklist findings are recorded as nonblocking evidence' "$source" \
    || { echo 'checklist findings still route directly to repair' >&2; exit 1; }
grep -q 'record_nonblocking_failure VERIFICATION_REPORT.json' "$source" \
    || { echo 'continued checklist findings are not recorded for audit' >&2; exit 1; }
grep -q 'continue_nonblocking_test_review()' "$source" \
    || { echo 'missing canonical test-review continuation helper' >&2; exit 1; }
grep -q 'continue_nonblocking_test_review FINAL_AUDIT' "$source" \
    || { echo 'final audit can still route nonblocking test review to repair' >&2; exit 1; }
echo 'checklist-continue-test.sh: passing green checks continue checklist evidence to audit'
