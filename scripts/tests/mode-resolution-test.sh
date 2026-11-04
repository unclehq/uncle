#!/usr/bin/env bash
# Table-driven exact-match tests for scripts/lib/mode.sh.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
MODE_SH="$HERE/../lib/mode.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fails=0; n=0; RES="$T/res"

B_UN='Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.'
N_FLAG='uncle: --unattended is deprecated; unattended is now the default. Use --attended to approve gates yourself.'
N_ENV() { printf 'uncle: %s=1 is deprecated; unattended is now the default. Use UNCLE_ATTENDED=1 to approve gates yourself.' "$1"; }
R_CONTRA='uncle: --attended and --unattended contradict each other; choose one.'
R_TTY='uncle: attended mode needs an interactive terminal on stdin; set UNCLE_ATTENDED_STDIN=1 to answer gates from stdin.'
R_INH='uncle: attended mode was requested but this run was already resolved as unattended; start a new run with --attended.'

# run NAME WORKDIR "ENV ASSIGNMENTS" ARGS... ; sets rc, out, err, res
run() {
  local dir=$1 envs=$2; shift 2
  # shellcheck disable=SC2086
  env -i PATH="$PATH" HOME="$T" RES="$RES" $envs UNCLE_MODE_DIR="${dir}" \
    bash -c 'source "$0"; uncle_resolve_mode "$@"; rc=$?; printf "%s %s %s\n" "${UNATTENDED-}" "${UNCLE_MODE_RESOLVED-}" "${UNCLE_MODE_SOURCE-}" >"$RES"; exit $rc' \
    "$MODE_SH" "$@" >"$T/out" 2>"$T/err" </dev/null
  rc=$?; out=$(cat "$T/out"); err=$(cat "$T/err"); res=$(cat "$RES" 2>/dev/null)
}

# check NAME WANT_RC WANT_ERR WANT_UNATTENDED(or -) ; uses globals from run
check() {
  n=$((n+1))
  local name=$1 wrc=$2 werr=$3 wun=${4:--} ok=1
  [ "$rc" = "$wrc" ] || ok=0
  [ "$err" = "$werr" ] || ok=0
  [ -z "$out" ] || ok=0
  if [ "$wun" != - ] && [ "${res%% *}" != "$wun" ]; then ok=0; fi
  if [ "$wrc" != 0 ] && [ "$wun" != - ]; then ok=0; fi
  if [ "$ok" = 0 ]; then
    fails=$((fails+1))
    printf 'FAIL %s: rc=%s(want %s) unatt=%s(want %s)\n  err=[%s]\n  want=[%s]\n  out=[%s]\n' \
      "$name" "$rc" "$wrc" "${res%% *}" "$wun" "$err" "$werr" "$out" >&2
  fi
}

TTY="UNCLE_STDIN_TTY=1"; NOTTY="UNCLE_STDIN_TTY=0"
D="$T/none"   # nonexistent: no run state

# --- flag / env matrix (fresh dir) ---
run "$D" "$NOTTY";                                  check default 0 "" 1
run "$D" "$TTY" --attended;                         check attended-flag-tty 0 "" 0
run "$D" "$NOTTY" --attended;                       check attended-flag-notty 1 "$R_TTY"
run "$D" "$NOTTY UNCLE_ATTENDED_STDIN=1" --attended; check attended-flag-stdin-waiver 0 "" 0
run "$D" "$NOTTY UNCLE_ATTENDED_STDIN=1";           check stdin-waiver-alone-ignored 0 "" 1
run "$D" "$NOTTY UNCLE_ATTENDED_STDIN=1" --unattended; check stdin-waiver-unattended 0 "$N_FLAG" 1
run "$D" "$NOTTY UNCLE_ATTENDED_STDIN=0" --attended; check stdin-waiver-zero 1 "$R_TTY"
run "$D" "$TTY" --attended --unattended;            check contradict 1 "$R_CONTRA"
run "$D" "$NOTTY" --unattended --attended;          check contradict-notty 1 "$R_CONTRA"
run "$D" "$TTY UNCLE_ATTENDED=1";                   check env-attended 0 "" 0
run "$D" "$NOTTY UNCLE_ATTENDED=1";                 check env-attended-notty 1 "$R_TTY"
for v in 0 "" yes true 2; do
  run "$D" "$TTY UNCLE_ATTENDED=$v";                check "env-attended-ignored[$v]" 0 "" 1
done
run "$D" "$TTY UNCLE_ATTENDED=1" --unattended;     check env-attended-plus-flag-unattended 0 "$N_FLAG" 0
run "$D" "$TTY UNCLE_ATTENDED=1 UNCLE_UNATTENDED=1"; check env-attended-plus-legacy 0 "$(N_ENV UNCLE_UNATTENDED)" 0
run "$D" "$NOTTY" --unattended;                     check unattended-flag 0 "$N_FLAG" 1
for name in UNCLE_UNATTENDED WORKFLOW_UNATTENDED UNCLE_HOUSEKEEPING_UNATTENDED; do
  run "$D" "$NOTTY $name=1";                        check "legacy-$name" 0 "$(N_ENV $name)" 1
  for v in 0 "" junk; do
    run "$D" "$NOTTY $name=$v";                     check "legacy-$name-ignored[$v]" 0 "" 1
  done
