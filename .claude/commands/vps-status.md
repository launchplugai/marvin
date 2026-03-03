Check the VPS and all Docker containers.

Steps:
1. Call the Hostinger API to list all Docker projects on VM 1405440
2. For any container not in "running" state, get its logs
3. Report a summary table: project name, state, uptime, ports
4. Flag any issues (crashed containers, failed clones, restart loops)

API base: https://developers.hostinger.com/api/vps/v1
VM ID: 1405440
Auth: Bearer token from ANTHROPIC_API_KEY (same key used for Hostinger API)
