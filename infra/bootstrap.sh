#!/bin/bash
# Bootstrap project context for Claude Code sessions on the VPS.
# This script is stored on the locker-vault volume and runs on every boot.
# It's idempotent — safe to run multiple times.

PROJECTS_DIR="/root/projects"
mkdir -p "$PROJECTS_DIR"

# -- 1. Clone repos if missing -------------------------------------------
if [ -n "$GH_TOKEN" ]; then
  git config --global credential.helper store
  echo "https://x-access-token:${GH_TOKEN}@github.com" > /root/.git-credentials
fi

clone_if_missing() {
  local repo="$1" dir="$2"
  if [ ! -d "$PROJECTS_DIR/$dir/.git" ]; then
    echo "Cloning $repo..."
    git clone "https://github.com/$repo.git" "$PROJECTS_DIR/$dir" 2>/dev/null || echo "  Clone failed (auth needed?)"
  else
    echo "Repo $dir already present"
  fi
}

clone_if_missing "launchplugai/claude-hub" "claude-hub"
clone_if_missing "launchplugai/BetApp" "BetApp"
clone_if_missing "launchplugai/marvin" "marvin"

# -- 2. CLAUDE.md (project instructions) ---------------------------------
if [ ! -f "$PROJECTS_DIR/CLAUDE.md" ] || [ -f /vault/CLAUDE.md ]; then
  if [ -f /vault/CLAUDE.md ]; then
    cp /vault/CLAUDE.md "$PROJECTS_DIR/CLAUDE.md"
    echo "CLAUDE.md synced from vault"
  fi
fi

# -- 3. Claude Code settings ----------------------------------------------
mkdir -p /root/.claude
if [ ! -f /root/.claude/settings.json ]; then
  cat > /root/.claude/settings.json <<'SETTINGS'
{
  "remoteControl": true,
  "permissions": {
    "allow": [
      "Bash(npm:*)",
      "Bash(npx:*)",
      "Bash(git:*)",
      "Bash(gh:*)"
    ]
  }
}
SETTINGS
  echo "Claude settings configured (remote control enabled)"
fi

# -- 4. Memory files ------------------------------------------------------
MEMORY_DIR="/root/.claude/projects/-root-projects/memory"
mkdir -p "$MEMORY_DIR"

if [ -f /vault/MEMORY.md ]; then
  cp /vault/MEMORY.md "$MEMORY_DIR/MEMORY.md"
  echo "Memory synced from vault"
fi
if [ -f /vault/betapp-sprint.md ]; then
  cp /vault/betapp-sprint.md "$MEMORY_DIR/betapp-sprint.md"
fi
if [ -f /vault/ruflo-guide.md ]; then
  cp /vault/ruflo-guide.md "$MEMORY_DIR/ruflo-guide.md"
fi

# -- 5. Ruflo init (if not done) ------------------------------------------
cd "$PROJECTS_DIR"
if [ ! -d .claude-flow ]; then
  npx ruflo init --full 2>/dev/null || true
fi

echo '=== Bootstrap complete ==='