done
run "$D" "$NOTTY UNCLE_UNATTENDED=1 WORKFLOW_UNATTENDED=1"
n1=$(N_ENV UNCLE_UNATTENDED); n2=$(N_ENV WORKFLOW_UNATTENDED)
check legacy-two 0 "$n1
$n2" 1

# --- inherited UNCLE_MODE_RESOLVED ---
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1";                check inh-unatt 0 "" 1
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1" --unattended;   check inh-unatt-flag-ignored 0 "" 1
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1 WORKFLOW_UNATTENDED=1"; check inh-unatt-legacy-silent 0 "" 1
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1" --attended;       check inh-unatt-attended-refuse 1 "$R_INH"
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1 UNCLE_ATTENDED=1"; check inh-unatt-env-attended-refuse 1 "$R_INH"
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=0";                  check inh-att 0 "" 0
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=0" --attended;       check inh-att-attended-ok 0 "" 0
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=0" --unattended;     check inh-att-unatt-ignored 0 "" 0
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=0" --attended;     check inh-att-notty 1 "$R_TTY"
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=0 UNCLE_ATTENDED_STDIN=1" --attended; check inh-att-stdin 0 "" 0
run "$D" "$TTY UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1" --attended --unattended; check inh-contradict 1 "$R_CONTRA"
run "$D" "$NOTTY UNCLE_MODE_RESOLVED=0 UNCLE_UNATTENDED=0";                check inh-not-one-ignored 0 "" 1

# --- resume rows ---
mkrun() { # mkrun DIR [MODE-CONTENT]
  rm -rf "$1"; mkdir -p "$1"; : >"$1/state.json"
  [ $# -ge 2 ] && printf '%s' "$2" >"$1/mode"
  return 0
}
R="$T/run/.uncle/workflow"
for rec in attended unattended; do
  for flag in none --attended --unattended env-att env-leg; do
    for tty in "$TTY" "$NOTTY"; do
      mkrun "$R" "$rec
"
      args=(); envs="$tty"
      case $flag in
        --attended) args=(--attended) ;;
        --unattended) args=(--unattended) ;;
        env-att) envs="$tty UNCLE_ATTENDED=1" ;;
        env-leg) envs="$tty UNCLE_UNATTENDED=1" ;;
      esac
      case "$flag:$rec" in
        none:*|env-leg:attended|--unattended:attended) :;; esac
      # expected
      if [ "$flag" = none ]; then want=$rec; elif [ "$flag" = --attended ] || [ "$flag" = env-att ]; then want=attended; else want=unattended; fi
      werr=""
      case $flag in --unattended) werr="$N_FLAG";; env-leg) werr="$(N_ENV UNCLE_UNATTENDED)";; esac
      wrc=0; wun=1; [ "$want" = attended ] && wun=0
      if [ "$want" = attended ] && [ "$tty" = "$NOTTY" ]; then wrc=1; werr="$R_TTY"; fi
      before=$(shasum "$R/mode" | cut -d' ' -f1)
      run "$R" "$envs" "${args[@]+"${args[@]}"}"
      check "resume[$rec/$flag/$tty]" "$wrc" "$werr" "$([ $wrc = 0 ] && echo $wun || echo -)"
      [ "$(shasum "$R/mode" | cut -d' ' -f1)" = "$before" ] || { fails=$((fails+1)); echo "FAIL mode file changed on resolve [$rec/$flag/$tty]" >&2; }
      if [ $wrc = 0 ]; then
        exp=resume; [ "$flag" != none ] && exp=$([ "$flag" = --attended ] && echo flag || { [ "$flag" = env-att ] && echo env || { [ "$flag" = --unattended ] && echo flag || echo env; }; })
        [ "${res##* }" = "$exp" ] || { fails=$((fails+1)); echo "FAIL source [$rec/$flag/$tty] got ${res##* } want $exp" >&2; }
      fi
    done
  done
done
# recorded attended + legacy-attended-no-tty with stdin waiver resumes attended
mkrun "$R" "attended
"; run "$R" "$NOTTY UNCLE_ATTENDED_STDIN=1"; check resume-attended-stdin-waiver 0 "" 0
# recorded unattended, no tty, env waiver ignored
mkrun "$R" "unattended
"; run "$R" "$NOTTY UNCLE_ATTENDED_STDIN=1"; check resume-unattended-waiver-ignored 0 "" 1

