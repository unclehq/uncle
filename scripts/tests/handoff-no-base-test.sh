#!/usr/bin/env bash
# Hand-off in a commit-less repository (T-2a/T-2b/T-2c, T-3 signing negative test).
# Fixtures: temp repos with no commits, signing disabled locally, no remote, no gh.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0; n=0
ok() { n=$((n+1)); echo "ok - $1"; }
bad() { n=$((n+1)); fails=$((fails+1)); echo "not ok - $1"; }
check() { local d="$1"; shift; if "$@"; then ok "$d"; else bad "$d"; fi; }

# Hostile inherited environment: global config demands signing through a fake signer that records and fails.
export HOME="$TMP/home"; mkdir -p "$HOME"
REC="$TMP/signer.log"; : > "$REC"
cat > "$TMP/fake-gpg" <<SH
#!/usr/bin/env bash
echo "invoked: \$*" >> "$REC"
exit 1
SH
chmod +x "$TMP/fake-gpg"
cat > "$TMP/gitconfig" <<CFG
[commit]
	gpgsign = true
[tag]
	gpgsign = true
[gpg]
	program = $TMP/fake-gpg
CFG
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
unset UNCLE_RUN_POLICY WORKFLOW_WORKTREE UNCLE_PROJECT_ROOT_LOCKED

mkrepo() { local d="$TMP/$1"; mkdir -p "$d"; (cd "$d" && git init -q -b main && git config commit.gpgsign false && git config tag.gpgsign false && echo x > app.txt); echo "$d"; }
refs() { git -C "$1" for-each-ref --format='%(refname) %(objectname)'; git -C "$1" symbolic-ref -q HEAD; git -C "$1" rev-parse -q --verify HEAD 2>&1; }
seed() { local d="$1"; shift; (cd "$d" && env "$@" bash -c 'source "$1"; run_policy_snapshot_base; echo "rc=$?"' _ "$ROOT/scripts/lib/run-policy.sh") 2>&1; }

# T-2a: successful seed in hand-off mode, under hostile signing config.
d="$(mkrepo ok)"
out="$(seed "$d" UNCLE_PUBLISH_MODE=handoff)"
check "T-2a seed succeeds (rc=0)" grep -q 'rc=0' <<<"$out"
check "T-2a base ref created" git -C "$d" rev-parse -q --verify refs/uncle/handoff-base
check "T-2a HEAD stays unborn" bash -c '! git -C "$1" rev-parse -q --verify HEAD >/dev/null' _ "$d"
check "T-3 fake signer never invoked" test ! -s "$REC"
check "T-3 base commit is unsigned" bash -c '! git -C "$1" cat-file commit refs/uncle/handoff-base | grep -q "^gpgsig"' _ "$d"

# Non-hand-off run leaves refs and HEAD untouched.
d="$(mkrepo plain)"; before="$(refs "$d")"
seed "$d" >/dev/null
check "non-hand-off run: HEAD and refs unchanged" test "$before" = "$(refs "$d")"
check "T-3 signer still never invoked" test ! -s "$REC"

# T-2b: injected seed failure -> no base, HEAD absent.
d="$(mkrepo fail)"; mkdir -p "$TMP/shim"; rg="$(command -v git)"
cat > "$TMP/shim/git" <<SH
#!/usr/bin/env bash
for a in "\$@"; do [[ "\$a" == commit-tree ]] && { echo injected >&2; exit 1; }; done
exec "$rg" "\$@"
SH
chmod +x "$TMP/shim/git"
out="$(seed "$d" UNCLE_PUBLISH_MODE=handoff PATH="$TMP/shim:$PATH")"
check "T-2b failed seed still returns 0" grep -q 'rc=0' <<<"$out"
check "T-2b HEAD stays absent" bash -c '! git -C "$1" rev-parse -q --verify HEAD >/dev/null' _ "$d"
check "T-2b no base ref" bash -c '! git -C "$1" rev-parse -q --verify refs/uncle/handoff-base >/dev/null' _ "$d"
check "T-2b no handoff.json written" test ! -e "$d/.uncle/handoff.json"

# D-2/D-3 wording contracts (artifact-conditional completion text; no-base message).
AV="$ROOT/scripts/lib/audit-verdict.sh"; CW="$ROOT/scripts/change-workflow.sh"
check "D-2 completion text points to FINAL_AUDIT.md fallback" grep -q 'FINAL_AUDIT.md' "$AV"
check "D-2 completion text conditional on handoff.json existing" grep -Eq 'handoff\.json' "$AV"
check "D-3 no-base hand-off message present" grep -Eiq 'no hand-?off record' "$CW"
check "T-3 signing disabled explicitly in seed" grep -Eq 'gpgsign=false|--no-gpg-sign' "$ROOT/scripts/lib/run-policy.sh"

echo "# $n checks, $fails failed"
test "$fails" -eq 0
