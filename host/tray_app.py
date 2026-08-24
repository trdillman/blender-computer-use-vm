"""
GhostCanvas 3D - Desktop Companion & System Tray Manager.
Provides status monitoring, one-click VM controls, snapshot resets,
and license activation from the Windows system tray.
"""

from __future__ import annotations


import sys
import time
from typing import Any, Dict

try:
    from licensing import LicenseManager
    from vm_controller import VMController
except ImportError:
    from .licensing import LicenseManager  # type: ignore
    from .vm_controller import VMController  # type: ignore


class GhostCanvasTrayManager:
    """Manages the background system tray status and quick actions."""

    def __init__(self):
        self.vm_ctrl = VMController()
        self.license_mgr = LicenseManager()
        self.is_running = True
        self._status_cache: Dict[str, Any] = {}

    def get_system_summary(self) -> Dict[str, Any]:
        """Collects current VM state and license entitlement."""
        entitlement = self.license_mgr.check_active_entitlement()
        vm_status = self.vm_ctrl.get_status()

        summary = {
            "license_tier": entitlement.get("tier", "unlicensed").upper(),
            "license_customer": entitlement.get("customer", "N/A"),
            "hwid": entitlement.get("hwid", "N/A"),
            "vm_state": vm_status.get("vm", {}).get("State", "Stopped") if vm_status.get("status") == "ok" else "Unknown",
            "timestamp": time.time(),
        }
        self._status_cache = summary
        return summary

    def action_start_vm(self) -> str:
        res = self.vm_ctrl.start()
        return f"Start VM: {res.get('status')}"

    def action_reset_golden(self) -> str:
        res = self.vm_ctrl.restore_snapshot(snapshot_name="golden_base")
        return f"Snapshot Reset: {res.get('status')} in {res.get('duration_seconds', 0)}s"

    def action_activate_license(self, key: str) -> str:
        is_valid, payload, msg = self.license_mgr.validate_license_key(key)
        if is_valid:
            self.license_mgr.save_license(key)
            return f"Success: Activated {payload.get('tier').upper()} tier"
        return f"Failed: {msg}"

    def run_cli_dashboard(self):
        """Displays formatted terminal status dashboard."""
        summary = self.get_system_summary()
        print("\n================================================================================")
        print("   GhostCanvas 3D - Desktop Companion Manager")
        print("================================================================================")
        print(f" License Tier:     {summary['license_tier']} ({summary['license_customer']})")
        print(f" Hardware ID:      {summary['hwid']}")
        print(f" Hyper-V VM State: {summary['vm_state']}")
        print("--------------------------------------------------------------------------------")
        print(" Available Controls:")
        print("  1. Start Isolated VM (python host/tray_app.py --start)")
        print("  2. Reset to Golden Baseline (python host/tray_app.py --reset)")
        print("  3. Activate License (python host/tray_app.py --activate <KEY>)")
        print("  4. Start Host MCP Server (python host/mcp_server.py)")
        print("================================================================================\n")


if __name__ == "__main__":
    manager = GhostCanvasTrayManager()

    if "--start" in sys.argv:
        print(manager.action_start_vm())
    elif "--reset" in sys.argv:
        print(manager.action_reset_golden())
    elif "--activate" in sys.argv and len(sys.argv) > 2:
        print(manager.action_activate_license(sys.argv[2]))
    else:
        manager.run_cli_dashboard()
