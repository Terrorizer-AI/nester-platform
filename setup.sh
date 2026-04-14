#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────────
# Nester Agent Platform — First-Time Setup
#
# One-liner: curl -sL <your-host>/setup.sh | bash
# Or:        chmod +x setup.sh && ./setup.sh
#
# What it does:
#   1. Checks & installs system deps (Homebrew, Python 3.11+, Node 18+)
#   2. Creates Python virtual environment & installs packages
#   3. Installs frontend dependencies
#   4. Installs Playwright browsers
#   5. Interactive API key wizard (only asks for sales-relevant keys)
#   6. Configures sender profile for outreach emails
#   7. Starts backend + frontend
#   8. Health check + opens browser
# ────────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors & helpers ─────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

step_num=0

step() {
    step_num=$((step_num + 1))
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}  Step ${step_num}: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${DIM}→${NC} $1"; }

ask_key() {
    local var_name="$1"
    local prompt="$2"
    local required="$3"
    local current_val=""

    # Read current value from .env if exists
    if [ -f .env ]; then
        current_val=$(grep "^${var_name}=" .env 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
    fi

    # Skip if already set to a real value
    if [ -n "$current_val" ] && [[ "$current_val" != *"your_"* ]] && [[ "$current_val" != "sk-proj-xxx"* ]]; then
        ok "${var_name} already configured"
        return
    fi

    if [ "$required" = "required" ]; then
        echo -e "  ${RED}(required)${NC} ${prompt}"
    else
        echo -e "  ${DIM}(optional — press Enter to skip)${NC} ${prompt}"
    fi

    while true; do
        echo -ne "  ${BOLD}${var_name}=${NC}"
        read -r value
        if [ -n "$value" ]; then
            # Update .env
            if grep -q "^${var_name}=" .env 2>/dev/null; then
                # Use a temp file for portable sed
                sed "s|^${var_name}=.*|${var_name}=${value}|" .env > .env.tmp && mv .env.tmp .env
            else
                echo "${var_name}=${value}" >> .env
            fi
            ok "Saved ${var_name}"
            return
        elif [ "$required" = "optional" ]; then
            info "Skipped"
            return
        else
            fail "This key is required. Please enter a value."
        fi
    done
}

# ── Banner ───────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║           🚀  NESTER AGENT PLATFORM              ║"
echo "  ║               First-Time Setup                    ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${DIM}Build Once. Configure Many. Deploy Any Flow.${NC}"
echo ""
echo -e "  This wizard will set up everything you need."
echo -e "  ${DIM}Takes about 3-5 minutes. You'll need your API keys ready.${NC}"
echo ""
echo -ne "  ${BOLD}Press Enter to begin...${NC}"
read -r

# ── Resolve project directory ────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PROJECT_DIR="$SCRIPT_DIR"

# ── Step 1: System Dependencies ──────────────────────────────────────────────

step "Checking system dependencies"

# macOS only — check for Homebrew
if [[ "$(uname)" == "Darwin" ]]; then
    # Ensure Homebrew PATH is loaded (needed for python3.13, node, etc.)
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi

    if command -v brew &>/dev/null; then
        ok "Homebrew installed"
    else
        info "Installing Homebrew (macOS package manager)..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        ok "Homebrew installed"
    fi
fi

# Python 3.11+
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        py_version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        major=$(echo "$py_version" | cut -d. -f1)
        minor=$(echo "$py_version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -n "$PYTHON_CMD" ]; then
    ok "Python $("$PYTHON_CMD" --version 2>&1) found"
else
    info "Python 3.11+ not found. Installing..."
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install python@3.13
        PYTHON_CMD="python3.13"
    else
        fail "Please install Python 3.11+ manually: https://python.org/downloads"
        exit 1
    fi
    ok "Python installed: $("$PYTHON_CMD" --version 2>&1)"
fi

# Node.js 18+
if command -v node &>/dev/null; then
    node_version=$(node --version | grep -oE '[0-9]+' | head -1)
    if [ "$node_version" -ge 18 ]; then
        ok "Node.js $(node --version) found"
    else
        info "Node.js is too old (need 18+). Installing..."
        if [[ "$(uname)" == "Darwin" ]]; then
            brew install node
        else
            fail "Please install Node.js 18+: https://nodejs.org"
            exit 1
        fi
        ok "Node.js $(node --version) installed"
    fi
else
    info "Node.js not found. Installing..."
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install node
    else
        fail "Please install Node.js 18+: https://nodejs.org"
        exit 1
    fi
    ok "Node.js $(node --version) installed"
fi

# ── Step 2: Python Virtual Environment ───────────────────────────────────────

step "Setting up Python environment"

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
    ok "Virtual environment created"
else
    ok "Virtual environment exists"
fi

# Activate venv
source .venv/bin/activate
ok "Activated .venv ($(python --version))"

info "Installing Python packages (this may take a minute)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Python packages installed"

# ── Step 3: Playwright Browsers ──────────────────────────────────────────────

step "Installing browser automation"

info "Installing Playwright Chromium (for LinkedIn research)..."
python -m playwright install chromium --quiet 2>/dev/null || python -m playwright install chromium
ok "Playwright browser ready"

info "Installing Patchright browser (for LinkedIn MCP)..."
# IMPORTANT: Preserve LinkedIn profile before reinstalling browsers
PROFILE_BACKUP="$HOME/.linkedin-mcp/profile.backup"
PROFILE_DIR="$HOME/.linkedin-mcp/profile"
if [ -d "$PROFILE_DIR" ]; then
    info "Backing up LinkedIn session..."
    cp -r "$PROFILE_DIR" "$PROFILE_BACKUP" 2>/dev/null || true
fi

if python -m patchright install chromium 2>/dev/null; then
    ok "LinkedIn browser ready"
else
    warn "Patchright browser install failed — trying pip install first..."
    pip install --quiet patchright
    python -m patchright install chromium
    ok "LinkedIn browser ready"
fi

# Restore LinkedIn profile if it was backed up
if [ -d "$PROFILE_BACKUP" ] && [ ! -d "$PROFILE_DIR" ]; then
    info "Restoring LinkedIn session..."
    cp -r "$PROFILE_BACKUP" "$PROFILE_DIR" 2>/dev/null || true
    ok "LinkedIn session restored"
fi
rm -rf "$PROFILE_BACKUP" 2>/dev/null || true

# ── Step 3b: LinkedIn Login ──────────────────────────────────────────────────

step "LinkedIn Login (one-time)"

echo ""
echo -e "  ${BOLD}Nester uses your LinkedIn session to research prospects.${NC}"
echo -e "  ${DIM}A browser window will open — log in to LinkedIn as you normally would.${NC}"
echo -e "  ${DIM}Your session is saved to ~/.linkedin-mcp/profile${NC}"
echo -e "  ${DIM}Sessions expire after 24-48 hours — you may need to re-login periodically.${NC}"
echo ""

# Check if session is valid using the official --status check
PROFILE_DIR="$HOME/.linkedin-mcp/profile"
COOKIES_FILE="$HOME/.linkedin-mcp/cookies.json"
SOURCE_STATE="$HOME/.linkedin-mcp/source-state.json"
NEEDS_LOGIN=false
LOGIN_REASON=""

if [ ! -d "$PROFILE_DIR" ] || [ ! -f "$COOKIES_FILE" ] || [ ! -f "$SOURCE_STATE" ]; then
    NEEDS_LOGIN=true
    LOGIN_REASON="No LinkedIn session found"
elif ! uvx linkedin-scraper-mcp@latest --status >/dev/null 2>&1; then
    NEEDS_LOGIN=true
    LOGIN_REASON="LinkedIn session expired or invalid"
    warn "$LOGIN_REASON"
else
    ok "LinkedIn session is valid"
fi

# If login is needed, run the correct uvx login command
if [ "$NEEDS_LOGIN" = true ]; then
    echo ""
    echo -e "  ${BOLD}${CYAN}LinkedIn Login Required${NC} ${DIM}($LOGIN_REASON)${NC}"
    echo ""
    echo -e "  ${DIM}A browser will open. It visits a few sites first (anti-detection),${NC}"
    echo -e "  ${DIM}then opens LinkedIn. Log in manually — you have 5 minutes.${NC}"
    echo ""
    echo -ne "  ${BOLD}Press Enter to open browser for LinkedIn login...${NC}"
    read -r

    # Use the CORRECT command: uvx linkedin-scraper-mcp@latest --login
    if uvx linkedin-scraper-mcp@latest --login; then
        if [ -f "$COOKIES_FILE" ] && [ -f "$SOURCE_STATE" ]; then
            ok "LinkedIn login complete — session saved"
        else
            warn "Login may have partially failed — missing cookies or state file"
        fi
    else
        warn "LinkedIn login failed — you can retry later with: uvx linkedin-scraper-mcp@latest --login"
    fi
fi

# ── Step 4: Frontend Dependencies ────────────────────────────────────────────

step "Setting up frontend"

cd "$PROJECT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    info "Installing frontend packages..."
    npm install --silent 2>/dev/null || npm install
    ok "Frontend packages installed"
else
    ok "Frontend packages already installed"
fi
cd "$PROJECT_DIR"

# ── Step 5: Environment File ─────────────────────────────────────────────────

step "Creating configuration"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        ok "Created .env from template"
    else
        touch .env
        cat > .env << 'ENVEOF'
# ── Nester Agent Platform Configuration ──

# --- LLM Provider (OpenAI for all agents + embeddings) ---
OPENAI_API_KEY=your_openai_key
OPENAI_RESEARCH_MODEL=gpt-4o
OPENAI_SYNTHESIS_MODEL=gpt-4o
OPENAI_EMAIL_MODEL=gpt-4o

# --- Web Scraping ---
FIRECRAWL_API_KEY=your_firecrawl_key

# --- Search ---
TAVILY_API_KEY=your_tavily_key

# --- Calendly (optional — auto-configured by setup wizard) ---
CALENDLY_API_KEY=
CALENDLY_USER_URI=
CALENDLY_EVENT_TYPE_URI=
CALENDLY_SCHEDULING_URL=

# --- Email Sender ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# --- Platform ---
LOG_LEVEL=INFO
PLAYWRIGHT_HEADLESS=true
BROWSER_POOL_SIZE=2
BROWSER_PAGE_TIMEOUT_MS=30000
DEFAULT_COST_BUDGET_PER_FLOW=0.50
ENVEOF
        ok "Created .env"
    fi
else
    ok ".env file exists"
fi

# ── Step 6: API Key Setup (minimum required only) ────────────────────────────

step "API Key Setup"

echo ""
echo -e "  ${BOLD}Only 2 keys are needed to start.${NC}"
echo -e "  ${DIM}All other keys (Firecrawl, Tavily, Calendly, Google, SMTP) can be${NC}"
echo -e "  ${DIM}added later in the app → API Keys page.${NC}"
echo ""

echo -e "  ${BOLD}${CYAN}1/1 — OpenAI${NC} ${RED}(required)${NC}"
echo -e "  ${DIM}Powers all AI agents (GPT-4o) + knowledge base embeddings.${NC}"
echo -e "  ${DIM}Get yours at: https://platform.openai.com/api-keys${NC}"
ask_key "OPENAI_API_KEY" "Enter your OpenAI API key:" "required"
echo ""

# ── Step 9: Install global `nester` command ──────────────────────────────────

step "Installing global 'nester' command"

NESTER_CMD_PATH="/usr/local/bin/nester"
cat > /tmp/nester-cmd << CMDEOF
#!/usr/bin/env bash
# Nester global command — works from any directory
NESTER_DIR="$PROJECT_DIR"
cd "\$NESTER_DIR"

case "\${1:-start}" in
    start)   bash start.sh ;;
    stop)    bash stop.sh ;;
    update)  bash update.sh ;;
    setup)   bash setup.sh ;;
    linkedin-login)
        echo "🔐 Refreshing LinkedIn Session..."
        uvx linkedin-scraper-mcp@latest --login
        echo "✅ LinkedIn session refreshed"
        ;;
    logs)
        case "\${2:-backend}" in
            backend)  tail -f /tmp/nester-backend.log ;;
            frontend) tail -f /tmp/nester-frontend.log ;;
            linkedin) tail -f /tmp/nester-linkedin-mcp.log ;;
            *)        tail -f /tmp/nester-backend.log ;;
        esac ;;
    *)
        echo "Usage: nester [start|stop|update|setup|linkedin-login|logs]"
        echo "  nester start           — Start all servers"
        echo "  nester stop            — Stop all servers"
        echo "  nester update          — Pull latest & restart"
        echo "  nester setup           — Run setup wizard (auto-detects session expiry)"
        echo "  nester linkedin-login  — Refresh LinkedIn session manually"
        echo "  nester logs            — Tail backend logs"
        ;;
