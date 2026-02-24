#!/usr/bin/env python3
"""
Git Invalidation Hook
Phase 1 Day 2

Automatically clears cache when project state changes (git commits, branch changes).

Installation:
    python install_git_hooks.py

This script runs as a git post-commit hook and invalidates cache for the project.
"""

import subprocess
import sys
import os
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_project_name():
    """Get project name from git remote or directory."""
    try:
        # Try to get from git remote
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.stdout:
            # Extract project name from URL
            # https://github.com/org/project.git → project
            url = result.stdout.strip()
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            return name
    except:
        pass
    
    # Fallback: use directory name
    return Path.cwd().name


def get_cache_db_path():
    """Find the cache database file."""
    candidates = [
        Path.home() / ".openclaw/workspace/cache/responses.db",
        Path.home() / ".cache/marvin/responses.db",
        Path.cwd() / ".marvin_cache.db",
        "/tmp/marvin_cache.db",
    ]
    
    for path in candidates:
        if path.exists():
            return str(path)
    
    # Default (will be created if needed)
    return str(Path.home() / ".openclaw/workspace/cache/responses.db")


def invalidate_project_cache(project_name: str):
    """
    Invalidate cache for this project.
    
    Called after git commit to clear stale cached responses.
    """
    db_path = get_cache_db_path()
    
    logger.info(f"Invalidating cache for project: {project_name}")
    logger.info(f"Cache DB: {db_path}")
    
    try:
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count before
        cursor.execute("SELECT COUNT(*) FROM cache_entries WHERE project = ?", (project_name,))
        count_before = cursor.fetchone()[0]
        
        # Delete entries for this project
        cursor.execute(
            "DELETE FROM cache_entries WHERE project = ?",
            (project_name,)
        )
        
        # Get count after
        count_after = cursor.execute(
            "SELECT COUNT(*) FROM cache_entries WHERE project = ?",
            (project_name,)
        ).fetchone()[0]
        
        # Log invalidation
        cursor.execute(
            "INSERT INTO invalidation_log (timestamp, reason, target_type, target_value, keys_cleared) "
            "VALUES (strftime('%s', 'now'), ?, ?, ?, ?)",
            ("git_commit", "project", project_name, count_before - count_after)
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cache invalidated: {count_before} → {count_after} entries for {project_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        return False


def install_git_hook():
    """
    Install this script as a git post-commit hook.
    
    Usage: python git_invalidation.py install
    """
    hook_path = Path(".git/hooks/post-commit")
    
    if not hook_path.exists():
        hook_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create hook script
    hook_content = f"""#!/bin/bash
# Marvin Cache Invalidation Hook
# Auto-invalidates cache after git commits

python {Path(__file__).absolute()} hook
"""
    
    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)
    
    logger.info(f"Installed git hook: {hook_path}")


def main():
    """Entry point for git hook or manual invocation."""
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        # Install mode
        install_git_hook()
        return 0
    
    # Hook mode (called by git)
    project_name = get_project_name()
    success = invalidate_project_cache(project_name)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
