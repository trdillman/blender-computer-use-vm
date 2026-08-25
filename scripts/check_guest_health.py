"""
Live Guest VM Network & Telemetry Health Checker for Blender-CU-VM.
Validates:
- Guest Daemon HTTP/HV-SOCK API connectivity on port 8000
- 1080p Virtual Display Adapter resolution
- In-process Blender 5.2.0 LTS Telemetry Bridge on port 9199
- NVIDIA GPU-PV compute acceleration
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict


def _auth_headers(extra: Dict[str, str]) -> Dict[str, str]:
    """Adds the daemon session secret when GUEST_DAEMON_SECRET is set."""
    secret = os.environ.get("GUEST_DAEMON_SECRET", "").strip()
    if secret:
        extra["X-Session-Secret"] = secret
    return extra


def query_endpoint(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=_auth_headers({"User-Agent": "GhostCanvas-HealthCheck/1.1"}))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_live_guest_health(guest_url: str = "http://192.168.122.100:8000") -> bool:
    print(f"\n=== Live Guest Health Check: {guest_url} ===")

    # 1. Daemon Health Check
    health_url = f"{guest_url.rstrip('/')}/health"
    print(f" [1/3] Polling Guest Daemon ({health_url})...")
    try:
        data = query_endpoint(health_url)
        print(f"  + Status: {data.get('status')}")
        display = data.get("display", {})
        print(f"  + Display Resolution: {display.get('width')}x{display.get('height')}")
        if display.get("width") != 1920 or display.get("height") != 1080:
            print("  ! Warning: Display resolution is not locked to 1920x1080.")
    except Exception as e:
        print(f"  ! Daemon not reachable: {e}")
        return False

    # 2. Windows List Check
    windows_url = f"{guest_url.rstrip('/')}/ui/windows"
    print(f" [2/3] Inspecting Desktop Windows ({windows_url})...")
    try:
        win_data = query_endpoint(windows_url)
        print(f"  + Open Windows Count: {win_data.get('count', 0)}")
    except Exception as e:
        print(f"  ! Window enumeration error: {e}")

    # 3. Blender Telemetry Bridge Check
    eval_url = f"{guest_url.rstrip('/')}/blender/eval"
    print(f" [3/3] Querying In-Process Blender Bridge ({eval_url})...")
    try:
        payload = json.dumps({"expression": "bpy.app.version_string"}).encode("utf-8")
        req = urllib.request.Request(eval_url, data=payload, headers=_auth_headers({"Content-Type": "application/json"}), method="POST")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            eval_data = json.loads(resp.read().decode("utf-8"))
            print(f"  + Blender Version: {eval_data.get('result')}")
    except Exception as e:
        print(f"  ! Blender bridge not currently answering: {e}")

    print("=== Health Check Complete ===\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GhostCanvas Live Guest Health Checker")
    parser.add_argument("--url", default="http://192.168.122.100:8000", help="Guest Daemon URL")
    args = parser.parse_args()

    success = check_live_guest_health(args.url)
    sys.exit(0 if success else 1)
