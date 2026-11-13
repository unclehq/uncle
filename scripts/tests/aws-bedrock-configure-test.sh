#!/usr/bin/env bash
# Fallback line menu of `uncle`: Configure AWS Bedrock (AC-1, AC-2, AC-3, AC-4).
# Drives the real shipped `uncle` script over piped stdin (non-TTY -> line menu).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
TOKEN=bedrock-sentinel-token-7731
SHTOKEN=selfhosted-sentinel-token-1188
URL=https://bedrock.example.com/openai/v1
STAGES="requirements change-spec project-plan change-plan adversarial-review updated-plan updated-change-plan preflight implementation repair test-review manual-checklist execute-checklist final-audit"
fails=0
ok() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fails=$((fails+1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# Tool-only PATH (no agent CLIs) and one with stub claude + codex.
mkdir -p "$T/minbin" "$T/stubbin"
for tool in bash python3 env tr cat mktemp rm dirname readlink sed grep awk date mkdir cp mv head tail cut sort uname basename ls wc printf git sleep id tee find xargs chmod touch stat; do
  p=$(command -v "$tool" 2>/dev/null) && [ -x "$p" ] && ln -sf "$p" "$T/minbin/$tool"
  [ -e "$T/minbin/$tool" ] && ln -sf "$p" "$T/stubbin/$tool"
done
for stub in claude codex; do printf '#!/bin/sh\nexit 0\n' >"$T/stubbin/$stub"; chmod +x "$T/stubbin/$stub"; done

new_project() { # name -> dir with .uncle/config seeded by caller
  P="$T/$1"; mkdir -p "$P/.uncle"; CFG="$P/.uncle/config"; BK="$P/.uncle/aws-bedrock-keys.json"; SK="$P/.uncle/self-hosted-keys.json"
}
seed_keys() { # bedrock key file: model, connection, token on implementation
  python3 - "$BK" "$TOKEN" "$URL" <<'PY'
import json, sys
json.dump({'__opencode_models__': {'anthropic.claude-x': {'model': 'anthropic.claude-x', 'base_url': sys.argv[3]}},
           '__opencode_connection__': {'base_url': sys.argv[3]}, 'implementation': sys.argv[2]}, open(sys.argv[1], 'w'))
PY
}
run_uncle() { # path-dir stdin -> combined output in $OUT, stdout/err in $T/o $T/e
  local pathdir=$1 input=$2
  (cd "$P" && printf '%b' "$input" | env -i PATH="$pathdir" HOME="$P" UNCLE_CONFIG="$CFG" UNCLE_SKIP_UPGRADE_CHECK=1 \
     TERM=dumb bash "$ROOT/uncle" >"$T/o" 2>"$T/e")
  OUT="$(cat "$T/o" "$T/e")"
}
cfgval() { grep -E "^$1 " "$CFG" | head -1; }
nok_leak() { ! grep -q "$TOKEN" "$T/o" "$T/e" "$CFG"; }

# --- AC-1: runner prompt order, case-insensitive, stored lowercase --------------------------------
new_project p1; printf 'requirements.runner claude\nrequirements.model local/foo\n' >"$CFG"; seed_keys
run_uncle "$T/stubbin" '4\n1\n1\nr\nAWS-Bedrock\nq\nq\nq\nq\n'
prompt=$(grep -o 'Runner ([^)]*)' <<<"$OUT" | head -1)
check "AC-1 prompt lists aws-bedrock then anthropic-api last: $prompt" '[[ "$prompt" == *" aws-bedrock anthropic-api;"* ]] && [[ "${prompt%%aws-bedrock*}" == *claude*codex* ]]'
check "AC-1 AWS-Bedrock stored lowercase" '[ "$(cfgval requirements.runner)" = "requirements.runner aws-bedrock" ]'
check "AC-1 model kept unchanged after switch to aws-bedrock (self/other -> bedrock)" '[ "$(cfgval requirements.model)" = "requirements.model local/foo" ]'

# --- AC-1: empty PATH lists only aws-bedrock and selecting succeeds -------------------------------
new_project p2; printf 'requirements.effort high\n' >"$CFG"; seed_keys
run_uncle "$T/minbin" '4\n1\n1\nr\naws-bedrock\nq\nq\nq\nq\n'
prompt=$(grep -o 'Runner ([^)]*)' <<<"$OUT" | head -1)
check "AC-1 empty PATH prompt lists aws-bedrock: $prompt" '[[ "$prompt" == *aws-bedrock* && "$prompt" != *claude* && "$prompt" != *codex* ]]'
check "AC-1 empty PATH selection succeeds" '[ "$(cfgval requirements.runner)" = "requirements.runner aws-bedrock" ]'

# --- aws-bedrock -> self-hosted keeps model; a following m uses the current runner's store -------
new_project p3; printf 'requirements.runner aws-bedrock\nrequirements.model anthropic.claude-x\naws-bedrock.model keep-global\n' >"$CFG"; seed_keys
run_uncle "$T/stubbin" '4\n1\n1\nm\nanthropic.claude-x\nq\nq\nq\n'
check "m on bedrock stage writes stage model from Bedrock store" '[ "$(cfgval requirements.model)" = "requirements.model anthropic.claude-x" ]'
check "m never modifies global aws-bedrock.model" '[ "$(cfgval aws-bedrock.model)" = "aws-bedrock.model keep-global" ]'
check "m output has no token" 'nok_leak'

# --- AC-3: apply-to-all happy path, mixed runners -------------------------------------------------
new_project p4
{ echo 'requirements.runner claude'; echo 'repair.runner codex'; echo 'final-audit.runner self-hosted'
  echo 'implementation.runner aws-bedrock'; echo 'implementation.model anthropic.claude-x'; echo "implementation.base_url $URL"
  echo 'requirements.model stale'; } >"$CFG"
seed_keys; python3 -c "import json,sys;json.dump({'final-audit':'$SHTOKEN'},open('$SK','w'))"
cp "$SK" "$T/sk.before"
run_uncle "$T/stubbin" '4\n1\n9\na\nq\nq\nq\nq\n'
allbedrock=1; for s in $STAGES; do [ "$(cfgval $s.runner)" = "$s.runner aws-bedrock" ] || allbedrock=0; done
check "AC-3 every stage runner is aws-bedrock" '[ $allbedrock = 1 ]'
check "AC-3 model copied to claude stage (stale overwritten)" '[ "$(cfgval requirements.model)" = "requirements.model anthropic.claude-x" ]'
check "AC-3 base_url copied" '[ "$(cfgval requirements.base_url)" = "requirements.base_url $URL" ]'
check "AC-3 bedrock key set is exactly the stage list, values equal token" 'python3 - "$BK" "$TOKEN" $STAGES <<PY
import json, sys
k = json.load(open(sys.argv[1])); tok = sys.argv[2]
stages = {s for s in k if not s.startswith("__")}
sys.exit(0 if stages == set(sys.argv[3:]) and all(k[s] == tok for s in stages) else 1)
PY'
check "AC-3 self-hosted-keys.json byte-identical" 'cmp -s "$SK" "$T/sk.before"'
check "AC-3 token absent from stdout, stderr and config" 'nok_leak'

# --- AC-3 failure: source stage lacks token / model / base_url; nothing written -------------------
for missing in token model base_url; do
  new_project "f-$missing"
  { echo 'implementation.runner aws-bedrock'; echo 'implementation.model anthropic.claude-x'; echo "implementation.base_url $URL"; } >"$CFG"
  seed_keys; python3 -c "import json;json.dump({'final-audit':'$SHTOKEN'},open('$SK','w'))"
  case $missing in
    token) python3 - "$BK" <<'PY'
import json, sys
k = json.load(open(sys.argv[1])); k.pop('implementation'); json.dump(k, open(sys.argv[1], 'w'))
PY
      ;;
    model) grep -v '^implementation.model ' "$CFG" >"$CFG.n"; mv "$CFG.n" "$CFG" ;;
    base_url) grep -v '^implementation.base_url ' "$CFG" >"$CFG.n"; mv "$CFG.n" "$CFG" ;;
  esac
  cp "$CFG" "$T/cfg.b"; cp "$BK" "$T/bk.b"; cp "$SK" "$T/sk.b"
  run_uncle "$T/stubbin" '4\n1\n9\na\nq\nq\nq\nq\n'
  check "AC-3 missing $missing: Bedrock-worded stderr" 'grep -qi bedrock "$T/e" || grep -qi bedrock "$T/o"'
  check "AC-3 missing $missing: config and both key files byte-identical" 'cmp -s "$CFG" "$T/cfg.b" && cmp -s "$BK" "$T/bk.b" && cmp -s "$SK" "$T/sk.b"'
  check "AC-3 missing $missing: no token output" 'nok_leak'
