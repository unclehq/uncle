#!/usr/bin/env bash
# green_run re-runs failed verification commands once a missing program has been installed (hosted runs), and not otherwise.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; LIB="$HERE/../lib"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/state"
printf '#!/bin/sh\n[ "$1" = -n ] || exit 9\nshift\nexec "$@"\n' > "$T/bin/sudo"
printf '#!/bin/sh\n[ "$1" = search ] || exit 0\ncase "$3" in */sh$) echo "dash: /usr/bin/sh";; */zzmk$) echo "pkg-mk: /usr/bin/zzmk";; esac\n' > "$T/bin/apt-file"
printf '#!/bin/sh\ncase "$*" in *pkg-mk*) printf "#!/bin/sh\\necho built\\n" > %s/bin/zzmk; chmod +x %s/bin/zzmk;; esac\n' "$T" "$T" > "$T/bin/apt-get"
chmod +x "$T/bin/"*
checks=0; failed=0
ok() { checks=$((checks + 1)); if [[ "$1" == 0 ]]; then echo "ok - $2"; else failed=$((failed + 1)); echo "not ok - $2"; fi; }
printf 'zzmk all\n' > "$T/cmds"
run() {
    ( export PATH="$T/bin:/usr/bin:/bin" UNCLE_HOSTED="$1" STATE_DIR="$T/state"; cd "$T"
      perf_record() { :; }
      . "$LIB/green-check.sh"
      green_run "$T/cmds" "$T/out.tsv" "$T/out.log" 2>"$T/err" ) ; }
rm -f "$T/bin/zzmk"; run 1
[[ "$(cut -f1 "$T/out.tsv")" == 0 ]]; ok $? "hosted: the command passes after the program is installed"
grep -q 'Toolchain repair' "$T/err"; ok $? "hosted: the repair is announced"
rm -f "$T/bin/zzmk" "$T/state/toolchain-heal.json"; run 0
[[ "$(cut -f1 "$T/out.tsv")" != 0 ]]; ok $? "not hosted: nothing is installed and the failure stands"
echo "# $checks checks, $failed failed"; [[ "$failed" == 0 ]]