esac
CMDEOF

if sudo cp /tmp/nester-cmd "$NESTER_CMD_PATH" 2>/dev/null && sudo chmod +x "$NESTER_CMD_PATH" 2>/dev/null; then
    ok "Installed: nester command → $NESTER_CMD_PATH"
    ok "You can now run: nester start / nester stop / nester update"
else
    # Fallback: install to ~/.local/bin (no sudo needed)
    mkdir -p "$HOME/.local/bin"
    cp /tmp/nester-cmd "$HOME/.local/bin/nester"
    chmod +x "$HOME/.local/bin/nester"

    # Add to PATH in shell rc if not already there
    for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
        if [ -f "$rc" ] && ! grep -q 'HOME/.local/bin' "$rc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
        fi
    done
    ok "Installed: nester command → ~/.local/bin/nester"
    warn "Run: source ~/.zshrc   (to activate in this terminal)"
fi

rm -f /tmp/nester-cmd

# ── Step 10: Start Servers ────────────────────────────────────────────────────

step "Starting Nester"

info "Starting backend server..."
source .venv/bin/activate
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/nester-backend.log 2>&1 &
echo $! > /tmp/nester-backend.pid
ok "Backend starting on port 8000"

info "Starting LinkedIn MCP server..."
nohup uvx linkedin-scraper-mcp@latest --transport streamable-http --host 0.0.0.0 --port 8001 > /tmp/nester-linkedin-mcp.log 2>&1 &
echo $! > /tmp/nester-linkedin-mcp.pid
ok "LinkedIn MCP starting on port 8001"

