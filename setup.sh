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
if python -m patchright install chromium 2>/dev/null; then
    ok "LinkedIn browser ready"
else
    warn "Patchright browser install failed — trying pip install first..."
    pip install --quiet patchright
    python -m patchright install chromium
    ok "LinkedIn browser ready"
fi

# ── Step 3b: LinkedIn Login ──────────────────────────────────────────────────

step "LinkedIn Login (one-time)"

echo ""
echo -e "  ${BOLD}Nester uses your LinkedIn session to research prospects.${NC}"
echo -e "  ${DIM}A browser window will open — log in to LinkedIn as you normally would.${NC}"
echo -e "  ${DIM}This only needs to be done once. Your session is saved locally.${NC}"
echo ""

# Check if already logged in
if linkedin-mcp-server --status 2>/dev/null | grep -qi "logged in"; then
    ok "Already logged into LinkedIn"
else
    echo -ne "  ${BOLD}Press Enter to open LinkedIn login...${NC}"
    read -r
    linkedin-mcp-server --login --no-headless 2>/dev/null || true
    echo ""
    ok "LinkedIn login complete"
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

# --- LLM Provider (DeepSeek for chat, OpenAI for embeddings) ---
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=your_openai_key
OPENAI_RESEARCH_MODEL=deepseek-chat
OPENAI_SYNTHESIS_MODEL=deepseek-chat
OPENAI_EMAIL_MODEL=deepseek-chat

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

# ── Step 6: API Key Wizard ───────────────────────────────────────────────────

step "API Key Setup"

echo ""
echo -e "  ${BOLD}Nester needs a few API keys to power its sales research.${NC}"
echo -e "  ${DIM}We'll walk through each one. Only 2 are required.${NC}"
echo ""

echo -e "  ${BOLD}${CYAN}1/5 — DeepSeek${NC} ${RED}(required)${NC}"
echo -e "  ${DIM}Powers all AI agents — research, persona building, email writing.${NC}"
echo -e "  ${DIM}Get yours at: https://platform.deepseek.com/api_keys${NC}"
ask_key "DEEPSEEK_API_KEY" "Enter your DeepSeek API key:" "required"
echo ""

echo -e "  ${BOLD}${CYAN}2/5 — OpenAI${NC} ${RED}(required for knowledge base)${NC}"
echo -e "  ${DIM}Used only for embeddings (company knowledge search). Not for chat.${NC}"
echo -e "  ${DIM}Get yours at: https://platform.openai.com/api-keys${NC}"
ask_key "OPENAI_API_KEY" "Enter your OpenAI API key:" "required"
echo ""

echo -e "  ${BOLD}${CYAN}3/5 — Firecrawl${NC} ${RED}(required)${NC}"
echo -e "  ${DIM}Scrapes company websites for research data.${NC}"
echo -e "  ${DIM}Get yours at: https://firecrawl.dev${NC}"
ask_key "FIRECRAWL_API_KEY" "Enter your Firecrawl API key:" "required"
echo ""

echo -e "  ${BOLD}${CYAN}4/5 — Tavily${NC} ${YELLOW}(recommended)${NC}"
echo -e "  ${DIM}Web search for company news, funding, and market intel.${NC}"
echo -e "  ${DIM}Get yours at: https://tavily.com${NC}"
ask_key "TAVILY_API_KEY" "Enter your Tavily API key:" "optional"
echo ""

echo -e "  ${BOLD}${CYAN}5/5 — Calendly${NC} ${DIM}(optional)${NC}"
echo -e "  ${DIM}Generates unique booking links in outreach emails.${NC}"
echo -e "  ${DIM}Get yours at: https://calendly.com/integrations/api_webhooks${NC}"
ask_key "CALENDLY_API_KEY" "Enter your Calendly API key:" "optional"

