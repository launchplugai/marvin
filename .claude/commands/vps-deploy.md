Deploy or update a Docker project on the VPS.

Usage: /vps-deploy <project-name>

Steps:
1. Read the project's docker-compose.yml from the local repo (or ask for compose content)
2. If project exists: POST to /api/vps/v1/virtual-machines/1405440/docker/{name}/update
3. If project is new: POST to /api/vps/v1/virtual-machines/1405440/docker with project_name and content
4. Poll the action status until success/failure
5. Get and display the project logs

Important constraints:
- Compose content must be <= 8192 characters
- VM ID: 1405440
- Auth: Bearer token from ANTHROPIC_API_KEY
