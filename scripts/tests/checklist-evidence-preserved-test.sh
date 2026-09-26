#!/usr/bin/env bash
# prompts/change/execute-change-checklist.md asks the execute stage for
# Markdown only -- .uncle/docs/VERIFICATION_REPORT.md and .uncle/docs/DEFECTS.md.
# It never names a canonical JSON. So a run's real verification evidence lives
# in that Markdown.
#
# checklist_report_fallback --missing-only carefully preserved those Markdown
# files, then unconditionally overwrote all three canonical JSON artifacts with
# "NOT RUN" rows. VALIDATE_CHECKLIST re-renders the Markdown from
# EXECUTE_CHECKLIST.json, so the fabricated rows overwrote the very report that
# had just been preserved. A real run executed every check, wrote its report,
# and still reached the audit as 42 of 42 NOT RUN / "Not recorded" -- which is
# what produced its NOT READY verdict.
#
# export_from_markdown already parses that report. Use it, and never infer a
# status the report did not state.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

project="$work/project"
mkdir -p "$project/.uncle/docs" "$project/.uncle/workflow/documents"
cd "$project"

fail() { echo "checklist-evidence-preserved-test.sh: FAIL: $*" >&2; exit 1; }

cat > .uncle/docs/MANUAL_CHECKLIST.md <<'MD'
# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exact action: Open the page
- Expected result: Greeting visible
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exact action: Call the endpoint
- Expected result: 200 with two booleans
- Status: NOT RUN

### MC-102
- Required for acceptance: NO
- Exact action: Start the app
- Expected result: Ready on 8765
- Status: NOT RUN
MD

# What the execute stage actually delivers: its own report, in Markdown.
cat > .uncle/docs/VERIFICATION_REPORT.md <<'MD'
# Verification report

## Findings

### MC-100
- **Action:** Opened / with devtools open
- **Expected result:** Greeting visible
- **Actual result:** Greeting rendered; no voice affordances present
- **Defects:** None

### MC-101
- **Action:** curl -i /api/admin/login-options
- **Expected result:** 200 with two booleans
- **Actual result:** 200, {"voice_login":false,"voice_only_login":false}
- **Defects:** None

### MC-102
- **Action:** .venv/bin/python -m app --port 8765
- **Expected result:** Ready on 8765
- **Actual result:** Model faster-whisper-base not downloaded
- **Defects:** D-1

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | PASS | Screenshot and DOM query recorded |
| MC-101 | YES | PASS | curl transcript recorded |
| MC-102 | NO | BLOCKED | Model absent; startup could not be reached |
MD
printf '# Defects\n\n## D-1\n\n- **Status:** open\n' > .uncle/docs/DEFECTS.md

report_before="$(shasum -a 256 .uncle/docs/VERIFICATION_REPORT.md | awk '{print $1}')"

python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only \
    || fail 'the fallback errored on a delivered report'

# VALIDATE_CHECKLIST re-renders the Markdown from the canonical artifact right
# after the fallback runs; that round trip must not lose the results.
python3 -c "
import importlib.util
s = importlib.util.spec_from_file_location('r', '$ROOT/scripts/lib/checklist_report_fallback.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.render_from_json('.')" || fail 'render_from_json failed'

python3 - <<'PY' || exit 1
import json, sys
from pathlib import Path


def bad(message):
    print('checklist-evidence-preserved-test.sh: FAIL: ' + message, file=sys.stderr)
    raise SystemExit(1)


results = json.loads(Path('.uncle/workflow/documents/EXECUTE_CHECKLIST.json').read_text())['results']
status = {row['id']: row['status'] for row in results}
if status != {'MC-100': 'PASS', 'MC-101': 'PASS', 'MC-102': 'BLOCKED'}:
    bad('EXECUTE_CHECKLIST.json lost the reported statuses: %r' % status)

required = {row['id']: row['required'] for row in results}
if required != {'MC-100': True, 'MC-101': True, 'MC-102': False}:
    bad('required flags were not carried over: %r' % required)

row = next(r for r in results if r['id'] == 'MC-102')
if 'faster-whisper-base' not in (row.get('actual_result') or ''):
    bad('per-check findings were dropped: %r' % row)
if row.get('defect_ids') != ['D-1']:
    bad('defect ids were dropped: %r' % row)

rows = json.loads(Path('.uncle/workflow/documents/VERIFICATION_REPORT.json').read_text())['rows']
acceptance = {r['id']: r['status'] for r in rows}
if acceptance != status:
    bad('VERIFICATION_REPORT.json disagrees with the executed results: %r' % acceptance)

text = Path('.uncle/docs/VERIFICATION_REPORT.md').read_text()
if 'Not recorded' in text:
    bad('the re-rendered report replaced real evidence with "Not recorded"')
for fragment in ('curl transcript recorded', 'faster-whisper-base'):
    if fragment not in text:
        bad('the re-rendered report lost: ' + fragment)
PY

# Absent evidence must still never become a PASS.
rm -rf "$work/empty"; mkdir -p "$work/empty/.uncle/docs" "$work/empty/.uncle/workflow/documents"
cp .uncle/docs/MANUAL_CHECKLIST.md "$work/empty/.uncle/docs/"
( cd "$work/empty"
  python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only >/dev/null ) \
    || fail 'the fallback errored with no delivered report'
python3 - "$work/empty" <<'PY' || exit 1
import json, sys
from pathlib import Path
results = json.loads((Path(sys.argv[1]) / '.uncle/workflow/documents/EXECUTE_CHECKLIST.json').read_text())['results']
if {r['status'] for r in results} != {'NOT RUN'}:
    print('checklist-evidence-preserved-test.sh: FAIL: a missing report must record NOT RUN, got %r'
          % {r['status'] for r in results}, file=sys.stderr)
    raise SystemExit(1)
PY

[[ "$report_before" != "$(shasum -a 256 .uncle/docs/VERIFICATION_REPORT.md | awk '{print $1}')" ]] \
    || echo '  (note: the delivered report round-tripped byte-identical)'

echo 'checklist-evidence-preserved-test.sh: executed checklist results survive into the canonical artifacts'
