#!/usr/bin/env bash
# ============================================================
# lock-ollama.sh — Lock Ollama to localhost, verify everything
# Run on VPS as root: bash lock-ollama.sh
# ============================================================
set -euo pipefail

COMPOSE_DIR="/docker/ollama-wmf4"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
BACKUP_FILE="$COMPOSE_FILE.bak.$(date +%s)"

echo "============================================"
echo "  LOCK OLLAMA TO LOCALHOST"
echo "============================================"
echo ""

# ── Step 1: Backup ────────────────────────────────
echo "[1/6] Backing up compose file..."
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: $COMPOSE_FILE not found."
    echo "Update COMPOSE_DIR at top of script if your path differs."
    exit 1
fi
cp "$COMPOSE_FILE" "$BACKUP_FILE"
echo "  Backup saved: $BACKUP_FILE"
echo ""

# ── Step 2: Fix the port binding ──────────────────
echo "[2/6] Fixing port binding..."

# Replace any variation of the ollama port line:
#   - "11434"           (random host port on 0.0.0.0)
#   - "11434:11434"     (fixed but still 0.0.0.0)
#   - 11434:11434       (unquoted)
#   - 0.0.0.0:*:11434   (explicit 0.0.0.0)
# With the safe version:
#   - "127.0.0.1:11434:11434"
sed -i -E 's|^(\s*-\s*)"?[0-9.:]*11434[^"]*"?\s*$|\1"127.0.0.1:11434:11434"|' "$COMPOSE_FILE"

echo "  Updated port binding to 127.0.0.1:11434:11434"
echo ""

# Show the result
echo "  Current compose ports section:"
grep -A2 "ports:" "$COMPOSE_FILE" | head -5
echo ""

# ── Step 3: Restart Ollama ────────────────────────
echo "[3/6] Restarting Ollama..."
cd "$COMPOSE_DIR"
docker compose down 2>/dev/null || docker-compose down 2>/dev/null
docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null
echo "  Ollama restarted."
echo ""

# Give it a moment to bind
sleep 3

# ── Step 4: Verify port binding ──────────────────
echo "[4/6] Verifying port binding..."
echo ""
echo "  Docker ps output:"
docker ps --format "  {{.Names}}  {{.Ports}}" | grep -i ollama || echo "  WARNING: no ollama container found"
echo ""

echo "  Socket binding (ss):"
ss -ltnp | grep 11434 | sed 's/^/  /' || echo "  WARNING: nothing on 11434"
echo ""

# Check for bad bindings
if ss -ltnp | grep 11434 | grep -q "0.0.0.0"; then
    echo "  !! FAIL: Ollama is still bound to 0.0.0.0 !!"
    echo "  Check $COMPOSE_FILE manually."
    echo ""
else
    echo "  PASS: No 0.0.0.0 binding on 11434"
fi

if ss -ltnp | grep 11434 | grep -q "127.0.0.1"; then
    echo "  PASS: Ollama bound to 127.0.0.1:11434"
else
    echo "  !! WARNING: 127.0.0.1:11434 not found in ss output"
fi
echo ""

# ── Step 5: Test Ollama responds locally ─────────
echo "[5/6] Testing Ollama locally..."
OLLAMA_RESPONSE=$(curl -s --connect-timeout 5 http://127.0.0.1:11434/api/version 2>&1) || true
if echo "$OLLAMA_RESPONSE" | grep -q "version"; then
    echo "  PASS: Ollama responds on 127.0.0.1:11434"
    echo "  Response: $OLLAMA_RESPONSE"
else
    echo "  !! FAIL: Ollama not responding on 127.0.0.1:11434"
    echo "  Response: $OLLAMA_RESPONSE"
fi
echo ""

# ── Step 6: Test OpenAI CLI ──────────────────────
echo "[6/6] Testing OpenAI CLI..."
if command -v openai &>/dev/null; then
    echo "  OpenAI CLI found: $(which openai)"
    echo "  (Skipping live API call — run manually if needed)"
    echo "  Test command: openai api chat.completions.create -m gpt-4o-mini -g user 'ping'"
else
    echo "  OpenAI CLI not in PATH (may be inside a container — that's fine)"
fi
echo ""

# ── Summary ──────────────────────────────────────
echo "============================================"
echo "  DONE"
echo "============================================"
echo ""
echo "  Backup:   $BACKUP_FILE"
echo "  Rollback: cp $BACKUP_FILE $COMPOSE_FILE && cd $COMPOSE_DIR && docker compose down && docker compose up -d"
echo ""
echo "  Optional UFW hardening:"
echo "    sudo ufw deny in on eth0 to any port 11434"
echo ""
