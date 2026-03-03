#!/bin/bash
# Bootstrap project context for Claude Code on VPS. Idempotent.
P="/root/projects"
mkdir -p "$P"

# 1. Git credentials
[ -n "$GH_TOKEN" ] && {
  git config --global credential.helper store
  echo "https://x-access-token:${GH_TOKEN}@github.com" > /root/.git-credentials
}

# 2. Clone repos
clone_if_missing() {
  [ ! -d "$P/$2/.git" ] && git clone "https://github.com/$1.git" "$P/$2" 2>/dev/null && echo "Cloned $2" || echo "Repo $2 already present"
}
clone_if_missing "launchplugai/claude-hub" "claude-hub"
clone_if_missing "launchplugai/BetApp" "BetApp"
clone_if_missing "launchplugai/marvin" "marvin"

# 3. CLAUDE.md
[ -f /vault/CLAUDE.md ] && cp /vault/CLAUDE.md "$P/CLAUDE.md" && echo "CLAUDE.md synced"

# 4. Claude Code settings
mkdir -p /root/.claude
[ ! -f /root/.claude/settings.json ] && cat > /root/.claude/settings.json <<'S'
{"remoteControl":true,"permissions":{"allow":["Bash(npm:*)","Bash(npx:*)","Bash(git:*)","Bash(gh:*)"]}}
S

# 5. Memory files
M="/root/.claude/projects/-root-projects/memory"
mkdir -p "$M"
[ -f /vault/MEMORY.md ] && cp /vault/MEMORY.md "$M/MEMORY.md" && echo "Memory synced"
[ -f /vault/betapp-sprint.md ] && cp /vault/betapp-sprint.md "$M/betapp-sprint.md"
[ -f /vault/ruflo-guide.md ] && cp /vault/ruflo-guide.md "$M/ruflo-guide.md"

# 6. Superpowers plugin
grep -q superpowers /root/.claude/plugins/installed_plugins.json 2>/dev/null || {
  claude plugin marketplace add obra/superpowers-marketplace 2>/dev/null
  claude plugin install superpowers@superpowers-marketplace 2>/dev/null
  echo "Superpowers installed"
}

# 7. Ruflo
cd "$P"
[ ! -d .claude-flow ] && npx ruflo init --full 2>/dev/null || true

echo '=== Bootstrap complete ==='
