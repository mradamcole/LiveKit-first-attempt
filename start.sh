#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  LiveKit Voice App – Service Manager
#
#  Usage:
#    ./start.sh start     Start LiveKit server, token server & agent
#    ./start.sh stop      Stop all services
#    ./start.sh restart   Restart everything
#    ./start.sh status    Show which services are running
#    ./start.sh logs      Tail all log files
# ─────────────────────────────────────────────────────────────

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"
LOG_DIR="$ROOT_DIR/.logs"
PIDFILE_DIR="$ROOT_DIR/.pids"

# Ports
LIVEKIT_PORT=7880
TOKEN_PORT=3000

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Helpers ──────────────────────────────────────────────────

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

ensure_dirs() {
    mkdir -p "$LOG_DIR" "$PIDFILE_DIR"
}

check_venv() {
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        log_error "Virtual environment not found at $VENV_DIR"
        log_info  "Create it with:  cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

check_livekit_server() {
    if ! command -v livekit-server &>/dev/null; then
        log_error "livekit-server not found. Install it with:  brew install livekit"
        exit 1
    fi
}

port_in_use() {
    lsof -i :"$1" -sTCP:LISTEN &>/dev/null
}

pid_alive() {
    [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

read_pid() {
    local pidfile="$PIDFILE_DIR/$1.pid"
    if [ -f "$pidfile" ]; then
        cat "$pidfile"
    fi
}

write_pid() {
    echo "$2" > "$PIDFILE_DIR/$1.pid"
}

remove_pid() {
    rm -f "$PIDFILE_DIR/$1.pid"
}

# ── Start functions ──────────────────────────────────────────

start_livekit() {
    local pid
    pid=$(read_pid livekit)
    if pid_alive "$pid"; then
        log_warn "LiveKit server already running (PID $pid)"
        return 0
    fi

    if port_in_use "$LIVEKIT_PORT"; then
        log_error "Port $LIVEKIT_PORT already in use. Another LiveKit server running?"
        log_info  "Run:  lsof -i :$LIVEKIT_PORT  to check"
        return 1
    fi

    log_info "Starting LiveKit server on port $LIVEKIT_PORT ..."
    livekit-server --dev > "$LOG_DIR/livekit.log" 2>&1 &
    local new_pid=$!
    write_pid livekit "$new_pid"

    # Wait briefly and verify it started
    sleep 1
    if pid_alive "$new_pid"; then
        log_info "LiveKit server started (PID $new_pid)"
    else
        log_error "LiveKit server failed to start. Check $LOG_DIR/livekit.log"
        return 1
    fi
}

start_token_server() {
    local pid
    pid=$(read_pid token_server)
    if pid_alive "$pid"; then
        log_warn "Token server already running (PID $pid)"
        return 0
    fi

    if port_in_use "$TOKEN_PORT"; then
        log_error "Port $TOKEN_PORT already in use."
        log_info  "Run:  lsof -i :$TOKEN_PORT  to check"
        return 1
    fi

    log_info "Starting token server on port $TOKEN_PORT ..."
    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"
    uvicorn token_server:app --port "$TOKEN_PORT" > "$LOG_DIR/token_server.log" 2>&1 &
    local new_pid=$!
    write_pid token_server "$new_pid"

    sleep 1
    if pid_alive "$new_pid"; then
        log_info "Token server started (PID $new_pid)"
    else
        log_error "Token server failed to start. Check $LOG_DIR/token_server.log"
        return 1
    fi
}

start_agent() {
    local pid
    pid=$(read_pid agent)
    if pid_alive "$pid"; then
        log_warn "Agent already running (PID $pid)"
        return 0
    fi

    log_info "Starting agent ..."
    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"
    python agent.py dev > "$LOG_DIR/agent.log" 2>&1 &
    local new_pid=$!
    write_pid agent "$new_pid"

    sleep 2
    if pid_alive "$new_pid"; then
        log_info "Agent started (PID $new_pid)"
    else
        log_error "Agent failed to start. Check $LOG_DIR/agent.log"
        return 1
    fi
}

# ── Stop functions ───────────────────────────────────────────

kill_tree() {
    # Recursively kill a process and all its descendants
    local target_pid="$1"
    local sig="${2:-TERM}"
    # Find all descendants first, then kill bottom-up
    local children
    children=$(pgrep -P "$target_pid" 2>/dev/null || true)
    for child in $children; do
        kill_tree "$child" "$sig"
    done
    kill -"$sig" "$target_pid" 2>/dev/null || true
}

stop_service() {
    local name="$1"
    local pid
    pid=$(read_pid "$name")

    if [ -z "$pid" ]; then
        log_warn "$name: no PID file found"
        return 0
    fi

    if pid_alive "$pid"; then
        log_info "Stopping $name (PID $pid) and all child processes ..."
        # Kill the entire process tree (parent + all descendants)
        kill_tree "$pid" TERM
        # Wait up to 5 seconds for graceful shutdown
        for i in {1..10}; do
            if ! pid_alive "$pid"; then
                break
            fi
            sleep 0.5
        done
        # Force kill if still alive
        if pid_alive "$pid"; then
            log_warn "$name didn't stop gracefully, force killing ..."
            kill_tree "$pid" 9
        fi
        log_info "$name stopped"
    else
        log_warn "$name was not running (stale PID $pid)"
    fi

    remove_pid "$name"
}

# ── Commands ─────────────────────────────────────────────────

cmd_start() {
    ensure_dirs
    check_livekit_server
    check_venv

    echo ""
    echo -e "${CYAN}━━━ Starting LiveKit Voice App ━━━${NC}"
    echo ""

    start_livekit
    start_token_server
    start_agent

    echo ""
    echo -e "${GREEN}━━━ All services started ━━━${NC}"
    echo ""
    echo -e "  Frontend:       ${CYAN}http://localhost:$TOKEN_PORT${NC}"
    echo -e "  LiveKit server: ${CYAN}ws://localhost:$LIVEKIT_PORT${NC}"
    echo -e "  Logs:           ${CYAN}$LOG_DIR/${NC}"
    echo ""
    echo -e "  Stop with:      ${YELLOW}./start.sh stop${NC}"
    echo ""
}

cmd_stop() {
    ensure_dirs

    echo ""
    echo -e "${CYAN}━━━ Stopping LiveKit Voice App ━━━${NC}"
    echo ""

    stop_service agent
    stop_service token_server
    stop_service livekit

    echo ""
    echo -e "${GREEN}━━━ All services stopped ━━━${NC}"
    echo ""
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    ensure_dirs

    echo ""
    echo -e "${CYAN}━━━ Service Status ━━━${NC}"
    echo ""

    for name in livekit token_server agent; do
        local pid
        pid=$(read_pid "$name")
        if pid_alive "$pid"; then
            echo -e "  ${GREEN}●${NC} $name ${GREEN}running${NC} (PID $pid)"
        else
            echo -e "  ${RED}●${NC} $name ${RED}stopped${NC}"
            [ -n "$pid" ] && remove_pid "$name"
        fi
    done

    echo ""
}

cmd_logs() {
    ensure_dirs
    if [ ! -d "$LOG_DIR" ] || [ -z "$(ls -A "$LOG_DIR" 2>/dev/null)" ]; then
        log_warn "No log files found. Start the services first."
        return
    fi
    tail -f "$LOG_DIR"/*.log
}

# ── Main ─────────────────────────────────────────────────────

case "${1:-}" in
    start)   cmd_start   ;;
    stop)    cmd_stop    ;;
    restart) cmd_restart ;;
    status)  cmd_status  ;;
    logs)    cmd_logs    ;;
    *)
        echo ""
        echo "Usage: ./start.sh {start|stop|restart|status|logs}"
        echo ""
        echo "  start    Start LiveKit server, token server & agent"
        echo "  stop     Stop all services"
        echo "  restart  Restart everything"
        echo "  status   Show which services are running"
        echo "  logs     Tail all log files"
        echo ""
        exit 1
        ;;
esac
