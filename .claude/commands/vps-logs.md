Get logs from a Docker container on the VPS.

Usage: /vps-logs <project-name>

If no project name given, show logs for claude-hub.

Steps:
1. Call GET /api/vps/v1/virtual-machines/1405440/docker/{project-name}/logs
2. Parse the JSON response and display log entries with timestamps
3. Show the last 50 entries from the main service (not [build])

Available projects: claude-hub, key-locker, marvin-skills, ollama-wmf4, openclaw-quzk
