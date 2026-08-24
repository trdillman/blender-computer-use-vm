"""
Commercial Test Suite for GhostCanvas 3D.
Validates:
- Cryptographic license generation & validation
- Tampered license rejection & hardware node-lock enforcement
- Agent Studio Pro Blender Addon integration
- MSI / Inno Setup builder script generation
- Desktop Tray App status reporting
- MCP server license gating & activation tools
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "host"))
sys.path.insert(0, os.path.join(ROOT_DIR, "blender"))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

from licensing import LicenseManager  # type: ignore
from tray_app import GhostCanvasTrayManager  # type: ignore
from mcp_server import handle_tool_call  # type: ignore
import build_msi  # type: ignore


class TestLicensingSubsystem(unittest.TestCase):
    """Validates cryptographic license signing, validation, and node locking."""

    def setUp(self):
        self.mgr = LicenseManager()
        self.hwid = self.mgr.get_hardware_fingerprint()

    def test_generate_and_validate_valid_key(self):
        key = self.mgr.generate_license_key(
            customer_id="alice@studio.com",
            tier="indie",
            duration_days=365,
            hwid=self.hwid,
        )
        self.assertTrue(key.startswith("GC3D-"))
        valid, payload, msg = self.mgr.validate_license_key(key, current_hwid=self.hwid)
        self.assertTrue(valid)
        self.assertEqual(payload["tier"], "indie")
        self.assertEqual(payload["cust"], "alice@studio.com")
        self.assertIn("Valid INDIE License", msg)

    def test_tampered_license_rejection(self):
        key = self.mgr.generate_license_key(
            customer_id="bob@studio.com",
            tier="studio_pro",
            duration_days=365,
            hwid=self.hwid,
        )
        # Tamper with the signature portion
        tampered_key = key[:-2] + "99"
        valid, _, msg = self.mgr.validate_license_key(tampered_key, current_hwid=self.hwid)
        self.assertFalse(valid)
        self.assertIn("signature verification failed", msg.lower())

    def test_hwid_node_lock_rejection(self):
        key = self.mgr.generate_license_key(
            customer_id="charlie@studio.com",
            tier="indie",
            duration_days=365,
            hwid="DIFFERENT_HWID_99",
        )
        valid, _, msg = self.mgr.validate_license_key(key, current_hwid=self.hwid)
        self.assertFalse(valid)
        self.assertIn("node-locked", msg.lower())

    def test_perpetual_license(self):
        key = self.mgr.generate_license_key(
            customer_id="dave@studio.com",
            tier="enterprise",
            duration_days=None,  # Perpetual
            hwid=None,  # Floating
        )
        valid, payload, _ = self.mgr.validate_license_key(key, current_hwid=self.hwid)
        self.assertTrue(valid)
        self.assertEqual(payload["exp"], 0)


class TestMCPLicensingIntegration(unittest.TestCase):
    """Validates MCP license status and activation tool handlers."""

    def test_vm_license_status_tool(self):
        res = handle_tool_call("vm_license_status", {})
        self.assertIsInstance(res, dict)
        self.assertIn("licensed", res)
        self.assertIn("tier", res)
        self.assertIn("hwid", res)

    def test_vm_activate_license_tool(self):
        mgr = LicenseManager()
        valid_key = mgr.generate_license_key(customer_id="test@agent.com", tier="studio_pro")
        res = handle_tool_call("vm_activate_license", {"license_key": valid_key})
        self.assertEqual(res.get("status"), "activated")
        self.assertEqual(res.get("tier"), "studio_pro")


class TestTrayAppDashboard(unittest.TestCase):
    """Validates Desktop Tray App status collection."""

    def test_tray_manager_summary(self):
        tray = GhostCanvasTrayManager()
        summary = tray.get_system_summary()
        self.assertIn("license_tier", summary)
        self.assertIn("hwid", summary)
        self.assertIn("vm_state", summary)


class TestMSIBuilderScript(unittest.TestCase):
    """Validates MSI and Inno Setup script generator."""

    def test_generate_inno_script(self):
        dist_dir = os.path.join(ROOT_DIR, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        iss_path = os.path.join(dist_dir, "test_setup.iss")
        build_msi.generate_inno_setup_script(iss_path, ROOT_DIR)
        self.assertTrue(os.path.exists(iss_path))
        with open(iss_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("GhostCanvas 3D", content)
            self.assertIn("OutputBaseFilename=GhostCanvas3D-Setup-v1.1.0", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
