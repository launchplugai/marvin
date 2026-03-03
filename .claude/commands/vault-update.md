Update the vault (key-locker) on the VPS.

This updates secrets, entrypoint.sh, or bootstrap.sh on the locker-vault Docker volume.

## Token Setup
Load tokens: `source .env` or use `$ANTHROPIC_API_KEY` from env.
Set: `TOKEN="${HOSTINGER_API_TOKEN:-$ANTHROPIC_API_KEY}"`
If no token available, tell user to run /bootstrap first.

## Steps
1. Fetch current key-locker compose:
   GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/key-locker
2. The compose contains:
   - A `printf` line writing secrets to /vault/.keys.enc
   - Base64-encoded entrypoint.sh and bootstrap.sh
3. To modify scripts: decode base64, edit, re-encode, replace in compose
4. To add/change keys: modify the printf line
5. Delete old key-locker:
   DELETE .../docker/key-locker/down → wait for action success
6. Create new key-locker:
   POST .../docker with {"project_name": "key-locker", "content": "<updated compose>"}
   IMPORTANT: content must be <= 8192 characters
7. Restart claude-hub to pick up changes:
   POST .../docker/claude-hub/restart

## Current Vault Contents
- .keys.enc: HOSTINGER_API_TOKEN (named ANTHROPIC_API_KEY), GH_TOKEN
- entrypoint.sh: container startup (deps, bootstrap, tmux watchdog)
- bootstrap.sh: clone repos, sync CLAUDE.md, configure settings, sync memory

## Source of Truth
The canonical versions of entrypoint.sh and bootstrap.sh are in `infra/` in this repo.
Edit those files, then use this command to push them to the vault.
