Bootstrap a new Claude Code session with full system context.

Run this at the start of any new chat to load all context.

Steps:
1. Read /home/user/marvin/CLAUDE.md for project context
2. Read /home/user/marvin/hub-card.md for VPS architecture
3. Check VPS status via Hostinger API:
   - GET https://developers.hostinger.com/api/vps/v1/virtual-machines/1405440/docker
   - Report container states
4. Check claude-hub logs for any errors
5. Summarize:
   - System health (all containers green?)
   - Any failed clones or restart loops?
   - Current repos on VPS
   - Available slash commands (/vps-status, /vps-logs, /vps-deploy, /vault-update)
