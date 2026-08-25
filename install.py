"""
Cross-Platform Python Installer & MCP Registrar for Blender Computer-Use VM.
Automates:
- Registering 'blender-cu-vm' MCP server into ~/.claude.json & ~/.omp/agent/config.yml
- Deploying 'blender-computer-use-vm' into ~/.omp/agent/managed-skills/
- Running verification and self-test suite
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_HOME = os.path.expanduser("~")


def register_claude_json() -> bool:
    """Injects blender-cu-vm MCP server into ~/.claude.json."""
    claude_json_path = os.path.join(USER_HOME, ".claude.json")
    print(f"Checking Claude configuration: {claude_json_path}")

    config_data = {}
    if os.path.exists(claude_json_path):
        try:
            with open(claude_json_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            # SAFETY: writing a fresh dict here would DESTROY the user's entire
            # Claude Code configuration. Refuse instead.
            print(f"  ! REFUSING to modify {claude_json_path}: existing file failed to parse ({e}).")
            print("    Back up or repair the file manually, then re-run.")
            sys.exit(1)

    if "mcpServers" not in config_data:
        config_data["mcpServers"] = {}

    mcp_script_path = os.path.join(ROOT_DIR, "host", "mcp_server.py")
    config_data["mcpServers"]["blender-cu-vm"] = {
        "command": "python",
        "args": [mcp_script_path],
        "env": {
            "BLENDER_VM_NAME": "Blender-CU-VM",
            "BLENDER_GUEST_URL": "http://192.168.122.100:8000",
        },
    }

    try:
        if os.path.exists(claude_json_path):
            backup_path = claude_json_path + time.strftime(".backup-%Y%m%d-%H%M%S")
            shutil.copy2(claude_json_path, backup_path)
            print(f"  + Backup written: {backup_path}")
        with open(claude_json_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        print(f"  + Successfully registered 'blender-cu-vm' in {claude_json_path}")
        return True
    except Exception as e:
        print(f"  ! Failed to write {claude_json_path}: {e}")
        return False


def deploy_managed_skill() -> bool:
    """Copies SKILL.md into ~/.omp/agent/managed-skills/blender-computer-use-vm/."""
    managed_skills_dir = os.path.join(USER_HOME, ".omp", "agent", "managed-skills", "blender-computer-use-vm")
    os.makedirs(managed_skills_dir, exist_ok=True)

    src_skill = os.path.join(ROOT_DIR, "skills", "blender-computer-use-vm", "SKILL.md")
    dest_skill = os.path.join(managed_skills_dir, "SKILL.md")

    if os.path.exists(src_skill):
        try:
            shutil.copy2(src_skill, dest_skill)
            print(f"  + Deployed managed skill to: {dest_skill}")
            return True
        except Exception as e:
            print(f"  ! Failed to copy skill: {e}")
            return False
    return False


def run_tests() -> bool:
    """Runs automated verification tests."""
    print("\nRunning Verification & Self-Test Suite...")
    security_script = os.path.join(ROOT_DIR, "tests", "test_security_boundaries.py")
    test_script = os.path.join(ROOT_DIR, "tests", "test_blender_user_story.py")
    iso_script = os.path.join(ROOT_DIR, "tests", "verify_isolation.py")

    res0 = subprocess.run([sys.executable, security_script])
    res1 = subprocess.run([sys.executable, test_script])
    res2 = subprocess.run([sys.executable, iso_script])
    return res0.returncode == 0 and res1.returncode == 0 and res2.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Blender Computer-Use VM & MCP Installer")
    parser.add_argument("--register-mcp", action="store_true", help="Register MCP server in ~/.claude.json")
    parser.add_argument("--deploy-skill", action="store_true", help="Deploy managed skill")
    parser.add_argument("--verify", action="store_true", help="Run test suite")
    parser.add_argument("--all", action="store_true", help="Perform complete registration, deployment & verification")

    args = parser.parse_args()

    if len(sys.argv) == 1 or args.all:
        print("=== Blender Computer-Use VM & MCP Server Setup ===")
        register_claude_json()
        deploy_managed_skill()
        run_tests()
        print("\nSetup complete! The 'blender-cu-vm' MCP server is ready for use.")
    else:
        if args.register_mcp:
            register_claude_json()
        if args.deploy_skill:
            deploy_managed_skill()
        if args.verify:
            run_tests()


if __name__ == "__main__":
    main()
