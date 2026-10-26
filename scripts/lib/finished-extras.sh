# Sourced by the drivers. Best effort: never fails the caller. The helper reads
# the state directory from STATE_DIR (default .uncle/workflow).
# Usage: finished_extras start|reset|print [--kind new|change] [--reason ENUM] [--unattended] [--stopped]
finished_extras() {
  python3 "${ROOT:-.}/scripts/lib/finished_extras.py" "$@" || true
}
