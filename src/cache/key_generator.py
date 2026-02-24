#!/usr/bin/env python3
"""
Cache Key Generation — State-Aware Caching
Phase 1 Day 2

Implements:
- generate_cache_key(intent, project, state) → deterministic key
- get_project_state(project) → git branch, last commit, deploy status
- Key changes when project state changes (cache miss on new commit)
- Same message + same state = cache hit (key identical)
"""

import hashlib
import json
import logging
import subprocess
import os
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class CacheKeyGenerator:
    """
    Generate deterministic cache keys that incorporate project state.
    
    Design:
    - Cache key = hash(intent + project + state_signature)
    - State signature includes: git branch, last commit, deploy status
    - Key changes when: commit happens, branch changes, deploy occurs
    - Same message + same state = identical key = cache hit
    """
    
    def __init__(self, projects_root: str = None):
        """Initialize key generator with projects root directory."""
        if projects_root is None:
            projects_root = os.path.expanduser("~/projects")
        
        self.projects_root = projects_root
        self.state_cache = {}  # In-memory cache of project states
    
    def generate_cache_key(self, intent: str, project: str = None, state_sig: str = None) -> str:
        """
        Generate deterministic cache key.
        
        Args:
            intent: Classification (status_check, how_to, debugging, etc.)
            project: Project context (BetApp, DevOps, etc.)
            state_sig: Pre-computed state signature (if None, will fetch)
        
        Returns:
            Deterministic hex string (12 chars)
        
        Design:
            key = SHA256(intent:project:state_sig)[:12]
            - If state changes (new commit), key changes, cache miss occurs
            - If nothing changes, key is identical, cache hit
        """
        if state_sig is None and project:
            state_sig = self.get_project_state_sig(project)
        else:
            state_sig = state_sig or "global"
        
        key_data = f"{intent}:{project or 'global'}:{state_sig}"
        key = hashlib.sha256(key_data.encode()).hexdigest()[:12]
        
        logger.debug(f"Generated key: {key} (intent={intent}, project={project}, state={state_sig})")
        return key
    
    def get_project_state(self, project: str) -> Dict[str, Any]:
        """
        Fetch current project state: git branch, last commit, deploy status.
        
        Args:
            project: Project directory name or full path
        
        Returns:
            {
                branch: "main",
                last_commit: "a1b2c3d",
                last_commit_msg: "Fix import error",
                last_commit_author: "Alice",
                last_commit_time: 1708620000,
                deploy_status: "running",
                deploy_version: "v2.5.1",
            }
        """
        # Check cache first (avoid repeated git calls in same session)
        if project in self.state_cache:
            return self.state_cache[project]
        
        state = {
            "branch": None,
            "last_commit": None,
            "last_commit_msg": None,
            "last_commit_author": None,
            "last_commit_time": None,
            "deploy_status": None,
            "deploy_version": None,
        }
        
        # Find project directory
        project_dir = self._find_project_dir(project)
        if not project_dir:
            logger.warning(f"Project {project} not found")
            return state
        
        # Git state
        try:
            # Current branch
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            state["branch"] = branch
            
            # Last commit hash (short)
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            state["last_commit"] = commit
            
            # Last commit message
            msg = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            state["last_commit_msg"] = msg
            
            # Last commit author
            author = subprocess.run(
                ["git", "log", "-1", "--pretty=%an"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            state["last_commit_author"] = author
            
            # Last commit timestamp
            try:
                timestamp = int(subprocess.run(
                    ["git", "log", "-1", "--pretty=%at"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout.strip())
                state["last_commit_time"] = timestamp
            except:
                pass
            
            logger.debug(f"Git state for {project}: branch={branch}, commit={commit}")
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Git command timeout for {project}")
        except Exception as e:
            logger.warning(f"Error fetching git state for {project}: {e}")
        
        # Deploy status (check for common deployment markers)
        state["deploy_status"] = self._get_deploy_status(project_dir, project)
        state["deploy_version"] = self._get_deploy_version(project_dir)
        
        # Cache it
        self.state_cache[project] = state
        
        return state
    
    def get_project_state_sig(self, project: str) -> str:
        """
        Get state signature (hash of important state).
        
        This is what changes when project state changes.
        If signature is same, cache key is same (cache hit).
        If signature differs, cache key differs (cache miss).
        """
        state = self.get_project_state(project)
        
        # Include: branch + commit + deploy status
        sig_data = f"{state['branch']}:{state['last_commit']}:{state['deploy_status']}"
        sig = hashlib.sha256(sig_data.encode()).hexdigest()[:8]
        
        logger.debug(f"State signature for {project}: {sig}")
        return sig
    
    def _find_project_dir(self, project: str) -> Optional[Path]:
        """Find project directory by name or return as-is if full path."""
        if os.path.isdir(project):
            return Path(project)
        
        # Try projects_root
        candidate = Path(self.projects_root) / project
        if candidate.is_dir():
            return candidate
        
        # Try common locations
        for base in [
            Path.home() / "projects",
            Path.home() / "dev",
            Path.home() / "src",
            Path("/tmp"),
        ]:
            candidate = base / project
            if candidate.is_dir() and (candidate / ".git").exists():
                return candidate
        
        return None
    
    def _get_deploy_status(self, project_dir: Path, project_name: str) -> Optional[str]:
        """
        Detect deploy status.
        
        Checks for:
        - Docker container running
        - Process running
        - systemd service status
        - Custom status files
        """
        try:
            # Check if it's a running Docker container
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={project_name}", "-q"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip():
                return "running_docker"
            
            # Check systemd (if available)
            result = subprocess.run(
                ["systemctl", "--user", "is-active", project_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip() == "active":
                return "running_systemd"
            
            # Check for .status file
            status_file = project_dir / ".status"
            if status_file.exists():
                return status_file.read_text().strip()
            
        except Exception as e:
            logger.debug(f"Error checking deploy status: {e}")
        
        return None
    
    def _get_deploy_version(self, project_dir: Path) -> Optional[str]:
        """Get deployed version from various sources."""
        try:
            # Check VERSION file
            version_file = project_dir / "VERSION"
            if version_file.exists():
                return version_file.read_text().strip()
            
            # Check package.json
            package_file = project_dir / "package.json"
            if package_file.exists():
                with open(package_file) as f:
                    pkg = json.load(f)
                    return pkg.get("version")
            
            # Check pyproject.toml
            pyproject_file = project_dir / "pyproject.toml"
            if pyproject_file.exists():
                with open(pyproject_file) as f:
                    content = f.read()
                    # Simple parsing
                    for line in content.split("\n"):
                        if "version" in line and "=" in line:
                            return line.split("=")[1].strip().strip('"\'')
            
        except Exception as e:
            logger.debug(f"Error getting deploy version: {e}")
        
        return None
    
    def invalidate_project(self, project: str):
        """
        Invalidate cached state for a project.
        Call this after git commit, deploy, etc.
        """
        if project in self.state_cache:
            del self.state_cache[project]
            logger.info(f"Invalidated cached state for {project}")


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    gen = CacheKeyGenerator()
    
    # Test key generation
    key1 = gen.generate_cache_key("status_check", "BetApp", "abc123")
    key2 = gen.generate_cache_key("status_check", "BetApp", "abc123")
    key3 = gen.generate_cache_key("status_check", "BetApp", "xyz789")
    
    print(f"\nSame inputs → same key: {key1 == key2} (both {key1})")
    print(f"Different state → different key: {key1 != key3} ({key1} vs {key3})")
    
    # Test state detection (if in a git repo)
    print("\nProject state detection:")
    state = gen.get_project_state(".")
    for k, v in state.items():
        print(f"  {k}: {v}")
