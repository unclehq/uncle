#!/usr/bin/env bash
set -euo pipefail
# Fails on any case-insensitive 'cline' in a tracked file outside the allowlist.
# 'decline' (and 'inclined' etc.) is a different word and is not a hit.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# Allowed: the D1/D2 removal message (and its tests), the chat.py .cline sandbox
# deny entry, historical ledger tolerance, this test, the tests that assert the
# rejection (and the two that use the real issue's title or an old ledger row as a
# fixture), the request and plan docs, and the audit report of the removal itself.
ALLOW_FILES='^(scripts/tests/(no-cline-references|tui-config|checklist-runner-config|runner-validation|stage-runner|supervisor|native-steering|stage-billing|ledger-tolerance|origin-self-heal)-test\.(sh|py)|CHANGE_REQUEST\.md|FINAL_AUDIT\.md|\.uncle/.*)$'
ALLOW_LINE='== .?cline.?( |:|$)|removal text only for cline|Cline support was removed|\.cline|cline-usage|clinepass|runner .?cline|runner.cline|cline.*(removed|unsupported|unknown|legacy|stale)|(removed|unsupported|legacy|stale).*cline'
hits="$(git ls-files -z | xargs -0 grep -InoiE '(^|[^a-z])cline([^a-z]|$)' 2>/dev/null \
    | grep -vE "$ALLOW_FILES" | awk -F: '{print $1":"$2}' | sort -u || true)"
bad=""
while IFS=: read -r f n; do
    [[ -n "$f" ]] || continue
    [[ "$f" =~ $ALLOW_FILES ]] && continue
    line="$(sed -n "${n}p" "$f")"
    if printf '%s' "$line" | grep -qiE "$ALLOW_LINE"; then continue; fi
    bad+="$f:$n: ${line:0:100}"$'\n'
done <<< "$hits"
if [[ -n "$bad" ]]; then
    echo "FAIL: unexpected cline references:"; printf '%s' "$bad" | head -60
    echo "total: $(printf '%s' "$bad" | grep -c .)"; exit 1
fi
echo "no-cline-references-test: ok"
