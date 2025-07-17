# Session logging
log() {
    if [[ -z $1 ]]; then
        echo "Usage: log {start|status|view|clear|stop}"
    elif [[ $1 == start ]]; then
        export SESSION_LOG_FILE="/tmp/shell-session-logs/$(date +%Y%m%d_%H%M%S)"
        mkdir -p $(dirname "$SESSION_LOG_FILE")
        script -fq "$SESSION_LOG_FILE"
    elif [[ $1 == status ]]; then
        if [[ -f "$SESSION_LOG_FILE" ]]; then
            echo "Session logging initialized, file: $SESSION_LOG_FILE"
        else
            echo "Session logging not initialized."
        fi
    elif [[ $1 == view ]]; then
        cat "$SESSION_LOG_FILE"
    elif [[ $1 == clear ]]; then
        : >"$SESSION_LOG_FILE"
    elif [[ $1 == stop ]]; then
        rm -f "$SESSION_LOG_FILE"
    fi
}
if [[ ! -f "$SESSION_LOG_FILE" && $- == *i* ]]; then
    log start
fi
trap 'log stop' EXIT

# Shell AI integration
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_ROOT="$(dirname $SCRIPT_DIR)"
export PATH="$PATH:$PROJECT_ROOT/bin"

# AI assistant function
ai() {
    eval "$(shell-ai --context-file "$SESSION_LOG_FILE" --message "$*")"
}
