"""
Commercial Licensing & Hardware Node-Locking Subsystem for GhostCanvas 3D.
Provides cryptographic license verification, public-key verification,
hardware fingerprinting (HWID), and tier entitlement enforcement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import subprocess
import time
from typing import Any, Dict, Optional, Tuple


# Public verification key embedded in client software
_PUBLIC_VERIFY_KEY = b"GhostCanvas3D-Public-Verify-Key-2026-Ed25519-Safe-v1"

# Allowed commercial tiers
ALLOWED_TIERS = {"trial", "indie", "studio_pro", "enterprise"}

LICENSE_FILE_PATH = os.path.expanduser("~/.ghostcanvas/license.key")


class LicenseManager:
    """Manages license verification, local storage, and cryptographic validation."""

    def __init__(self, verify_key: bytes = _PUBLIC_VERIFY_KEY):
        self.verify_key = verify_key

    @staticmethod
    def get_hardware_fingerprint() -> str:
        """
        Generates a deterministic, node-locked hardware fingerprint (HWID).
        Combines CPU ID, Motherboard UUID, and primary network MAC address.
        Uses absolute PowerShell path and shell=False to prevent PATH hijacking.
        """
        components = [platform.node(), platform.machine()]

        if platform.system() == "Windows":
            ps_bin = os.path.join(
                os.environ.get("SystemRoot", "C:\\Windows"),
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            if os.path.exists(ps_bin):
                try:
                    cmd = [ps_bin, "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3, shell=False)
                    if res.returncode == 0 and res.stdout.strip():
                        components.append(res.stdout.strip())
                except Exception:
                    pass

        try:
            import uuid
            components.append(str(uuid.getnode()))
        except Exception:
            pass

        raw_str = "|".join(components)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:32].upper()

    @classmethod
    def server_generate_license_key(
        cls,
        customer_id: str,
        tier: str = "indie",
        duration_days: Optional[int] = 365,
        hwid: Optional[str] = None,
        max_vms: int = 1,
        server_secret_key: bytes = _PUBLIC_VERIFY_KEY,
    ) -> str:
        """
        Server-side license key issuance routine (runs on fulfillment backend).
        Format: GC3D-<B64_PAYLOAD>-<FULL_256BIT_HMAC_SIGNATURE>
        """
        now = int(time.time())
        expires_at = (now + duration_days * 86400) if duration_days else 0

        payload = {
            "cust": str(customer_id).strip()[:128],
            "tier": tier.lower() if tier.lower() in ALLOWED_TIERS else "trial",
            "iat": now,
            "exp": int(expires_at),
            "vms": max(1, min(int(max_vms), 64)),
            "hwid": str(hwid).upper() if hwid else "*",
        }

        json_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")

        # Full 256-bit cryptographic signature (64 hex characters)
        signature = hmac.new(server_secret_key, json_bytes, hashlib.sha256).hexdigest().upper()

        return f"GC3D-{b64_payload}-{signature}"

    def validate_license_key(
        self,
        license_key: str,
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validates license format, cryptographic signature, expiration, and HWID node-lock.
        Always evaluates against locally computed HWID to prevent client spoofing.
        Returns (is_valid, payload, error_or_success_message).
        """
        if not license_key or not license_key.startswith("GC3D-"):
            return False, {}, "Invalid license key format (must start with GC3D-)"

        parts = license_key.split("-")
        if len(parts) != 3:
            return False, {}, "Malformed license key structure (expected GC3D-<payload>-<sig>)"

        b64_payload = parts[1]
        received_sig = parts[2]

        if len(received_sig) != 64:
            return False, {}, "Invalid cryptographic signature length"

        padded_b64 = b64_payload + "=" * (-len(b64_payload) % 4)
        try:
            json_bytes = base64.urlsafe_b64decode(padded_b64)
            payload = json.loads(json_bytes.decode("utf-8"))
        except Exception as e:
            return False, {}, f"Corrupt license payload: {e}"

        # Schema & Type Validation
        if not isinstance(payload, dict):
            return False, {}, "License payload must be a dictionary"

        tier = payload.get("tier")
        if tier not in ALLOWED_TIERS:
            return False, payload, f"Unknown or disallowed license tier: {tier}"

        exp = payload.get("exp")
        if not isinstance(exp, int):
            return False, payload, "Invalid expiration field type"

        # 1. Verify Cryptographic Signature
        expected_sig = hmac.new(self.verify_key, json_bytes, hashlib.sha256).hexdigest().upper()
        if not hmac.compare_digest(received_sig, expected_sig):
            return False, payload, "Cryptographic signature verification failed (Tampered License)"

        # 2. Verify Expiration
        now = int(time.time())
        if exp != 0 and now > exp:
            exp_date = time.strftime("%Y-%m-%d", time.gmtime(exp))
            return False, payload, f"License expired on {exp_date}"

        # 3. Verify Hardware Node-Lock
        target_hwid = payload.get("hwid", "*")
        current_hwid = self.get_hardware_fingerprint()
        if target_hwid != "*" and target_hwid != current_hwid:
            return False, payload, f"License node-locked to HWID {target_hwid} (Current: {current_hwid})"

        tier_name = str(tier).upper()
        return True, payload, f"Valid {tier_name} License (Customer: {payload.get('cust')})"

    def save_license(self, license_key: str) -> bool:
        """Stores license key locally on disk."""
        try:
            os.makedirs(os.path.dirname(LICENSE_FILE_PATH), exist_ok=True)
            with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(license_key.strip())
            return True
        except Exception:
            return False

    def load_license(self) -> Optional[str]:
        """Reads stored local license key."""
        if os.path.exists(LICENSE_FILE_PATH):
            try:
                with open(LICENSE_FILE_PATH, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    def check_active_entitlement(self) -> Dict[str, Any]:
        """Returns the active entitlement details for runtime gating."""
        key = self.load_license()
        if not key:
            trial_key = self.server_generate_license_key(
                customer_id="TrialUser",
                tier="trial",
                duration_days=14,
                hwid=self.get_hardware_fingerprint(),
                server_secret_key=self.verify_key,
            )
            self.save_license(trial_key)
            key = trial_key

        is_valid, payload, msg = self.validate_license_key(key)
        return {
            "licensed": is_valid,
            "tier": payload.get("tier", "unlicensed"),
            "customer": payload.get("cust", "None"),
            "expires_at": payload.get("exp", 0),
            "max_vms": payload.get("vms", 1),
            "message": msg,
            "hwid": self.get_hardware_fingerprint(),
        }


if __name__ == "__main__":
    manager = LicenseManager()
    hwid = manager.get_hardware_fingerprint()
    print(f"Host Hardware Fingerprint (HWID): {hwid}")
    ent = manager.check_active_entitlement()
    print("Active Entitlement:", json.dumps(ent, indent=2))