done

# --- AR-021: d on a Bedrock stage with no stored key leaves key file byte-identical ----------------
new_project p5; printf 'requirements.runner aws-bedrock\n' >"$CFG"; seed_keys; cp "$BK" "$T/bk.b"
run_uncle "$T/stubbin" '4\n1\n1\nd\nq\nq\nq\n'
check "d with no stored key leaves aws-bedrock-keys.json byte-identical" 'cmp -s "$BK" "$T/bk.b"'
check "d clears stage runner" '[ -z "$(cfgval requirements.runner)" ]'

# --- Stages menu display: opencode/aider show as self-hosted; bedrock shows aws-bedrock -----------
new_project p6; printf 'requirements.runner opencode\nchange-spec.runner aws-bedrock\nproject-plan.runner aider\n' >"$CFG"
run_uncle "$T/stubbin" '4\n1\nq\nq\nq\n'
check "display: opencode stage shown as self-hosted" 'grep -E "requirements +self-hosted" <<<"$OUT" >/dev/null'
check "display: aider stage shown as self-hosted" 'grep -E "project-plan +self-hosted" <<<"$OUT" >/dev/null'
check "display: bedrock stage shown as aws-bedrock" 'grep -E "change-spec +aws-bedrock" <<<"$OUT" >/dev/null'
run_uncle "$T/stubbin" '4\n1\nm\nq\nq\nq\n'
cp "$CFG" "$T/cfg.b"
run_uncle "$T/stubbin" '4\n1\nm\nq\nq\nq\n'
check "stages-menu m leaves config byte-identical" 'cmp -s "$CFG" "$T/cfg.b"'

