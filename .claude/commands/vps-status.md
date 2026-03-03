Check the VPS and all Docker containers.

## Token Setup
First, load tokens. Try in order:
1. `source .env` (chat sessions)
2. Use `$ANTHROPIC_API_KEY` from environment (VPS sessions)
3. If neither works, tell the user: "No API token found. Run /bootstrap first."

Set: `TOKEN="${HOSTINGER_API_TOKEN:-$ANTHROPIC_API_KEY}"`

## Steps
1. GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker
   - Auth: `Bearer $TOKEN`
2. For each project, report: name, state, container uptime, ports
3. For any container NOT in "running" state, get its logs
4. Report a summary table and flag any issues

## Expected Projects
| Project | Expected State |
|---------|---------------|
| claude-hub | running |
| key-locker | exited (normal — run-once) |
| marvin-skills | running |
| ollama-wmf4 | running (healthy) |
| openclaw-quzk | running |
