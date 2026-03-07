FROM node:20-bookworm

RUN apt-get update -qq && apt-get install -y -qq python3 python3-pip bash ca-certificates && rm -rf /var/lib/apt/lists/*

# Best-effort Codex CLI install. If unavailable, set CODEX_COMMAND to another installed command.
RUN npm install -g @openai/codex || true

WORKDIR /app
