#!/usr/bin/env bash
# The change flow drafts its manual checklist beside implementation and reconciles it afterwards: the real functions from change-workflow.sh with stub reviewers.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CW="$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

fn() { awk -v n="$1" '$0 ~ "^"n"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$CW"; }
FUNCS="$(fn change_checklist_draft_fingerprint; fn change_checklist_draft_start; fn change_checklist_draft_cancel; fn change_checklist_draft_usable; fn change_checklist_reconcile; fn run_checklist_panel)"
[[ -n "$FUNCS" ]] || bad "could not extract the functions"

n=0
newproject() {
    project="$work/p$((++n))"; mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/workflow/logs" "$project/.uncle/docs"
    for d in BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW; do printf '{"doc": "%s", "v": 1}\n' "$d" > "$project/.uncle/workflow/documents/$d.json"; done
    : > "$project/calls"
}
run_in() {   # <project> <script>; extra environment through ENVX
    local project="$1"; shift
    ( cd "$project" && env -i PATH="$PATH" HOME="$HOME" ${ENVX:-X=1} bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'; PROJECT_ROOT=\"\$PWD\"; PARALLEL_CHECKLIST=\${PARALLEL_CHECKLIST:-1}; CODEX_EFFORT_CHECKLIST=low
        hash_file() { shasum -a 256 \"\$1\" | cut -d' ' -f1; }
        resolve_prompt() { printf '%s\n' \"\$1\"; }
        change_class_panel() { printf '%s' \"\$2\"; }
        uncle_stage_runner() { echo \"\${STUB_RUNNER:-claude}\"; }
        run_codex() {   # prompt output name effort
            echo \"\$3\" >> calls; cp \"\$1\" \"prompt-\$3.md\"
            case \"\$3\" in
                manual-checklist-review-worker-reconcile) cp \"\$RECONCILE_PACKET\" \"\$2\" ;;
                manual-checklist-review-worker-*)
                    lens=\"\${3##*worker-}\"; lens=\"\${lens#draft-}\"; lens=\"\${lens#full-}\"
                    case \"\$lens\" in coverage) base=100;; invariants) base=200;; resources) base=300;; *) base=400;; esac
                    printf '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"manual-checklist-worker-packet\",\"checks\":[{\"id\":\"MC-%d\",\"exact_action\":\"act %s\",\"expected_result\":\"see %s\",\"evidence_to_capture\":\"shot\",\"required\":true,\"depends_on\":[],\"exclusive_resources\":[],\"section\":\"%s\"},{\"id\":\"MC-%d\",\"exact_action\":\"act2 %s\",\"expected_result\":\"see2 %s\",\"evidence_to_capture\":\"shot\",\"required\":true,\"depends_on\":[],\"exclusive_resources\":[],\"section\":\"%s\"}]}' \$((base+1)) \"\$lens\" \"\$lens\" \"\$lens\" \$((base+2)) \"\$lens\" \"\$lens\" \"\$lens\" > \"\$2\" ;;
            esac
        }
        checklist_worker_codex() { run_codex \"\$@\"; }
        $FUNCS
        $*" 2>&1 )
}
PACKET='{"schema":"uncle.artifact/v1","kind":"manual-checklist-reconcile-packet","drop":[{"id":"MC-402","reason":"the regression was removed by the approved change"}],"modify":[{"id":"MC-101","reason":"the finished change renamed the control","fields":{"exact_action":"press the control labelled Save"}}],"add":[{"exact_action":"reload the page","expected_result":"the saved value is still shown","evidence_to_capture":"screenshot","required":true,"reason":"the test review found no persistence test"}]}'
printf '%s' "$PACKET" > "$work/packet.json"
doc() { printf '%s/.uncle/workflow/documents/%s.json' "$project" "$1"; }

# --- the draft reads only what exists before implementation ---------------------------------------------------------------------------
newproject
run_in "$project" 'change_checklist_draft_start; wait "$CHECKLIST_DRAFT_PID"; echo done' > "$work/out"
[[ -s "$(doc MANUAL_CHECKLIST_DRAFT)" ]] || bad "no draft was written: $(cat "$work/out")"
[[ -s "$project/.uncle/workflow/manual-checklist-draft.done" ]] || bad "the draft left no completion marker"
[[ ! -e "$(doc MANUAL_CHECKLIST)" ]] || bad "the draft wrote the final checklist"
[[ ! -e "$project/.uncle/docs/MANUAL_CHECKLIST.md" ]] || bad "the draft rendered the operator's checklist"
eq "one worker per lens" "$(grep -c 'worker-draft-' "$project/calls")" 4
p="$project/prompt-manual-checklist-review-worker-draft-coverage.md"
grep -q 'Draft before implementation' "$p" || bad "the draft prompt does not say it is a draft"
grep -q 'TEST_REVIEW\|green-check\|CHANGE_TEST_REPORT\|IMPLEMENTATION_NOTES' "$p" && bad "the draft prompt names something that exists only after implementation"
for d in BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW; do grep -q "$d.json" "$p" || bad "the draft prompt lacks $d"; done
eq "all lenses' checks are in the draft" "$(python3 -c "import json;print(len(json.load(open('$(doc MANUAL_CHECKLIST_DRAFT)'))['checks']))")" 8

# --- a resumed run keeps the draft ---------------------------------------------------------------------------------------------------------
before="$(wc -l < "$project/calls" | tr -d ' ')"
run_in "$project" 'change_checklist_draft_start; wait 2>/dev/null' > /dev/null
eq "an existing draft for the same inputs is kept" "$(wc -l < "$project/calls" | tr -d ' ')" "$before"

# --- reconcile: edits applied, audited, no full panel -----------------------------------------------------------------------------------
ENVX="RECONCILE_PACKET=$work/packet.json" run_in "$project" 'change_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=0' "$work/out" || bad "the reconciliation did not succeed: $(cat "$work/out")"
eq "the final checklist is the draft plus the edits" \
   "$(python3 -c "import json;print(' '.join(c['id'] for c in json.load(open('$(doc MANUAL_CHECKLIST)'))['checks']))")" \
   "MC-101 MC-102 MC-201 MC-202 MC-301 MC-302 MC-401 MC-901"
python3 -c "
import json
c={x['id']:x for x in json.load(open('$(doc MANUAL_CHECKLIST)'))['checks']}
assert c['MC-101']['exact_action']=='press the control labelled Save' and c['MC-101']['expected_result']=='see coverage'
assert 'MC-402' not in c" || bad "the edits were not applied as written"
eq "the audit counts the edits" "$(python3 -c "import json;a=json.load(open('$(doc MANUAL_CHECKLIST_RECONCILIATION)'));print(a['draft_checks'],len(a['dropped']),len(a['modified']),len(a['added']))")" "8 1 1 1"
[[ -s "$project/.uncle/docs/MANUAL_CHECKLIST.md" ]] || bad "the checklist was not rendered"
[[ -s "$(doc MANUAL_CHECKLIST_WORKERS)" ]] || bad "MANUAL_CHECKLIST_WORKERS.json was not written"
grep -q 'worker-full-' "$project/calls" && bad "the full panel ran after a successful reconciliation"
grep -q 'worker-reconcile' "$project/calls" || bad "the reconciler did not run"
grep -q 'This is a change to an existing application' "$project/.uncle/workflow/manual-checklist-reconcile/prompt.md" || bad "the reconciler was not told this is a change"
grep -q 'Checklist reconciled: 8 draft checks, 1 dropped, 1 modified, 1 added' "$work/out" || bad "the summary line is missing"

# --- a draft for a changed plan is not used ------------------------------------------------------------------------------------------
newproject
run_in "$project" 'change_checklist_draft_start; wait "$CHECKLIST_DRAFT_PID"' > /dev/null
printf '{"doc": "CHANGE_PLAN", "v": 2}\n' > "$(doc CHANGE_PLAN)"
ENVX="RECONCILE_PACKET=$work/packet.json" run_in "$project" 'change_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=1' "$work/out" || bad "a draft for a changed plan was used"
grep -q 'No usable checklist draft' "$work/out" || bad "the fallback was not announced"
[[ ! -e "$(doc MANUAL_CHECKLIST)" ]] || bad "a stale draft produced a final checklist"
grep -q 'worker-reconcile' "$project/calls" && bad "the reconciler ran against a stale draft"

# --- refused or unreadable edits fall back and write nothing -------------------------------------------------------------------------------
newproject
run_in "$project" 'change_checklist_draft_start; wait "$CHECKLIST_DRAFT_PID"' > /dev/null
printf '%s' '{"schema":"uncle.artifact/v1","kind":"manual-checklist-reconcile-packet","drop":[{"id":"MC-101","reason":"not needed any more"},{"id":"MC-102","reason":"not needed any more"},{"id":"MC-201","reason":"not needed any more"},{"id":"MC-202","reason":"not needed any more"},{"id":"MC-301","reason":"not needed any more"}],"modify":[],"add":[]}' > "$work/gutting.json"
ENVX="RECONCILE_PACKET=$work/gutting.json" run_in "$project" 'change_checklist_reconcile; echo rc=$?' > "$work/out"
grep -q 'rc=1' "$work/out" || bad "a gutting reconciliation was applied: $(cat "$work/out")"
[[ ! -e "$(doc MANUAL_CHECKLIST)" ]] || bad "a refused reconciliation wrote a checklist"
printf 'not json' > "$work/garbage.json"
ENVX="RECONCILE_PACKET=$work/garbage.json" run_in "$project" 'change_checklist_reconcile; echo rc=$?' | grep -q 'rc=1' || bad "garbage from the reconciler was applied"

# --- opt-outs: the switch, the one-reviewer path, a self-hosted endpoint -----------------------------------------------------------------
newproject
ENVX="WORKFLOW_CHECKLIST_DRAFT=0" run_in "$project" 'change_checklist_draft_start; echo started=${CHECKLIST_DRAFT_PID:-no}' | grep -q 'started=no' || bad "WORKFLOW_CHECKLIST_DRAFT=0 still started a draft"
ENVX="WORKFLOW_CHECKLIST_DRAFT=0" run_in "$project" 'change_checklist_reconcile; echo rc=$?' | grep -q 'rc=1' || bad "WORKFLOW_CHECKLIST_DRAFT=0 still reconciled"
ENVX="PARALLEL_CHECKLIST=0" run_in "$project" 'change_checklist_draft_start; echo started=${CHECKLIST_DRAFT_PID:-no}' | grep -q 'started=no' || bad "a draft started although the panel path is off"
ENVX="STUB_RUNNER=self-hosted" run_in "$project" 'change_checklist_draft_start; echo started=${CHECKLIST_DRAFT_PID:-no}' | grep -q 'started=no' || bad "a draft competed with implementation on a self-hosted endpoint"
run_in "$project" 'change_checklist_draft_start; change_checklist_draft_cancel; echo cancelled=${CHECKLIST_DRAFT_PID:-none}' | grep -q 'cancelled=none' || bad "cancelling the draft left its pid set"

# --- the hooks ----------------------------------------------------------------------------------------------------------------------------------
state_block() { awk -v s="        $1)" '$0 == s {buf=""; p=1; next} p && /^        [A-Z_]+\)$/ {p=0} p {buf = buf $0 "\n"} END {printf "%s", buf}' "$CW"; }
state_block IMPLEMENT | grep -q 'change_checklist_draft_start' || bad "IMPLEMENT does not start the draft"
state_block MANUAL_CHECKLIST | awk '/change_checklist_reconcile/{a=NR} /run_checklist_panel full/{b=NR} END{exit !(a && b && a<b)}' || bad "CHECKLIST must try the reconciliation before the full panel"
fn on_exit | grep -q 'change_checklist_draft_cancel' || bad "an exiting driver does not stop a running draft"
[[ $fail == 0 ]] && echo "change-checklist-draft-driver-test.sh: ok"
exit $fail
