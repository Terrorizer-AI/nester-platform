#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────────
# Nester Agent Platform — Upgrade to latest version
#
# Usage: ./update.sh
#
# What it does:
#   1. Pulls latest code from git
#   2. Installs any new Python packages
#   3. Installs any new frontend packages
#   4. Adds any new .env keys (never overwrites existing values)
#   5. Restarts all servers
# ────────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# macOS Homebrew PATH
if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

clear
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║         🔄  NESTER AGENT PLATFORM                ║"
echo "  ║               Upgrading...                        ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Guard: must have been set up first
if [ ! -f .env ] || [ ! -d .venv ]; then
    fail "Nester is not set up yet. Run ./setup.sh first."
    exit 1
fi

# ── Step 1: Pull latest code ──────────────────────────────────────────────────

step "Pulling latest code"

if [ ! -d .git ]; then
    warn "Not a git repository — skipping git pull"
    warn "If you have the code as a zip, extract it here and re-run ./update.sh"
else
    # Stash any local changes to tracked files so pull doesn't fail
    if ! git diff --quiet HEAD 2>/dev/null; then
        info "Stashing local changes..."
        git stash push -m "nester-update-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    fi

    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    info "Pulling latest on branch: $current_branch"
    git pull origin "$current_branch" 2>&1 | while IFS= read -r line; do info "$line"; done
    ok "Code updated"
fi

# ── Step 2: New Python packages ───────────────────────────────────────────────

step "Updating Python packages"

source .venv/bin/activate
info "Installing / upgrading Python packages..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Python packages up to date"

# ── Step 3: New frontend packages ─────────────────────────────────────────────

step "Updating frontend packages"

cd "$SCRIPT_DIR/frontend"
info "Installing / upgrading frontend packages..."
npm install --silent 2>/dev/null || npm install
ok "Frontend packages up to date"
cd "$SCRIPT_DIR"

# ── Step 4: Sync new .env keys (never overwrite existing values) ──────────────

step "Checking for new configuration keys"

# Define all keys the platform needs with their defaults.
# Only adds a key if it is completely missing from .env.
declare -A KEY_DEFAULTS=(
    ["DEEPSEEK_API_KEY"]="your_deepseek_key"
    ["DEEPSEEK_BASE_URL"]="https://api.deepseek.com"
    ["OPENAI_API_KEY"]="your_openai_key"
    ["OPENAI_RESEARCH_MODEL"]="deepseek-chat"
    ["OPENAI_SYNTHESIS_MODEL"]="deepseek-chat"
    ["OPENAI_EMAIL_MODEL"]="deepseek-chat"
    ["FIRECRAWL_API_KEY"]="your_firecrawl_key"
    ["TAVILY_API_KEY"]="your_tavily_key"
    ["NESTER_DATA_DIR"]="~/.nester"
    ["LOG_LEVEL"]="INFO"
    ["PLAYWRIGHT_HEADLESS"]="true"
    ["BROWSER_POOL_SIZE"]="2"
    ["BROWSER_PAGE_TIMEOUT_MS"]="30000"
    ["DEFAULT_COST_BUDGET_PER_FLOW"]="0.50"
)

new_keys=()
for key in "${!KEY_DEFAULTS[@]}"; do
    if ! grep -q "^${key}=" .env 2>/dev/null; then
        echo "${key}=${KEY_DEFAULTS[$key]}" >> .env
        new_keys+=("$key")
    fi
done

if [ ${#new_keys[@]} -eq 0 ]; then
    ok "No new keys — .env is up to date"
else
    ok "Added ${#new_keys[@]} new key(s) to .env:"
    for k in "${new_keys[@]}"; do
        info "  $k (set a real value in API Keys page or .env)"
    done
    echo ""
    warn "Some new keys need values. Open the app → API Keys page to configure."
fi

# ── Step 5: Refresh global nester command ────────────────────────────────────

step "Refreshing global 'nester' command"

NESTER_CMD_PATH="/usr/local/bin/nester"
cat > /tmp/nester-cmd << CMDEOF
#!/usr/bin/env bash
NESTER_DIR="$SCRIPT_DIR"
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
        ;;
esac
CMDEOF

if sudo cp /tmp/nester-cmd "$NESTER_CMD_PATH" 2>/dev/null && sudo chmod +x "$NESTER_CMD_PATH" 2>/dev/null; then
    ok "nester command refreshed → $NESTER_CMD_PATH"
else
    mkdir -p "$HOME/.local/bin"
    cp /tmp/nester-cmd "$HOME/.local/bin/nester"
    chmod +x "$HOME/.local/bin/nester"
    ok "nester command refreshed → ~/.local/bin/nester"
fi
rm -f /tmp/nester-cmd

# ── Step 6: Restart servers ───────────────────────────────────────────────────

step "Restarting servers"

info "Stopping current servers..."
bash "$SCRIPT_DIR/stop.sh" 2>/dev/null || true
sleep 2

info "Starting updated servers..."
bash "$SCRIPT_DIR/start.sh"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║          ✅  NESTER UPDATED & RUNNING!            ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Open your browser:${NC}  ${CYAN}http://localhost:3000${NC}"
echo ""
echo -e "  ${DIM}Commands (from anywhere):${NC}"
echo -e "    ${BOLD}nester start${NC}   — Start Nester"
echo -e "    ${BOLD}nester stop${NC}    — Stop all servers"
echo -e "    ${BOLD}nester update${NC}  — Pull latest & restart"
echo -e "    ${BOLD}nester logs${NC}    — Tail backend logs"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
