#!/bin/bash
# ============================================================
#  LiveKit Voice Assistant – Service Manager
# ============================================================
#  Usage:
#    ./start.sh start     Start token server + agent
#    ./start.sh stop      Stop all services
#    ./start.sh restart   Restart all services
#    ./start.sh status    Show service status
# ============================================================

# --- Resolve paths relative to this script ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
TOKEN_PORT=3000

PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/.logs"
TOKEN_PID_FILE="$PID_DIR/token_server.pid"
AGENT_PID_FILE="$PID_DIR/agent.pid"
TOKEN_LOG="$LOG_DIR/token_server.log"
AGENT_LOG="$LOG_DIR/agent.log"

# --- Colours ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Platform detection ---
if [[ "$OSTYPE" == msys* || "$OSTYPE" == mingw* || "$OSTYPE" == cygwin* ]]; then
    VENV_ACTIVATE="$BACKEND_DIR/venv/Scripts/activate"
    IS_WINDOWS=true
else
    VENV_ACTIVATE="$BACKEND_DIR/venv/bin/activate"
    IS_WINDOWS=false
fi

mkdir -p "$PID_DIR" "$LOG_DIR"

# ---------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------

# Get the Windows PID listening on $TOKEN_PORT (empty if none)
port_pid() {
    if $IS_WINDOWS; then
        netstat -ano 2>/dev/null \
            | grep ":${TOKEN_PORT} " \
            | grep "LISTENING" \
            | awk '{print $NF}' \
            | head -1
    else
        lsof -ti tcp:"${TOKEN_PORT}" 2>/dev/null | head -1
    fi
}

# Check whether a given PID's command line contains "token_server"
is_our_token_server() {
    local pid="$1"
    if $IS_WINDOWS; then
        wmic process where "processid=$pid" get commandline 2>/dev/null \
            | grep -qi "token_server"
    else
        ps -p "$pid" -o args= 2>/dev/null | grep -qi "token_server"
    fi
}

# Check whether a PID is alive
is_alive() {
    local pid="$1"
    [[ -z "$pid" ]] && return 1
    if $IS_WINDOWS; then
        wmic process where "processid=$pid" get processid 2>/dev/null \
            | grep -q "$pid"
    else
        kill -0 "$pid" 2>/dev/null
    fi
}

# Kill a process (and its tree on Windows)
kill_pid() {
    local pid="$1"
    if $IS_WINDOWS; then
        taskkill //PID "$pid" //F //T >/dev/null 2>&1
    else
        kill "$pid" 2>/dev/null
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
    fi
}

# Read a stored PID from file (empty string if missing)
read_pid_file() {
    [[ -f "$1" ]] && cat "$1" || echo ""
}

# ---------------------------------------------------------------
#  Token Server
# ---------------------------------------------------------------

start_token_server() {
    echo -e "${YELLOW}> Starting token server on port ${TOKEN_PORT}...${NC}"

    # --- Port-conflict detection ---
    local existing
    existing=$(port_pid)
    if [[ -n "$existing" ]]; then
        if is_our_token_server "$existing"; then
            echo -e "${GREEN}  Token server is already running (PID $existing).${NC}"
            echo "$existing" > "$TOKEN_PID_FILE"
            return 0
        else
            echo -e "${RED}  Port $TOKEN_PORT is already in use by another process (PID $existing):${NC}"
            if $IS_WINDOWS; then
                wmic process where "processid=$existing" get name,commandline 2>/dev/null | tail -n +2 | head -3
            else
                ps -p "$existing" -o pid,args 2>/dev/null
            fi
            echo ""
            echo -e "${RED}  Free the port or change TOKEN_PORT in this script, then try again.${NC}"
            return 1
        fi
    fi

    # --- Launch ---
    source "$VENV_ACTIVATE"
    cd "$BACKEND_DIR"
    uvicorn token_server:app --port "$TOKEN_PORT" >> "$TOKEN_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$TOKEN_PID_FILE"

    # Wait briefly for it to bind
    sleep 2

    if is_alive "$pid"; then
        echo -e "${GREEN}  Token server started (PID $pid).${NC}"
    else
        echo -e "${RED}  Token server failed to start. Check the log:${NC}"
        echo -e "${CYAN}  $TOKEN_LOG${NC}"
        tail -5 "$TOKEN_LOG" 2>/dev/null
        return 1
    fi
}

