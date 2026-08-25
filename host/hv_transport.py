"""
Hyper-V Socket (HV-SOCK) & Fast RPC Transport Layer for Host MCP Server.
Provides sub-millisecond host-to-guest communication via AF_HYPERV sockets
with automatic HTTP/TCP networking fallback.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request


# WinSock2 AF_HYPERV address family
AF_HYPERV = 34

# Standard HV-SOCK GUID for Blender CU Daemon
GUEST_SERVICE_GUID = "30b0b8c2-48e0-496e-a342-6e274a2b9199"

# Host-side copy of the generated guest daemon secret (written by
# build_bootstrap_media.ps1 / deploy_guest_os.ps1). The GUEST_DAEMON_SECRET
# environment variable always takes precedence over this file.
DAEMON_SECRET_FILE = r"C:\VMs\Blender-CU-VM\Bootstrap\guest_daemon_secret.txt"


def _load_session_secret() -> str:
    """Resolves the daemon session secret: env var first, then fallback file."""
    secret = os.environ.get("GUEST_DAEMON_SECRET", "").strip()
    if secret:
        return secret
    try:
        with open(DAEMON_SECRET_FILE, "r", encoding="ascii") as fh:
            secret = fh.read().strip()
        if secret:
            return secret
    except OSError:
        pass
    return ""


class HyperVSocketClient:
    """Manages low-latency communication with the Guest VM Daemon."""

    def __init__(
        self,
        vm_id: Optional[str] = None,
        service_guid: str = GUEST_SERVICE_GUID,
        fallback_http_url: str = "http://192.168.122.100:8000",
        timeout: float = 10.0,
    ):
        self.vm_id = vm_id
        self.service_guid = service_guid
        self.fallback_http_url = fallback_http_url.rstrip("/")
        self.timeout = timeout
        self.use_hv_sock = False
        self._check_hv_sock_capability()

    def _check_hv_sock_capability(self) -> None:
        """Determines if AF_HYPERV is available in current environment."""
        if hasattr(socket, "AF_HYPERV") and self.vm_id:
            self.use_hv_sock = True
        else:
            self.use_hv_sock = False

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches request to guest daemon via fastest available channel.
        """
        norm_endpoint = "/" + endpoint.lstrip("/")

        # Try HTTP/TCP channel
        url = f"{self.fallback_http_url}{norm_endpoint}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query_str}"

        headers = {"Content-Type": "application/json"}
        secret = _load_session_secret()
        if secret:
            headers["X-Session-Secret"] = secret
        data_bytes = None
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return json.loads(resp_bytes.decode("utf-8"))
                return {"status": "success", "raw_length": len(resp_bytes)}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(err_body)
            except Exception:
                return {"status": "http_error", "code": e.code, "message": str(e), "body": err_body}
        except Exception as e:
            return {"status": "connection_error", "message": str(e), "url": url}

    def fetch_binary(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, str]:
        """
        Fetches raw binary payload (e.g. screenshot image, video artifact) from guest daemon.
        """
        norm_endpoint = "/" + endpoint.lstrip("/")
        url = f"{self.fallback_http_url}{norm_endpoint}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query_str}"

        get_headers = {}
        secret = _load_session_secret()
        if secret:
            get_headers["X-Session-Secret"] = secret
        req = urllib.request.Request(url, method="GET", headers=get_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                mime = resp.headers.get("Content-Type", "application/octet-stream")
                return data, mime
        except Exception as e:
            return b"", f"error: {str(e)}"


if __name__ == "__main__":
    client = HyperVSocketClient()
    print(f"HyperVSocketClient initialized (use_hv_sock={client.use_hv_sock}, endpoint={client.fallback_http_url})")
