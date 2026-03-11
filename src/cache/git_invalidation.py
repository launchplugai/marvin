#!/usr/bin/env python3
"""
Git Invalidation Hook
Phase 1 Day 2

Automatically clears cache when project state changes (git commits, branch changes).

Installation:
    python -m src.cache.git_invalidation install

This script runs as a git post-commit hook and invalidates cache for the project.
It delegates all DB operations to CacheLayer — no direct SQLite access.
"""

import subprocess
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_project_name() -> str:
    """Get project name from git remote or directory."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout:
            url = result.stdout.strip()
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            return name
    except Exception:
        pass
    return Path.cwd().name


def invalidate_project_cache(project_name: str, db_path: str = None) -> bool:
    """
    Invalidate cache for this project using CacheLayer.

    Called after git commit to clear stale cached responses.
    """
    from .cache import CacheLayer

    logger.info(f"Invalidating cache for project: {project_name}")

    try:
        cache = CacheLayer(db_path)
        cleared = cache.clear_by_project(project_name, reason="git_commit")
        cache.close()
        logger.info(f"Cache invalidated: {cleared} entries cleared for {project_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        return False


def install_git_hook():
    """
    Install this script as a git post-commit hook.

    Usage: python -m src.cache.git_invalidation install
    """
    hook_path = Path(".git/hooks/post-commit")

    if not hook_path.parent.exists():
        logger.error("Not in a git repository (no .git/hooks)")
        return

    hook_content = f"""#!/bin/bash
# Marvin Cache Invalidation Hook
# Auto-invalidates cache after git commits

python3 -m src.cache.git_invalidation hook
"""

    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)
    logger.info(f"Installed git hook: {hook_path}")


def main():
    """Entry point for git hook or manual invocation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_git_hook()
        return 0

    # Hook mode (called by git)
    project_name = get_project_name()
    success = invalidate_project_cache(project_name)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