# --- AC-4: menu mapping ---------------------------------------------------------------------------
new_project p7; printf 'requirements.effort high\nmisc.approval_name keepme\n' >"$CFG"; cp "$CFG" "$T/cfg.b"
run_uncle "$T/stubbin" '4\n3\n'
check "menu: 3 opens Configure AWS Bedrock" 'grep -qi "bedrock" "$T/o" && ! grep -q "Auto mode (true/false)" "$T/o"'
check "menu lists Configure AWS Bedrock as item 3" 'grep -E "3\) +Configure AWS Bedrock" "$T/o" >/dev/null'
check "menu lists Configure Anthropic API as item 4" 'grep -E "4\) +Configure Anthropic API" "$T/o" >/dev/null'
check "menu lists Miscellaneous as item 5" 'grep -E "5\) +Miscellaneous" "$T/o" >/dev/null'
run_uncle "$T/stubbin" '4\n5\n\n\nq\n'
check "menu: 5 opens Miscellaneous" 'grep -q "Auto mode (true/false)" "$T/o"'
run_uncle "$T/stubbin" '4\n6\nq\nq\n'
check "menu: 6 prints invalid-choice message" 'grep -q "Unrecognized choice: 6" "$T/o"'
check "menu: 6 writes nothing" 'cmp -s "$CFG" "$T/cfg.b"'
check "menu: no token output" 'nok_leak'

[ "$fails" -eq 0 ]
