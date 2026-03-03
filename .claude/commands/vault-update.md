Update the vault (key-locker) on the VPS.

This updates secrets, entrypoint.sh, or bootstrap.sh stored on the locker-vault Docker volume.

Steps:
1. Fetch current key-locker compose: GET /api/vps/v1/virtual-machines/1405440/docker/key-locker
2. The compose contains base64-encoded scripts. To modify:
   - Decode the base64 blob for entrypoint.sh or bootstrap.sh
   - Make changes
   - Re-encode to base64
   - Replace in compose
3. To add/change keys: modify the printf line that writes to /vault/.keys.enc
4. Delete old key-locker: DELETE /api/vps/v1/virtual-machines/1405440/docker/key-locker/down
5. Wait for action to complete
6. Create new key-locker: POST /api/vps/v1/virtual-machines/1405440/docker
   - Body: {"project_name": "key-locker", "content": "<updated compose>"}
   - IMPORTANT: content must be <= 8192 characters
7. Restart claude-hub to pick up changes: POST .../docker/claude-hub/restart

Current vault contents:
- .keys.enc: ANTHROPIC_API_KEY, GH_TOKEN
- entrypoint.sh: main container startup (installs deps, runs bootstrap, starts tmux)
- bootstrap.sh: clones repos, syncs CLAUDE.md, configures Claude Code, syncs memory
