"""
Hyper-V Virtual Machine Lifecycle & Snapshot Rollback Controller.
Provides programmatic control over VM power state, health monitoring,
instant snapshot restoration, and guest daemon readiness checks.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Any, Dict
import urllib.error
import urllib.request


class VMController:
    """Controls Hyper-V VM lifecycle and snapshot operations."""

    # VM names are interpolated into PowerShell command strings; restrict to
    # safe identifier characters so no shell metacharacters can sneak in.
    _VM_NAME_RE = re.compile(r"^[A-Za-z0-9_.\- ]{1,64}$")
    _SNAPSHOT_NAME_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,64}\Z")

    def __init__(self, vm_name: str = "Blender-CU-VM", guest_url: str = "http://192.168.122.100:8000"):
        if not self._VM_NAME_RE.match(vm_name or ""):
            raise ValueError(f"Invalid VM name (allowed: letters, digits, _ . - space, max 64): {vm_name!r}")
        self.vm_name = vm_name
        self.guest_url = guest_url.rstrip("/")

    def _run_ps(self, cmd: str, timeout: int = 15) -> Dict[str, Any]:
        """Runs a PowerShell command and returns structured result."""
        ps_cmd = ["powershell", "-NoProfile", "-Command", cmd]
        try:
            res = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "returncode": res.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "stdout": "", "stderr": str(e), "returncode": -1}

    def get_status(self) -> Dict[str, Any]:
        """Queries current VM state, CPU, Memory, and Uptime from Hyper-V."""
        cmd = f"Get-VM -Name '{self.vm_name}' | Select-Object Name, State, CPUUsage, MemoryAssigned, Uptime | ConvertTo-Json"
        res = self._run_ps(cmd)
        if res["success"] and res["stdout"]:
            try:
                data = json.loads(res["stdout"])
                return {"status": "ok", "vm": data}
            except Exception:
                pass
        return {"status": "error", "message": res["stderr"] or "VM not found"}

    def start(self) -> Dict[str, Any]:
        """Powers on the VM."""
        cmd = f"Start-VM -Name '{self.vm_name}' -ErrorAction SilentlyContinue"
        res = self._run_ps(cmd)
        return {"status": "started" if res["success"] else "error", "details": res}

    def stop(self, force: bool = False) -> Dict[str, Any]:
        """Powers off or shuts down the VM."""
        if force:
            cmd = f"Stop-VM -Name '{self.vm_name}' -TurnOff -Confirm:$false"
        else:
            cmd = f"Stop-VM -Name '{self.vm_name}' -Save -Confirm:$false"
        res = self._run_ps(cmd)
        return {"status": "stopped" if res["success"] else "error", "details": res}

    def restore_snapshot(self, snapshot_name: str = "golden_base") -> Dict[str, Any]:
        """
        Instantly reverts VM to named snapshot and ensures it is running.
        """
        if not self._SNAPSHOT_NAME_RE.match(snapshot_name or ""):
            raise ValueError(
                "Invalid snapshot name (allowed: ASCII letters, digits, _, -, ., max 64): "
                f"{snapshot_name!r}"
            )
        start_time = time.time()
        cmd = (
            f"Restore-VMSnapshot -VMName '{self.vm_name}' -Name '{snapshot_name}' -Confirm:$false; "
            f"Start-VM -Name '{self.vm_name}' -ErrorAction SilentlyContinue"
        )
        res = self._run_ps(cmd, timeout=20)
        elapsed = round(time.time() - start_time, 2)

        return {
            "status": "restored" if res["success"] else "error",
            "snapshot": snapshot_name,
            "duration_seconds": elapsed,
            "details": res,
        }

    def wait_for_daemon_ready(self, timeout_s: float = 30.0, poll_interval: float = 0.5) -> bool:
        """
        Polls guest daemon /health endpoint until responsive.
        """
        url = f"{self.guest_url}/health"
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(poll_interval)

        return False


if __name__ == "__main__":
    controller = VMController()
    print("VMController initialized. Querying status for:", controller.vm_name)
    print(controller.get_status())
