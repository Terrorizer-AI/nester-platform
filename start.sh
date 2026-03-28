#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────────
# Nester Agent Platform — Start (daily use)
#
# Usage: ./start.sh
# ────────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${DIM}→${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure Homebrew PATH is loaded (macOS)
if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

echo ""
echo -e "${BOLD}${CYAN}  Nester Agent Platform — Starting...${NC}"
echo ""

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [ ! -f .env ]; then
    fail ".env file not found. Run ./setup.sh first."
    exit 1
fi

if [ ! -d .venv ]; then
    fail "Python virtual environment not found. Run ./setup.sh first."
    exit 1
fi

if [ ! -d frontend/node_modules ]; then
    fail "Frontend not installed. Run ./setup.sh first."
    exit 1
fi

# Check required keys
openai_key=$(grep "^OPENAI_API_KEY=" .env 2>/dev/null | cut -d'=' -f2- || true)
if [ -z "$openai_key" ] || [[ "$openai_key" == *"your_"* ]]; then
    fail "OPENAI_API_KEY not set in .env — run ./setup.sh to configure"
    exit 1
fi
ok "Configuration verified"

# ── Kill any existing servers ────────────────────────────────────────────────

if [ -f /tmp/nester-backend.pid ]; then
    old_pid=$(cat /tmp/nester-backend.pid)
    kill "$old_pid" 2>/dev/null && info "Stopped old backend (PID $old_pid)" || true
    rm -f /tmp/nester-backend.pid
fi

if [ -f /tmp/nester-frontend.pid ]; then
    old_pid=$(cat /tmp/nester-frontend.pid)
    kill "$old_pid" 2>/dev/null && info "Stopped old frontend (PID $old_pid)" || true
    rm -f /tmp/nester-frontend.pid
fi

# Kill LinkedIn MCP if running
if [ -f /tmp/nester-linkedin-mcp.pid ]; then
    old_pid=$(cat /tmp/nester-linkedin-mcp.pid)
    kill "$old_pid" 2>/dev/null && info "Stopped old LinkedIn MCP (PID $old_pid)" || true
    rm -f /tmp/nester-linkedin-mcp.pid
fi

# Also kill anything lingering on our ports
lsof -ti:8000 2>/dev/null | xargs kill 2>/dev/null || true
lsof -ti:3000 2>/dev/null | xargs kill 2>/dev/null || true
lsof -ti:8001 2>/dev/null | xargs kill 2>/dev/null || true
sleep 3  # Wait for ports to fully release

# ── Start backend ────────────────────────────────────────────────────────────

source .venv/bin/activate
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/nester-backend.log 2>&1 &
echo $! > /tmp/nester-backend.pid
ok "Backend starting (PID $!)"

# ── Start LinkedIn MCP server ─────────────────────────────────────────────────

nohup linkedin-mcp-server --transport streamable-http --host 0.0.0.0 --port 8001 > /tmp/nester-linkedin-mcp.log 2>&1 &
echo $! > /tmp/nester-linkedin-mcp.pid
ok "LinkedIn MCP starting (PID $!) → port 8001"

# ── Start frontend ───────────────────────────────────────────────────────────

cd "$SCRIPT_DIR/frontend"
nohup npm run dev -- --port 3000 > /tmp/nester-frontend.log 2>&1 &
echo $! > /tmp/nester-frontend.pid
cd "$SCRIPT_DIR"
ok "Frontend starting (PID $!)"

# ── Health check ─────────────────────────────────────────────────────────────

info "Waiting for servers..."
sleep 4

backend_ok=false
for i in 1 2 3 4 5 6; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        backend_ok=true
        break
    fi
    sleep 2
done

if [ "$backend_ok" = true ]; then
    ok "Backend ready  → http://localhost:8000"
else
    warn "Backend still starting — check /tmp/nester-backend.log"
fi

frontend_ok=false
for i in 1 2 3; do
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        frontend_ok=true
        break
    fi
    sleep 2
done

if [ "$frontend_ok" = true ]; then
    ok "Frontend ready → http://localhost:3000"
else
    warn "Frontend still starting — give it a few seconds"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${BOLD}${GREEN}Nester is running!${NC}  Open ${CYAN}http://localhost:3000${NC}"
echo -e "  ${DIM}Stop with: ./stop.sh${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Open browser
if [[ "$(uname)" == "Darwin" ]]; then
    sleep 1
    open "http://localhost:3000" 2>/dev/null || true
fi
