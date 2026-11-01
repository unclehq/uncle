#!/usr/bin/env bash
# The manual checklist is drafted beside implementation and reconciled afterwards: the real functions from stagegate.sh with stub reviewers.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SG="$ROOT/scripts/stagegate.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

fn() { awk -v n="$1" '$0 ~ "^"n"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$SG"; }
FUNCS="$(fn manual_checklist_draft_fingerprint; fn manual_checklist_draft_start; fn manual_checklist_draft_cancel; fn manual_checklist_draft_usable; fn manual_checklist_reconcile; fn run_manual_checklist_panel)"
[[ -n "$FUNCS" ]] || bad "could not extract the functions"

newproject() {   # -> $project with the approved documents and a place for the calls
    project="$work/p$((++n))"; mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/workflow/logs" "$project/.uncle/docs"
    for d in REQUIREMENTS_INTERPRETATION PROJECT_PLAN UPDATED_PROJECT_PLAN ADVERSARIAL_REVIEW; do
        printf '{"doc": "%s", "v": 1}\n' "$d" > "$project/.uncle/workflow/documents/$d.json"
    done
    : > "$project/calls"
}
n=0

# the driver environment: stub reviewers that write packets by call name; real helpers and validators
run_in() {   # <project> <script...>   (extra env through the caller)
    local project="$1"; shift
    ( cd "$project" && env -i PATH="$PATH" HOME="$HOME" ${ENVX:-X=1} bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'
        hash_file() { shasum -a 256 \"\$1\" | cut -d' ' -f1; }
        change_class_panel_subset() { printf '%s' \"\$2\"; }
        run_codex_review() {   # prompt output name
            echo \"\$3\" >> calls; cp \"\$1\" \"prompt-\$3.md\"
            case \"\$3\" in
                manual-checklist-review-worker-draft-*|manual-checklist-review-worker-coverage|manual-checklist-review-worker-invariants|manual-checklist-review-worker-resources)
                    lens=\"\${3##*worker-}\"; lens=\"\${lens#draft-}\"
                    case \"\$lens\" in coverage) base=100;; invariants) base=200;; *) base=300;; esac
                    printf '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"manual-checklist-worker-packet\",\"checks\":[{\"id\":\"MC-%d\",\"exact_action\":\"act %s\",\"expected_result\":\"see %s\",\"evidence_to_capture\":\"shot\",\"required\":true,\"depends_on\":[],\"exclusive_resources\":[],\"section\":\"%s\"},{\"id\":\"MC-%d\",\"exact_action\":\"act2 %s\",\"expected_result\":\"see2 %s\",\"evidence_to_capture\":\"shot\",\"required\":true,\"depends_on\":[],\"exclusive_resources\":[],\"section\":\"%s\"}]}' \$((base+1)) \"\$lens\" \"\$lens\" \"\$lens\" \$((base+2)) \"\$lens\" \"\$lens\" \"\$lens\" > \"\$2\" ;;
                manual-checklist-review-worker-reconcile) cp \"\$RECONCILE_PACKET\" \"\$2\" ;;
            esac
        }
        $FUNCS
        $*" 2>&1 )
}
PACKET_DROP_MODIFY_ADD='{"schema":"uncle.artifact/v1","kind":"manual-checklist-reconcile-packet","drop":[{"id":"MC-302","reason":"the resources behavior was removed by the approved plan"}],"modify":[{"id":"MC-101","reason":"the build labels the key differently from the plan","fields":{"exact_action":"press the key labelled AC"}}],"add":[{"exact_action":"reload the page","expected_result":"the display shows 0","evidence_to_capture":"screenshot","required":true,"reason":"the test review found no reload test"}]}'

# --- a draft is written beside implementation, from what exists before it --------------------------------------------------------
newproject
run_in "$project" 'manual_checklist_draft_start; wait "$MANUAL_DRAFT_PID"; echo done' > "$work/out"
[[ -s "$project/.uncle/workflow/documents/MANUAL_CHECKLIST_DRAFT.json" ]] || bad "no draft was written: $(cat "$work/out")"
[[ -s "$project/.uncle/workflow/manual-checklist-draft.done" ]] || bad "the draft left no completion marker"
[[ ! -e "$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json" ]] || bad "the draft wrote the final checklist"
eq "the draft ran one worker per lens" "$(grep -c 'worker-draft-' "$project/calls")" 3
grep -q 'Draft before implementation' "$project/prompt-manual-checklist-review-worker-draft-coverage.md" || bad "the draft prompt does not say it is a draft"
grep -q 'TEST_REVIEW\|green-check' "$project/prompt-manual-checklist-review-worker-draft-coverage.md" && bad "the draft prompt names something that exists only after implementation"
eq "the draft holds every lens's checks" "$(python3 -c "import json;print(len(json.load(open('$project/.uncle/workflow/documents/MANUAL_CHECKLIST_DRAFT.json'))['checks']))")" 6
eq "no final-panel directory was used" "$(ls "$project/.uncle/workflow" | grep -c '^manual-checklist-panel$')" 0

# --- a resumed run does not draft twice ---------------------------------------------------------------------------------------------
before="$(wc -l < "$project/calls" | tr -d ' ')"
run_in "$project" 'manual_checklist_draft_start; wait 2>/dev/null; echo ok' > /dev/null
eq "an existing draft for the same inputs is kept" "$(wc -l < "$project/calls" | tr -d ' ')" "$before"

# --- reconcile: edits applied, audited, full panel not run -----------------------------------------------------------------------
printf '%s' "$PACKET_DROP_MODIFY_ADD" > "$work/packet.json"
ENVX="RECONCILE_PACKET=$work/packet.json" run_in "$project" 'manual_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=0' "$work/out" || bad "the reconciliation did not succeed: $(cat "$work/out")"
ids="$(python3 -c "import json;print(' '.join(c['id'] for c in json.load(open('$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json'))['checks']))")"
eq "the final checklist is the draft plus the edits" "$ids" "MC-101 MC-102 MC-201 MC-202 MC-301 MC-901"
python3 -c "
import json
c={x['id']:x for x in json.load(open('$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json'))['checks']}
assert c['MC-101']['exact_action']=='press the key labelled AC' and c['MC-101']['expected_result']=='see coverage'
assert 'MC-302' not in c" || bad "the edits were not applied as written"
audit="$project/.uncle/workflow/documents/MANUAL_CHECKLIST_RECONCILIATION.json"
eq "the audit counts the edits" "$(python3 -c "import json;a=json.load(open('$audit'));print(a['draft_checks'],len(a['dropped']),len(a['modified']),len(a['added']))")" "6 1 1 1"
[[ -s "$project/.uncle/docs/MANUAL_CHECKLIST.md" ]] || bad "the checklist was not rendered"
[[ -s "$project/.uncle/workflow/documents/MANUAL_CHECKLIST_WORKERS.json" ]] || bad "MANUAL_CHECKLIST_WORKERS.json was not written"
grep -c 'worker-coverage$\|worker-invariants$\|worker-resources$' "$project/calls" | grep -qx 0 || bad "the full panel ran after a successful reconciliation"
grep -q 'worker-reconcile' "$project/calls" || bad "the reconciler did not run"
grep -q 'Checklist reconciled: 6 draft checks, 1 dropped, 1 modified, 1 added' "$work/out" || bad "the summary line is missing"

# --- a stale draft is not used --------------------------------------------------------------------------------------------------------
newproject
run_in "$project" 'manual_checklist_draft_start; wait "$MANUAL_DRAFT_PID"' > /dev/null
printf '{"doc": "UPDATED_PROJECT_PLAN", "v": 2}\n' > "$project/.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json"
ENVX="RECONCILE_PACKET=$work/packet.json" run_in "$project" 'manual_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=1' "$work/out" || bad "a draft for a changed plan was used"
grep -q 'No usable checklist draft' "$work/out" || bad "the fallback was not announced"
[[ ! -e "$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json" ]] || bad "a stale draft produced a final checklist"
grep -q 'worker-reconcile' "$project/calls" && bad "the reconciler ran against a stale draft"

# --- a packet the rules refuse falls back and writes nothing -----------------------------------------------------------------------------
newproject
run_in "$project" 'manual_checklist_draft_start; wait "$MANUAL_DRAFT_PID"' > /dev/null
printf '%s' '{"schema":"uncle.artifact/v1","kind":"manual-checklist-reconcile-packet","drop":[{"id":"MC-101","reason":"not needed any more"},{"id":"MC-102","reason":"not needed any more"},{"id":"MC-201","reason":"not needed any more"},{"id":"MC-202","reason":"not needed any more"}],"modify":[],"add":[]}' > "$work/gutting.json"
ENVX="RECONCILE_PACKET=$work/gutting.json" run_in "$project" 'manual_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=1' "$work/out" || bad "a gutting reconciliation was applied: $(cat "$work/out")"
[[ ! -e "$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json" ]] || bad "a refused reconciliation wrote a checklist"
printf 'not json' > "$work/garbage.json"
ENVX="RECONCILE_PACKET=$work/garbage.json" run_in "$project" 'manual_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=1' "$work/out" || bad "garbage from the reconciler was applied"

# --- the opt-out ------------------------------------------------------------------------------------------------------------------------------
newproject
ENVX="WORKFLOW_CHECKLIST_DRAFT=0" run_in "$project" 'manual_checklist_draft_start; echo started=${MANUAL_DRAFT_PID:-no}' > "$work/out"
grep -q 'started=no' "$work/out" || bad "WORKFLOW_CHECKLIST_DRAFT=0 still started a draft"
ENVX="WORKFLOW_CHECKLIST_DRAFT=0" run_in "$project" 'manual_checklist_reconcile; echo rc=$?' | grep -q 'rc=1' || bad "WORKFLOW_CHECKLIST_DRAFT=0 still reconciled"
newproject
run_in "$project" 'manual_checklist_draft_start; manual_checklist_draft_cancel; echo cancelled=${MANUAL_DRAFT_PID:-none}' | grep -q 'cancelled=none' || bad "cancelling the draft left its pid set"

# --- the hooks ----------------------------------------------------------------------------------------------------------------------------------
last_block() { awk -v s="        $1)" '$0 == s {buf=""; p=1; next} p && /^        [A-Z_]+\)$/ {p=0} p {buf = buf $0 "\n"} END {printf "%s", buf}' "$SG"; }
last_block IMPLEMENT | grep -q 'manual_checklist_draft_start' || bad "IMPLEMENT does not start the draft"
last_block IMPLEMENT | awk '/manual_checklist_draft_start/{a=NR} /preview_build_wait/{b=NR} END{exit !(a && b && a<b)}' || bad "the draft must start before the tree is touched"
grep -q 'manual_checklist_reconcile || run_manual_checklist_panel' "$SG" || bad "MANUAL_CHECKLIST does not reconcile first and fall back to the panel"
grep -q 'manual_checklist_draft_cancel; fi' "$SG" || bad "an exiting driver does not stop a running draft"
[[ $fail == 0 ]] && echo "checklist-draft-driver-test.sh: ok"
exit $fail