stop_token_server() {
    echo -e "${YELLOW}> Stopping token server...${NC}"

    local pid
    pid=$(read_pid_file "$TOKEN_PID_FILE")

    # If PID file is stale, fall back to port check
    if [[ -z "$pid" ]] || ! is_alive "$pid"; then
        pid=$(port_pid)
        if [[ -n "$pid" ]] && is_our_token_server "$pid"; then
            : # use this pid
        else
            echo -e "  Token server is not running."
            rm -f "$TOKEN_PID_FILE"
            return 0
        fi
    fi

    kill_pid "$pid"
    rm -f "$TOKEN_PID_FILE"
    echo -e "${GREEN}  Token server stopped (was PID $pid).${NC}"
}

# ---------------------------------------------------------------
#  Agent
# ---------------------------------------------------------------

start_agent() {
    echo -e "${YELLOW}> Starting agent...${NC}"

    local old_pid
    old_pid=$(read_pid_file "$AGENT_PID_FILE")
    if [[ -n "$old_pid" ]] && is_alive "$old_pid"; then
        echo -e "${GREEN}  Agent is already running (PID $old_pid).${NC}"
        return 0
    fi

    source "$VENV_ACTIVATE"
    cd "$BACKEND_DIR"
    python agent.py dev >> "$AGENT_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$AGENT_PID_FILE"

    sleep 2

    if is_alive "$pid"; then
        echo -e "${GREEN}  Agent started (PID $pid).${NC}"
    else
        echo -e "${RED}  Agent failed to start. Check the log:${NC}"
        echo -e "${CYAN}  $AGENT_LOG${NC}"
        tail -5 "$AGENT_LOG" 2>/dev/null
        return 1
    fi
}

stop_agent() {
    echo -e "${YELLOW}> Stopping agent...${NC}"

    local pid
    pid=$(read_pid_file "$AGENT_PID_FILE")
    if [[ -z "$pid" ]] || ! is_alive "$pid"; then
        echo -e "  Agent is not running."
        rm -f "$AGENT_PID_FILE"
        return 0
    fi

    kill_pid "$pid"
    rm -f "$AGENT_PID_FILE"
    echo -e "${GREEN}  Agent stopped (was PID $pid).${NC}"
}

# ---------------------------------------------------------------
#  Status
# ---------------------------------------------------------------

show_status() {
    echo ""
    echo -e "${BOLD}Service Status${NC}"
    echo -e "${BOLD}──────────────${NC}"

    # Token server
    local t_pid
    t_pid=$(read_pid_file "$TOKEN_PID_FILE")
    local p_pid
    p_pid=$(port_pid)

    if [[ -n "$t_pid" ]] && is_alive "$t_pid"; then
        echo -e "  Token server : ${GREEN}running${NC}  (PID $t_pid, port $TOKEN_PORT)"
    elif [[ -n "$p_pid" ]] && is_our_token_server "$p_pid"; then
        echo -e "  Token server : ${GREEN}running${NC}  (PID $p_pid, port $TOKEN_PORT — started outside this script)"
    else
        echo -e "  Token server : ${RED}stopped${NC}"
    fi

    # Agent
    local a_pid
    a_pid=$(read_pid_file "$AGENT_PID_FILE")
    if [[ -n "$a_pid" ]] && is_alive "$a_pid"; then
        echo -e "  Agent        : ${GREEN}running${NC}  (PID $a_pid)"
    else
        echo -e "  Agent        : ${RED}stopped${NC}"
    fi

    echo ""
}

# ---------------------------------------------------------------
#  Main
# ---------------------------------------------------------------

case "${1:-}" in
    start)
        echo ""
        start_token_server
        start_agent
        echo ""
        echo -e "${GREEN}${BOLD}App is ready -> http://localhost:${TOKEN_PORT}${NC}"
        echo -e "Logs: .logs/token_server.log, .logs/agent.log"
        echo ""
        ;;
    stop)
        echo ""
        stop_token_server
        stop_agent
        echo ""
        ;;
    restart)
        echo ""
        stop_token_server
        stop_agent
        echo -e "${YELLOW}  Waiting for ports to free...${NC}"
        sleep 2
        start_token_server
        start_agent
        echo ""
        echo -e "${GREEN}${BOLD}App is ready -> http://localhost:${TOKEN_PORT}${NC}"
        echo -e "Logs: .logs/token_server.log, .logs/agent.log"
        echo ""
        ;;
    status)
        show_status
        ;;
    *)
        echo ""
        echo -e "${BOLD}LiveKit Voice Assistant${NC}"
        echo ""
        echo "Usage:  ./start.sh <command>"
        echo ""
        echo "Commands:"
        echo "  start     Start token server + agent"
        echo "  stop      Stop all services"
        echo "  restart   Restart all services"
        echo "  status    Show service status"
        echo ""
        ;;
esac