# --- mode file validity ---
bad() { # bad NAME setup-cmd
  mkrun "$R"; eval "$2"
  before=$(find "$R" -type f -o -type l | sort | xargs shasum 2>/dev/null | shasum)
  run "$R" "$TTY"
  check "$1" 1 "uncle: $R/mode is not a regular file containing exactly \"attended\" or \"unattended\"; fix or remove it."
  after=$(find "$R" -type f -o -type l | sort | xargs shasum 2>/dev/null | shasum)
  [ "$before" = "$after" ] || { fails=$((fails+1)); echo "FAIL $1: tree changed on refusal" >&2; }
}
bad mode-empty ': >"$R/mode"'
bad mode-garbage 'echo bogus >"$R/mode"'
bad mode-case 'echo Attended >"$R/mode"'
bad mode-multiline 'printf "attended\nunattended\n" >"$R/mode"'
bad mode-trailing-space 'printf "attended \n" >"$R/mode"'
bad mode-symlink 'echo attended >"$T/target"; ln -s "$T/target" "$R/mode"'
bad mode-directory 'mkdir "$R/mode"'
# explicit flag does not rescue an invalid file
mkrun "$R"; echo bogus >"$R/mode"; run "$R" "$TTY" --attended
check mode-garbage-with-flag 1 "uncle: $R/mode is not a regular file containing exactly \"attended\" or \"unattended\"; fix or remove it."

# missing mode file on existing state: predates change, resumes attended
mkrun "$R"; run "$R" "$TTY"
check mode-missing-tty 0 "uncle: $R/mode is missing for this existing run; it predates the mode file and resumes attended." 0
mkrun "$R"; run "$R" "$NOTTY"; check mode-missing-notty 1 "$R_TTY"
[ ! -e "$R/mode" ] || { fails=$((fails+1)); echo "FAIL mode file created on refusal" >&2; }
mkrun "$R"; run "$R" "$NOTTY" --unattended
check mode-missing-explicit-unattended 0 "$N_FLAG" 1

# stale mode file, no run state: ignored
rm -rf "$R"; mkdir -p "$R"; echo attended >"$R/mode"; run "$R" "$NOTTY"; check mode-stale-ignored 0 "" 1
rm -rf "$R"; mkdir -p "$R"; echo bogus >"$R/mode"; run "$R" "$NOTTY"; check mode-stale-garbage-ignored 0 "" 1

# --- write helper: atomic, only on success, rejects symlink ---
w() { env -i PATH="$PATH" HOME="$T" bash -c 'source "$0"; uncle_write_mode_file "$@"' "$MODE_SH" "$@" 2>"$T/werr"; }
rm -rf "$R"; mkdir -p "$R"
w "$R" attended; n=$((n+1))
[ "$(cat "$R/mode")" = attended ] || { fails=$((fails+1)); echo "FAIL write attended" >&2; }
w "$R" unattended; n=$((n+1))
[ "$(cat "$R/mode")" = unattended ] && [ "$(wc -l <"$R/mode" | tr -d ' ')" = 1 ] || { fails=$((fails+1)); echo "FAIL write overwrite" >&2; }
[ -z "$(ls -A "$R" | grep -v '^mode$')" ] || { fails=$((fails+1)); echo "FAIL temp file left behind" >&2; }
rm -f "$R/mode"; echo x >"$T/tgt"; ln -s "$T/tgt" "$R/mode"; n=$((n+1))
if w "$R" attended; then fails=$((fails+1)); echo "FAIL write followed symlink" >&2; fi
[ "$(cat "$T/tgt")" = x ] || { fails=$((fails+1)); echo "FAIL symlink target overwritten" >&2; }

# --- banner strings ---
b() { env -i PATH="$PATH" HOME="$T" "$@" bash -c 'source "$MODE_SH"; uncle_mode_banner' MODE_SH="$MODE_SH" 2>&1 >"$T/bout"; }
bn() { n=$((n+1)); [ "$(b "$@")" = "$WANT" ] && [ ! -s "$T/bout" ] || { fails=$((fails+1)); echo "FAIL banner: $WANT" >&2; }; }
WANT="$B_UN";  bn UNCLE_MODE=unattended MODE_SH="$MODE_SH"
WANT='Mode: attended. Each approval gate waits for your decision.'; bn UNCLE_MODE=attended MODE_SH="$MODE_SH"
WANT='Mode: attended (resumed from .uncle/workflow/mode).'; bn UNCLE_MODE=attended UNCLE_MODE_SOURCE=resume MODE_SH="$MODE_SH"
WANT='Mode: unattended (resumed from .uncle/workflow/mode).'; bn UNCLE_MODE=unattended UNCLE_MODE_SOURCE=resume MODE_SH="$MODE_SH"

# --- EOF / garbage stdin at an attended gate stops the run ---
# Exercised against the real gate prompt helper when the drivers expose one;
# the resolver-level guarantee here is that stdin text never changes the mode.
run "$D" "$NOTTY UNCLE_ATTENDED_STDIN=1" --attended
check attended-stdin-eof-mode-stays-attended 0 "" 0

if [ "$fails" -ne 0 ]; then echo "mode-resolution-test: $fails of $n checks failed" >&2; exit 1; fi
echo "mode-resolution-test: $n checks passed"
