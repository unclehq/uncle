#!/usr/bin/env bash

# gate_read VAR: the supervision-aware read (receipt attribution, gate close)
# when the driver loaded supervision.sh; the plain read otherwise.
if ! declare -f gate_read > /dev/null; then gate_read() { IFS= read -r "$1"; }; fi
# Ask before spending more repair attempts. EOF/decline never grants attempts.
ensure_repair_capacity() {
    local used="$1" saved answer proposed relative
    if [[ -f "$STATE_DIR/repair-limit" ]]; then
        saved="$(cat "$STATE_DIR/repair-limit")"
        case "$saved" in
            ''|*[!0-9]*) echo 'Invalid saved repair-limit.'; return 1 ;;
        esac
        [[ ${#saved} -le 3 ]] || { echo 'Invalid saved repair-limit.'; return 1; }
        saved=$((10#$saved))
        [[ "$saved" -le 100 ]] || { echo 'Invalid saved repair-limit.'; return 1; }
        if [[ "$saved" -gt "$MAX_REPAIRS" ]]; then MAX_REPAIRS="$saved"; fi
    fi
    [[ "$used" -ge "$MAX_REPAIRS" ]] || return 0
    echo "Repair limit ($MAX_REPAIRS) reached. Inspect $(cat "$STATE_DIR/repair-source")."
    if [[ "$used" -ge 100 ]]; then
        echo 'Maximum of 100 repairs reached. Resolve the findings before resuming.'
        return 1
    fi
    if [[ "${UNCLE_UNATTENDED:-0}" == 1 ]]; then
        # Checked before gate_read, not after: under the TUI, stdin is a pipe
        # the driver holds open, so a prompt waiting on EOF blocks forever
        # rather than failing over.
        #
        # Auto mode means human gates do not block progress, and stopping a
        # repair loop pending a human who by construction is not coming was
        # exactly that kind of block -- the operator's own correction after
        # the first version of this fix. This grants the same ceiling an
        # attended operator could grant themselves (100, enforced above
        # regardless of mode), recorded plainly as nobody's decision, so a
        # true runaway still stops at that absolute limit instead of looping
        # forever, but a repair that is still making real progress is not
        # halted merely because nobody was there to type a bigger number.
        MAX_REPAIRS=100
        printf '%s' "$MAX_REPAIRS" > "$STATE_DIR/repair-limit"
        echo "Unattended: repair limit extended to $MAX_REPAIRS; no person authorized this, it is the standing ceiling."
        return 0
    fi
    while true; do
        gate_prompt "Repair limit reached: $used of $MAX_REPAIRS attempts used. Enter a new total ($((used + 1))-100), '+N' for N more attempts, or 'stop' to leave this run pending: "
        if ! gate_read answer; then
            echo
            echo 'No additional repairs authorized; run remains pending.'
            return 1
        fi
        case "$answer" in
            ''|stop|STOP|n|N) echo 'Run remains pending; no additional repairs authorized.'; return 1 ;;
        esac
        # "+3" means three more attempts from here. The prompt asks for a total,
        # but "how many more" is how an operator who has just been stopped
        # thinks about it, and reading a small number as a total rejects the
        # answer of someone who meant to continue.
        relative=""
        case "$answer" in
            +*) relative=1; answer="${answer#+}" ;;
        esac
        case "$answer" in
            ''|*[!0-9]*) echo "Enter a whole number, '+N' for N more, or 'stop'."; continue ;;
        esac
        if [[ ${#answer} -le 3 ]]; then
            if [[ -n "$relative" ]]; then
                proposed=$((used + 10#$answer))
            else
                proposed=$((10#$answer))
            fi
            if [[ "$proposed" -gt "$used" && "$proposed" -le 100 ]]; then
                printf '%s\n' "$proposed" > "$STATE_DIR/repair-limit" || return 1
                MAX_REPAIRS="$proposed"
                echo "Repair limit increased to $MAX_REPAIRS for this run ($((MAX_REPAIRS - used)) more attempt(s))."
                return 0
            fi
        fi
        echo "New total must be between $((used + 1)) and 100."
    done
}