info "Starting frontend..."
cd "$PROJECT_DIR/frontend"
nohup npm run dev -- --port 3000 > /tmp/nester-frontend.log 2>&1 &
echo $! > /tmp/nester-frontend.pid
cd "$PROJECT_DIR"
ok "Frontend starting on port 3000"

# ── Step 11: Health Check ────────────────────────────────────────────────────

step "Checking everything works"

info "Waiting for servers to start..."
sleep 5

# Backend health check
backend_ok=false
for i in 1 2 3 4 5; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        backend_ok=true
        break
    fi
    sleep 2
done

if [ "$backend_ok" = true ]; then
    ok "Backend is running (http://localhost:8000)"
else
    warn "Backend is still starting — check /tmp/nester-backend.log if it doesn't come up"
fi

# Frontend health check
frontend_ok=false
for i in 1 2 3; do
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        frontend_ok=true
        break
    fi
    sleep 2
done

if [ "$frontend_ok" = true ]; then
    ok "Frontend is running (http://localhost:3000)"
else
    warn "Frontend is still starting — give it a few more seconds"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║          ✅  NESTER IS READY!                     ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Open your browser:${NC}  ${CYAN}http://localhost:3000${NC}"
echo ""
echo -e "  ${DIM}Commands (from anywhere):${NC}"
echo -e "    ${BOLD}nester start${NC}   — Start Nester"
echo -e "    ${BOLD}nester stop${NC}    — Stop all servers"
echo -e "    ${BOLD}nester update${NC}  — Pull latest changes & restart"
echo -e "    ${BOLD}nester logs${NC}    — Tail backend logs"
echo ""
echo -e "  ${DIM}Logs:${NC}"
echo -e "    Backend:  /tmp/nester-backend.log"
echo -e "    Frontend: /tmp/nester-frontend.log"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Open browser
if [[ "$(uname)" == "Darwin" ]]; then
    sleep 2
    open "http://localhost:3000" 2>/dev/null || true
fi
