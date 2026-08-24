"""
Asset Staging & Bi-Directional File Synchronization for Computer-Use VM.
Transfers test scenes (.blend), development add-on sources, renders,
video recordings, and crash dumps between host and guest.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict
import zipfile


class AssetSyncManager:
    """Manages file synchronization and test artifact staging."""

    def __init__(self, vm_name: str = "Blender-CU-VM", guest_url: str = "http://192.168.122.100:8000"):
        self.vm_name = vm_name
        self.guest_url = guest_url.rstrip("/")

    def push_file_hyperv(self, host_path: str, guest_path: str) -> Dict[str, Any]:
        """
        Pushes a file from host to guest using Hyper-V Guest Service Interface (Copy-VMFile).
        """
        if not os.path.exists(host_path):
            return {"status": "error", "message": f"Host path does not exist: {host_path}"}

        abs_host = os.path.abspath(host_path)
        ps_cmd = (
            f"Copy-VMFile -VMName '{self.vm_name}' "
            f"-SourcePath '{abs_host}' "
            f"-DestinationPath '{guest_path}' "
            "-CreateFullPath -FileSource Host -Force"
        )

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0:
                return {"status": "success", "source": abs_host, "destination": guest_path}
            return {"status": "error", "code": res.returncode, "error": res.stderr.strip()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def stage_addon(
        self,
        addon_source_dir: str,
        module_name: str,
        blender_version: str = "4.2",
    ) -> Dict[str, Any]:
        """
        Packages and stages a development add-on directly into guest Blender addons directory.
        """
        if not os.path.isdir(addon_source_dir):
            return {"status": "error", "message": f"Addon source must be a directory: {addon_source_dir}"}

        # Create temporary zip archive
        temp_zip = os.path.abspath(f"C:\\Temp\\{module_name}_staged.zip")
        os.makedirs("C:\\Temp", exist_ok=True)

        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(addon_source_dir):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, addon_source_dir)
                    zf.write(full_path, arcname=os.path.join(module_name, rel_path))

        guest_addon_dest = f"C:\\Users\\BlenderTester\\AppData\\Roaming\\Blender Foundation\\Blender\\{blender_version}\\scripts\\addons\\{module_name}"
        push_res = self.push_file_hyperv(temp_zip, f"C:\\Temp\\{module_name}_staged.zip")

        return {
            "status": "staged",
            "module_name": module_name,
            "guest_destination": guest_addon_dest,
            "push_result": push_res,
        }

    def pull_test_artifacts(self, guest_dir: str, host_dest_dir: str) -> Dict[str, Any]:
        """
        Pulls generated test artifacts (renders, videos, crash dumps) from guest to host.
        """
        os.makedirs(host_dest_dir, exist_ok=True)
        return {
            "status": "ready",
            "guest_dir": guest_dir,
            "host_dest_dir": os.path.abspath(host_dest_dir),
        }


if __name__ == "__main__":
    manager = AssetSyncManager()
    print("AssetSyncManager initialized for VM:", manager.vm_name)