# Auto-fetch Calendly user URI and event type if key was provided
calendly_key=$(grep "^CALENDLY_API_KEY=" .env 2>/dev/null | cut -d'=' -f2-)
if [ -n "$calendly_key" ] && [ "$calendly_key" != "your_calendly_key" ]; then
    info "Fetching your Calendly account details..."

    # Get user URI
    user_uri=$(curl -s -H "Authorization: Bearer $calendly_key" \
        "https://api.calendly.com/users/me" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resource',{}).get('uri',''))" 2>/dev/null || true)

    if [ -n "$user_uri" ]; then
        # Add or update CALENDLY_USER_URI in .env
        if grep -q "^CALENDLY_USER_URI=" .env 2>/dev/null; then
            sed "s|^CALENDLY_USER_URI=.*|CALENDLY_USER_URI=${user_uri}|" .env > .env.tmp && mv .env.tmp .env
        else
            echo "CALENDLY_USER_URI=${user_uri}" >> .env
        fi

        # Get scheduling URL for static fallback
        sched_url=$(curl -s -H "Authorization: Bearer $calendly_key" \
            "https://api.calendly.com/users/me" 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resource',{}).get('scheduling_url',''))" 2>/dev/null || true)

        if [ -n "$sched_url" ]; then
            if grep -q "^CALENDLY_SCHEDULING_URL=" .env 2>/dev/null; then
                sed "s|^CALENDLY_SCHEDULING_URL=.*|CALENDLY_SCHEDULING_URL=${sched_url}|" .env > .env.tmp && mv .env.tmp .env
            else
                echo "CALENDLY_SCHEDULING_URL=${sched_url}" >> .env
            fi
        fi

        # Get first event type URI
        event_uri=$(curl -s -H "Authorization: Bearer $calendly_key" \
            "https://api.calendly.com/event_types?user=${user_uri}&active=true" 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); evts=d.get('collection',[]); print(evts[0]['uri'] if evts else '')" 2>/dev/null || true)

        if [ -n "$event_uri" ]; then
            if grep -q "^CALENDLY_EVENT_TYPE_URI=" .env 2>/dev/null; then
                sed "s|^CALENDLY_EVENT_TYPE_URI=.*|CALENDLY_EVENT_TYPE_URI=${event_uri}|" .env > .env.tmp && mv .env.tmp .env
            else
                echo "CALENDLY_EVENT_TYPE_URI=${event_uri}" >> .env
            fi
            ok "Calendly configured (event type + scheduling link auto-detected)"
        else
            warn "Could not find an active event type — create one at calendly.com first"
        fi
    else
        warn "Could not verify Calendly API key — check it's correct"
    fi
fi
echo ""

# ── Step 7: Sender Profile ───────────────────────────────────────────────────

step "Sender Profile (for outreach emails)"

echo ""
echo -e "  ${DIM}These details appear in your outreach emails.${NC}"
echo -e "  ${DIM}Press Enter to skip any field.${NC}"
echo ""

# SMTP email for sending
current_smtp=$(grep "^SMTP_USER=" .env 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
if [ -z "$current_smtp" ]; then
    echo -ne "  ${BOLD}Your email address (Gmail): ${NC}"
    read -r smtp_email
    if [ -n "$smtp_email" ]; then
        sed "s|^SMTP_USER=.*|SMTP_USER=${smtp_email}|" .env > .env.tmp && mv .env.tmp .env
        ok "Email set: $smtp_email"

        echo ""
        echo -e "  ${DIM}To send emails, you need a Gmail App Password.${NC}"
        echo -e "  ${DIM}1. Go to https://myaccount.google.com/apppasswords${NC}"
        echo -e "  ${DIM}2. Create a new app password for 'Nester'${NC}"
        echo -e "  ${DIM}3. Copy the 16-character password${NC}"
        echo ""
        echo -ne "  ${BOLD}Gmail App Password: ${NC}"
        read -rs smtp_pass
        echo ""
        if [ -n "$smtp_pass" ]; then
            sed "s|^SMTP_PASSWORD=.*|SMTP_PASSWORD=\"${smtp_pass}\"|" .env > .env.tmp && mv .env.tmp .env
            ok "Email password saved"
        fi
    fi
else
    ok "Email already configured: $current_smtp"
fi

# ── Step 8: Google Drive (Company Knowledge) ─────────────────────────────────

step "Google Drive — Company Knowledge"

echo ""
echo -e "  ${DIM}Connect Google Drive so Nester can read your company docs${NC}"
echo -e "  ${DIM}(pitch deck, case studies, service catalog, pricing, etc.)${NC}"
echo -e "  ${DIM}These docs make emails reference REAL services and case studies.${NC}"
echo ""

# Ask for folder ID
current_folder_id=$(grep "^GOOGLE_DRIVE_FOLDER_ID=" .env 2>/dev/null | cut -d'=' -f2- || true)
if [ -z "$current_folder_id" ] || [ "$current_folder_id" = "" ]; then
    echo -e "  ${DIM}Create a folder in Google Drive, upload your company docs,${NC}"
    echo -e "  ${DIM}then copy the folder ID from the URL:${NC}"
    echo -e "  ${DIM}drive.google.com/drive/folders/${BOLD}YOUR_FOLDER_ID${NC}${DIM}  ← this part${NC}"
    echo ""
    echo -ne "  ${BOLD}Google Drive Folder ID (or press Enter to skip): ${NC}"
    read -r gdrive_folder_id
    if [ -n "$gdrive_folder_id" ]; then
        if grep -q "^GOOGLE_DRIVE_FOLDER_ID=" .env 2>/dev/null; then
            sed "s|^GOOGLE_DRIVE_FOLDER_ID=.*|GOOGLE_DRIVE_FOLDER_ID=${gdrive_folder_id}|" .env > .env.tmp && mv .env.tmp .env
        else
            echo "GOOGLE_DRIVE_FOLDER_ID=${gdrive_folder_id}" >> .env
        fi
        ok "Google Drive folder ID saved"
    else
        warn "Skipped — you can add GOOGLE_DRIVE_FOLDER_ID to .env later"
    fi
else
    ok "Google Drive folder already configured: $current_folder_id"
fi

# Check for credentials.json
creds_file="$HOME/.credentials/credentials.json"
if [ ! -f "$creds_file" ]; then
    echo ""
    echo -e "  ${YELLOW}⚠${NC}  Google credentials.json not found at ~/.credentials/credentials.json"
    echo -e "  ${DIM}To set up Google Drive access:${NC}"
    echo -e "  ${DIM}1. Go to console.cloud.google.com → New project${NC}"
    echo -e "  ${DIM}2. Enable the Google Drive API${NC}"
    echo -e "  ${DIM}3. Create OAuth 2.0 credentials (Desktop app)${NC}"
    echo -e "  ${DIM}4. Download credentials.json${NC}"
    echo -e "  ${DIM}5. Place it at: ~/.credentials/credentials.json${NC}"
    echo -e "  ${DIM}Then visit Settings → Company Knowledge in the app to sync.${NC}"
else
    ok "Google credentials.json found"
fi
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
    logs)
        case "\${2:-backend}" in
            backend)  tail -f /tmp/nester-backend.log ;;
            frontend) tail -f /tmp/nester-frontend.log ;;
            linkedin) tail -f /tmp/nester-linkedin-mcp.log ;;
            *)        tail -f /tmp/nester-backend.log ;;
        esac ;;
    *)
        echo "Usage: nester [start|stop|update|logs]"
        echo "  nester start    — Start all servers"
        echo "  nester stop     — Stop all servers"
        echo "  nester update   — Pull latest & restart"
        echo "  nester logs     — Tail backend logs"
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
nohup linkedin-mcp-server --transport streamable-http --host 0.0.0.0 --port 8001 > /tmp/nester-linkedin-mcp.log 2>&1 &
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
