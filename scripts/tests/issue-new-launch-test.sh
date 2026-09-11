#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/install/scripts" "$tmp/bin"
cp "$ROOT/scripts/from-issue.sh" "$tmp/install/scripts/"
cp -R "$ROOT/scripts/lib" "$tmp/install/scripts/"
cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
printf '%s\n' '{"title":"Build an app","body":"App requirements","url":"https://github.com/example/project/issues/12"}'
GH
chmod +x "$tmp/bin/gh"
cat > "$tmp/install/scripts/stagegate.sh" <<'DRIVER'
#!/usr/bin/env bash
[[ -s REQUIREMENTS.md ]]
printf '%s\n' "$PWD" "$@" > called
exit "${TEST_DRIVER_EXIT:-0}"
DRIVER
for status in 0 7; do
    project="$tmp/project $status"
    mkdir "$project"
    result=0
    PATH="$tmp/bin:$PATH" UNCLE_PROJECT_ROOT="$project" TEST_DRIVER_EXIT="$status" \
        bash "$tmp/install/scripts/from-issue.sh" https://github.com/example/project/issues/12 --new --unattended > "$tmp/output" 2>&1 || result=$?
    [[ "$result" == "$status" ]]
    grep -qFx -- "$project" "$project/called"
    grep -qFx -- '--unattended' "$project/called"
    [[ ! -e "$tmp/install/REQUIREMENTS.md" ]]
done
echo 'issue-new-launch-test: passed'
