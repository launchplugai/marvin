Deploy or update a Docker project on the VPS.

Usage: /vps-deploy <project-name>

## Token Setup
Load tokens: `source .env` or use `$ANTHROPIC_API_KEY` from env.
Set: `TOKEN="${HOSTINGER_API_TOKEN:-$ANTHROPIC_API_KEY}"`
If no token available, tell user to run /bootstrap first.

## Steps
1. Read the compose content (from local file, user input, or ask)
2. Check compose content is <= 8192 characters (Hostinger hard limit)
3. Check if project already exists:
   - GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker/{name}
4. If exists: POST to .../docker/{name}/update with {"content": "..."}
5. If new: POST to .../docker with {"project_name": "...", "content": "..."}
6. Poll action status until success/failure:
   - GET .../actions/{actionId}
7. Get and display project logs

## Constraints
- Compose content max: 8192 characters
- VM ID: 1405440
- Auth: Bearer $TOKEN
