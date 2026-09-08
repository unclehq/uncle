#!/usr/bin/env bash
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
    while true; do
        gate_prompt "Repair limit reached: $used of $MAX_REPAIRS attempts used. Enter a new total ($((used + 1))-100), '+N' for N more attempts, or 'stop' to leave this run pending: "
        if ! IFS= read -r answer; then
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
