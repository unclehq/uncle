#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/install/scripts" "$TMP/project with spaces" "$TMP/bin"
cp "$ROOT/scripts/from-issue.sh" "$TMP/install/scripts/"
cp -R "$ROOT/scripts/lib" "$TMP/install/scripts/"
printf 'Installation sentinel\n' > "$TMP/install/CHANGE_REQUEST.md"
cat > "$TMP/bin/gh" <<'GH'
#!/usr/bin/env bash
[[ "$*" == 'issue view 42 --repo example/project --json title,body,url,state,labels' ]] || exit 1
printf '%s\n' '{"title":"Selected issue","body":"Exact issue body\n\n## Details\nKeep this text.","url":"https://github.com/example/project/issues/42"}'
GH
chmod +x "$TMP/bin/gh"
UNCLE_PROJECT_ROOT="$TMP/project with spaces" PATH="$TMP/bin:$PATH" \
    bash "$TMP/install/scripts/from-issue.sh" https://github.com/example/project/issues/42 --change < /dev/null > "$TMP/output"
grep -q '^Selected issue$' "$TMP/project with spaces/CHANGE_REQUEST.md"
grep -q '^Keep this text\.$' "$TMP/project with spaces/CHANGE_REQUEST.md"
grep -q 'example/project#42' "$TMP/project with spaces/CHANGE_REQUEST.md"
[[ "$(cat "$TMP/install/CHANGE_REQUEST.md")" == 'Installation sentinel' ]]
[[ ! -e "$TMP/install/.uncle" ]]
echo 'issue-project-root-test: passed'
