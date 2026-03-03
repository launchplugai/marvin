#!/bin/bash
set -euo pipefail

# Only run in remote (web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# -- 1. Install Python dependencies --
pip install --quiet pytest 2>/dev/null || pip3 install --quiet pytest 2>/dev/null || true

# -- 2. Export tokens from .env into the session --
ENV_FILE="${CLAUDE_PROJECT_DIR:-.}/.env"
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    echo "export $line" >> "$CLAUDE_ENV_FILE"
  done < "$ENV_FILE"
fi

# -- 3. Set PYTHONPATH so tests can import from src/ --
echo "export PYTHONPATH=\"${CLAUDE_PROJECT_DIR:-.}/src:\${PYTHONPATH:-}\"" >> "$CLAUDE_ENV_FILE"
