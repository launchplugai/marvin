Get logs from a Docker container on the VPS.

Usage: /vps-logs <project-name>
If no project name given, show logs for claude-hub.

## Token Setup
Load tokens: `source .env` or use `$ANTHROPIC_API_KEY` from env.
Set: `TOKEN="${HOSTINGER_API_TOKEN:-$ANTHROPIC_API_KEY}"`
If no token available, tell user to run /bootstrap first.

## Steps
1. GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/{project-name}/logs
   - Auth: `Bearer $TOKEN`
2. Parse the JSON response
3. Show entries from the main service (skip [build] unless requested)
4. Show the last 50 entries with timestamps

## Available Projects
claude-hub, key-locker, marvin-skills, ollama-wmf4, openclaw-quzk
