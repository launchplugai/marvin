#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Marvin — VPS Deploy Script
# Run this ON your VPS. It will:
#   1. Kill any existing bot process
#   2. Pull the latest code
#   3. Install deps
#   4. Start Marvin in a screen session
# ─────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${MARVIN_DIR:-/root/marvin}"
BRANCH="claude/create-vps-api-Gf2cY"
SCREEN_NAME="marvin"

echo "═══════════════════════════════════════"
echo "  Marvin Deploy"
echo "═══════════════════════════════════════"

# ── 1. Kill old bot ──────────────────────────────────────
echo ""
echo "[1/5] Killing old bot processes..."

# Kill any existing marvin screen session
screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true

# Kill any stray telegram bot processes
pkill -f "telegram_bot" 2>/dev/null || true
pkill -f "python.*bot" 2>/dev/null || true

sleep 1
echo "  ✓ Old processes stopped"

# ── 2. Clone or pull ────────────────────────────────────
echo ""
echo "[2/5] Getting latest code..."

if [ -d "$REPO_DIR/.git" ]; then
    cd "$REPO_DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
    echo "  ✓ Pulled latest from $BRANCH"
else
    echo "  Repo not found at $REPO_DIR"
    echo "  Cloning fresh..."
    git clone -b "$BRANCH" https://github.com/launchplugai/marvin.git "$REPO_DIR"
    cd "$REPO_DIR"
    echo "  ✓ Cloned"
fi

# ── 3. Python env ───────────────────────────────────────
echo ""
echo "[3/5] Setting up Python environment..."

if [ ! -d "$REPO_DIR/venv" ]; then
    python3 -m venv "$REPO_DIR/venv"
    echo "  ✓ Created venv"
fi

source "$REPO_DIR/venv/bin/activate"
pip install -q -r "$REPO_DIR/requirements.txt"
echo "  ✓ Dependencies installed"

# ── 4. Check .env ───────────────────────────────────────
echo ""
echo "[4/5] Checking environment..."

if [ ! -f "$REPO_DIR/.env" ]; then
    echo ""
    echo "  ⚠  No .env file found!"
    echo "  Create one from the template:"
    echo ""
    echo "    cp $REPO_DIR/.env.example $REPO_DIR/.env"
    echo "    nano $REPO_DIR/.env"
    echo ""
    echo "  Fill in at minimum:"
    echo "    TELEGRAM_BOT_TOKEN"
    echo "    OPENAI_API_KEY"
    echo ""
    echo "  Then re-run this script."
    exit 1
fi

# Source .env
set -a
source "$REPO_DIR/.env"
set +a

# Validate required vars
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "  ✗ TELEGRAM_BOT_TOKEN not set in .env"
    exit 1
fi
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "  ⚠  OPENAI_API_KEY not set — bot will fall back to Ollama/Kimi only"
fi
echo "  ✓ Environment loaded"

# ── 5. Launch ───────────────────────────────────────────
echo ""
echo "[5/5] Starting Marvin..."

# Install screen if not present
if ! command -v screen &>/dev/null; then
    apt-get install -y screen -qq 2>/dev/null || yum install -y screen -q 2>/dev/null || true
fi

# Start in a detached screen session
screen -dmS "$SCREEN_NAME" bash -c "
    cd $REPO_DIR
    source venv/bin/activate
    set -a; source .env; set +a
    cd src
    python -m bot.telegram_bot 2>&1 | tee ../marvin.log
"

sleep 2

# Verify it's running
if screen -list | grep -q "$SCREEN_NAME"; then
    echo "  ✓ Marvin is running in screen session '$SCREEN_NAME'"
    echo ""
    echo "═══════════════════════════════════════"
    echo "  Deploy complete!"
    echo "═══════════════════════════════════════"
    echo ""
    echo "  Useful commands:"
    echo "    screen -r marvin        # Attach to see logs"
    echo "    Ctrl+A then D           # Detach from screen"
    echo "    tail -f $REPO_DIR/marvin.log  # Follow logs"
    echo "    screen -S marvin -X quit # Stop the bot"
    echo ""
else
    echo "  ✗ Failed to start. Check logs:"
    echo "    cat $REPO_DIR/marvin.log"
    exit 1
fi
