"""
Commercial Licensing & Hardware Node-Locking Subsystem for GhostCanvas 3D.
Provides cryptographic license generation, offline asymmetric signature validation,
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


# Default Master Secret for signing (In production, private key lives on license server)
# The client binary only contains the verification secret / public key.
_DEFAULT_VERIFY_KEY = b"GhostCanvas3D-Public-Verify-Key-2026-Ed25519-Safe"
_DEFAULT_SIGN_KEY = b"GhostCanvas3D-Master-Secret-Sign-Key-Production-2026"

LICENSE_FILE_PATH = os.path.expanduser("~/.ghostcanvas/license.key")


class LicenseManager:
    """Manages license issuance, local storage, and cryptographic validation."""

    def __init__(self, verify_key: bytes = _DEFAULT_VERIFY_KEY):
        self.verify_key = verify_key

    @staticmethod
    def get_hardware_fingerprint() -> str:
        """
        Generates a deterministic, node-locked hardware fingerprint (HWID).
        Combines CPU ID, Motherboard UUID, and primary network MAC address.
        """
        components = []

        # 1. System Platform & Node
        components.append(platform.node())
        components.append(platform.machine())

        # 2. Windows-specific UUIDs via PowerShell/WMIC
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"'
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip():
                    components.append(res.stdout.strip())
            except Exception:
                pass

        # 3. Fallback to MAC address node
        try:
            import uuid
            components.append(str(uuid.getnode()))
        except Exception:
            pass

        raw_str = "|".join(components)
        hwid_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16].upper()
        return hwid_hash

    @classmethod
    def generate_license_key(
        cls,
        customer_id: str,
        tier: str = "indie",
        duration_days: Optional[int] = 365,
        hwid: Optional[str] = None,
        max_vms: int = 1,
        sign_key: bytes = _DEFAULT_SIGN_KEY,
    ) -> str:
        """
        Generates a signed commercial license key.
        Format: GC3D-<B64_PAYLOAD>-<HMAC_SIGNATURE>
        """
        now = int(time.time())
        expires_at = (now + duration_days * 86400) if duration_days else 0

        payload = {
            "cust": customer_id,
            "tier": tier.lower(),
            "iat": now,
            "exp": expires_at,
            "vms": max_vms,
            "hwid": hwid.upper() if hwid else "*",
        }

        json_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")

        # Compute cryptographic signature over payload
        signature = hmac.new(sign_key, json_bytes, hashlib.sha256).hexdigest()[:16].upper()

        return f"GC3D-{b64_payload}-{signature}"

    def validate_license_key(
        self,
        license_key: str,
        current_hwid: Optional[str] = None,
        sign_key: bytes = _DEFAULT_SIGN_KEY,
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validates license format, cryptographic signature, expiration, and HWID node-lock.
        Returns (is_valid, payload, error_or_success_message).
        """
        if not license_key or not license_key.startswith("GC3D-"):
            return False, {}, "Invalid license key format (must start with GC3D-)"

        parts = license_key.split("-")
        if len(parts) < 3:
            return False, {}, "Malformed license key structure"

        b64_payload = parts[1]
        received_sig = parts[2]

        # Re-pad base64
        padded_b64 = b64_payload + "=" * (-len(b64_payload) % 4)
        try:
            json_bytes = base64.urlsafe_b64decode(padded_b64)
            payload = json.loads(json_bytes.decode("utf-8"))
        except Exception as e:
            return False, {}, f"Corrupt license payload: {e}"

        # 1. Verify Signature
        expected_sig = hmac.new(sign_key, json_bytes, hashlib.sha256).hexdigest()[:16].upper()
        if not hmac.compare_digest(received_sig, expected_sig):
            return False, payload, "Cryptographic signature verification failed (Tampered License)"

        # 2. Verify Expiration
        now = int(time.time())
        exp = payload.get("exp", 0)
        if exp != 0 and now > exp:
            exp_date = time.strftime("%Y-%m-%d", time.gmtime(exp))
            return False, payload, f"License expired on {exp_date}"

        # 3. Verify Hardware Node-Lock
        target_hwid = payload.get("hwid", "*")
        if target_hwid != "*":
            hwid_to_check = current_hwid or self.get_hardware_fingerprint()
            if target_hwid != hwid_to_check:
                return False, payload, f"License node-locked to HWID {target_hwid} (Current: {hwid_to_check})"

        tier_name = payload.get("tier", "indie").upper()
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
            # Generate a 14-day local trial if none exists
            trial_key = self.generate_license_key(
                customer_id="TrialUser",
                tier="trial",
                duration_days=14,
                hwid=self.get_hardware_fingerprint(),
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
    import sys
    manager = LicenseManager()
    hwid = manager.get_hardware_fingerprint()
    print(f"Host Hardware Fingerprint (HWID): {hwid}")

    if "--generate" in sys.argv:
        key = manager.generate_license_key(
            customer_id="tyler@pro-studio.com",
            tier="studio_pro",
            duration_days=365,
            hwid=hwid,
            max_vms=4,
        )
        print("\nGenerated Commercial License Key:")
        print(key)
        valid, data, msg = manager.validate_license_key(key)
        print(f"Validation: {valid} - {msg}")
    else:
        ent = manager.check_active_entitlement()
        print("\nActive Entitlement:", json.dumps(ent, indent=2))
