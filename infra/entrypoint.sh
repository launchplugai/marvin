#!/bin/bash
# Claude Hub entrypoint — stored on the locker-vault volume
# This script is base64-encoded and written by the key-locker container.

export PATH="/root/.npm-global/bin:$PATH"

# Load keys from vault
if [ -f /vault/.keys.enc ]; then
  echo '=== Loading keys from vault ==='
  set -a
  . /vault/.keys.enc
  set +a
  echo 'Vault keys loaded'
else
  echo '=== WARNING: No vault keys found ==='
fi

# Always install tmux (container FS doesn't persist, but volume does)
if ! command -v tmux &>/dev/null; then
  echo '=== Installing tmux ==='
  apt-get update -qq && apt-get install -y -qq tmux >/dev/null 2>&1
fi

# First-run install (heavy deps — only once, npm globals persist on volume)
if [ ! -f /root/.claude-hub-ready ]; then
  echo '=== Claude Hub: First run - installing dependencies ==='
  apt-get update
  apt-get install -y --no-install-recommends \
    git python3 python3-pip build-essential curl jq \
    openssh-client ca-certificates gnupg lsb-release wget
  mkdir -p /root/.npm-global /root/.claude /root/projects
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | gpg --batch --yes --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update
  apt-get install -y gh
  npm install -g @anthropic-ai/claude-code ruflo@latest
  apt-get clean
  rm -rf /var/lib/apt/lists/*
  touch /root/.claude-hub-ready
  echo '=== Claude Hub: Installation complete ==='
else
  echo '=== Claude Hub: Already initialized ==='
fi

# Bootstrap project context (CLAUDE.md, memory, repos)
if [ -f /vault/bootstrap.sh ]; then
  echo '=== Bootstrapping project context ==='
  bash /vault/bootstrap.sh
fi

# Write keys + PATH to profile for interactive sessions (docker exec)
cat > /root/.claude-env <<'ENVEOF'
export PATH="/root/.npm-global/bin:$PATH"
ENVEOF
if [ -f /vault/.keys.enc ]; then
  while IFS= read -r line; do
    echo "export $line" >> /root/.claude-env
  done < /vault/.keys.enc
fi
# Ensure .bashrc sources env (only add once)
grep -q '.claude-env' /root/.bashrc 2>/dev/null || echo '. /root/.claude-env' >> /root/.bashrc

# Auto-start Claude Code in tmux so Remote Control is always available
echo '=== Starting Claude Code in tmux ==='
cd /root/projects
tmux new-session -d -s claude -x 200 -y 50 'source /root/.claude-env && claude'
echo '=== Claude Code session started (tmux: claude) ==='
echo '=== Claude Hub running ==='

# Keep container alive and restart Claude if it exits
while true; do
  sleep 30
  if ! tmux has-session -t claude 2>/dev/null; then
    echo '=== Claude Code exited, restarting ==='
    cd /root/projects
    tmux new-session -d -s claude -x 200 -y 50 'source /root/.claude-env && claude'
  fi
done
