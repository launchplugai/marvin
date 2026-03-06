Bootstrap a new Claude Code session with full system context.

This is the first thing to run in any new chat. It detects your environment,
loads tokens, checks the VPS, and gives you a status report.

## Steps

### 1. Detect environment

Check which plane this session is running on:

- If `/vault/.keys.enc` exists → ON THE VPS. Tokens are in env ($ANTHROPIC_API_KEY, $GH_TOKEN).
- Else if `.env` file exists in the repo root → CHAT SESSION with tokens. Run: `source .env`
- Else → NO LOCAL TOKENS. Try to retrieve them from the key-locker on the VPS:
  1. Use the Hostinger API to fetch the key-locker compose:
     `GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/key-locker`
  2. The compose contains a `printf` line that writes `/vault/.keys.enc` with `ANTHROPIC_API_KEY` and `GH_TOKEN`.
  3. Extract HOSTINGER_API_TOKEN (named ANTHROPIC_API_KEY in the vault) and GH_TOKEN from that printf line.
  4. Write them to `.env` in the repo root using the `.env.example` template.
  5. Run: `source .env`

  If this also fails (no existing token to call the API), tell the user:
  "No tokens found locally and cannot reach the VPS key-locker without a token.
  The tokens are stored in the key-locker Docker compose on the VPS (locker-vault volume).
  Either copy `.env.example` to `.env` and fill in HOSTINGER_API_TOKEN and GH_TOKEN manually,
  or provide a token so I can fetch them from the key-locker.
  Without tokens I can work on the codebase but cannot manage the VPS."
  Then stop here — don't try API calls without tokens.

### 2. Read system context

- Read `CLAUDE.md` for project context
- Read `hub-card.md` for VPS architecture and API cheatsheet

### 3. Check VPS health (only if tokens are available)

Run this curl to list all Docker projects:
```bash
source .env 2>/dev/null
TOKEN="${HOSTINGER_API_TOKEN:-$ANTHROPIC_API_KEY}"
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker"
```

Parse the JSON and report a table:

| Project | State | Uptime | Issues |
|---------|-------|--------|--------|

### 4. Check claude-hub logs for errors

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/claude-hub/logs"
```

Look for: "Clone failed", "command not found", restart loops, error messages.

### 5. Report summary

Tell the user:
- Environment: VPS / Chat with tokens / Cold start (local only)
- VPS health: all green / issues found
- Repos on VPS: which cloned successfully
- Available commands: /vps-status, /vps-logs, /vps-deploy, /vault-update
- Any action items (broken containers, missing tokens, etc.)
