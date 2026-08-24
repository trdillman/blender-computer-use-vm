"""
Host Model Context Protocol (MCP) Server for Blender Computer-Use Isolated VM.
Communicates via stdio JSON-RPC with AI Coding Agents (OMP, Claude Code, Codex)
and routes tool calls to the Guest Daemon & Hyper-V Management layer.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict

try:
    from hv_transport import HyperVSocketClient
except ImportError:
    from .hv_transport import HyperVSocketClient  # type: ignore

try:
    from licensing import LicenseManager
except ImportError:
    from .licensing import LicenseManager  # type: ignore

# Server metadata
SERVER_NAME = "blender-cu-vm-mcp"
SERVER_VERSION = "1.0.0"

# Hyper-V & VM Configuration
DEFAULT_VM_NAME = os.environ.get("BLENDER_VM_NAME", "Blender-CU-VM")
GUEST_HTTP_URL = os.environ.get("BLENDER_GUEST_URL", "http://192.168.122.100:8000")

client = HyperVSocketClient(fallback_http_url=GUEST_HTTP_URL)
license_mgr = LicenseManager()


# --- MCP Tool Registry ---
TOOLS = [
    {
        "name": "vm_mouse_click",
        "description": "Click the mouse inside the isolated Blender VM without disturbing host desktop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate on 1920x1080 virtual desktop"},
                "y": {"type": "integer", "description": "Y coordinate on 1920x1080 virtual desktop"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "default": 1, "description": "1 for single, 2 for double click"},
                "modifiers": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['ctrl', 'shift']"},
            },
        },
    },
    {
        "name": "vm_mouse_move",
        "description": "Smoothly move cursor to coordinates in virtual desktop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X coordinate"},
                "y": {"type": "integer", "description": "Target Y coordinate"},
                "duration_ms": {"type": "integer", "default": 100},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "vm_mouse_drag",
        "description": "Drag mouse from start to end coordinates (used for Blender viewport orbit/pan/zoom and node wires).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "duration_ms": {"type": "integer", "default": 200},
                "modifiers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["start_x", "start_y", "end_x", "end_y"],
        },
    },
    {
        "name": "vm_mouse_scroll",
        "description": "Scroll vertical or horizontal mouse wheel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "delta_y": {"type": "integer", "default": 120, "description": "Positive = scroll up, Negative = down"},
                "delta_x": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "vm_keyboard_type",
        "description": "Type text into active input field.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "cpm": {"type": "integer", "default": 400, "description": "Characters per minute"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "vm_keyboard_press",
        "description": "Press key or hotkey combo (e.g. ['ctrl', 's'], ['shift', 'a'], ['f12'], ['numpad_1']).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to press simultaneously"},
                "hold_ms": {"type": "integer", "default": 50},
            },
            "required": ["keys"],
        },
    },
    {
        "name": "vm_screenshot",
        "description": "Capture high-resolution screenshot from the isolated VM with optional grid overlay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "Optional ROI crop 'x,y,w,h'"},
                "format": {"type": "string", "enum": ["png", "jpeg", "webp"], "default": "png"},
                "annotate_grid": {"type": "boolean", "default": False, "description": "Overlay coordinate grid for spatial reasoning"},
            },
        },
    },
    {
        "name": "vm_video_record",
        "description": "Control hardware video recording of test user story session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "stop", "status"]},
                "output_path": {"type": "string", "default": "C:\\Temp\\session_record.mp4"},
                "fps": {"type": "integer", "default": 30},
            },
            "required": ["action"],
        },
    },
    {
        "name": "vm_list_windows",
        "description": "Enumerate all open desktop windows with coordinates, titles, and responsiveness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter_visible": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "vm_find_element",
        "description": "Find UI control coordinates and bounding box by title or class name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Button label or UI element text to find"},
                "hwnd": {"type": "integer", "description": "Optional parent window handle"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "vm_focus_window",
        "description": "Bring window to foreground by HWND.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hwnd": {"type": "integer"},
            },
            "required": ["hwnd"],
        },
    },
    {
        "name": "vm_blender_eval",
        "description": "Evaluate Python expression directly inside Blender embedded runtime via telemetry bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "e.g. 'bpy.context.active_object.name'"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "vm_session_reset",
        "description": "Instantly roll back the VM to clean golden snapshot in under 2 seconds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot_name": {"type": "string", "default": "golden_base"},
            },
        },
    },
    {
        "name": "vm_health_check",
        "description": "Check status of the isolated VM, virtual display resolution, and daemon connectivity.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vm_license_status",
        "description": "Check the commercial license status, tier, and hardware entitlements for GhostCanvas 3D.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vm_activate_license",
        "description": "Activate a commercial GhostCanvas 3D license key (GC3D-XXXX-YYYY...).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "license_key": {"type": "string", "description": "The commercial license key string"}
            },
            "required": ["license_key"]
        },
    },
]


def handle_tool_call(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Routes tool executions to guest daemon or host VM management."""
    if tool_name == "vm_license_status":
        return license_mgr.check_active_entitlement()

    elif tool_name == "vm_activate_license":
        key = args.get("license_key", "").strip()
        is_valid, payload, msg = license_mgr.validate_license_key(key)
        if is_valid:
            license_mgr.save_license(key)
            return {"status": "activated", "tier": payload.get("tier"), "message": msg}
        return {"status": "activation_failed", "error": msg}

    # Enforce active license gate
    entitlement = license_mgr.check_active_entitlement()
    if not entitlement.get("licensed"):
        return {
            "status": "license_required",
            "message": "A valid GhostCanvas 3D license or active trial is required to execute VM computer-use actions."
        }

    if tool_name == "vm_mouse_click":
        return client.request("/input/mouse/click", method="POST", payload=args)

    elif tool_name == "vm_mouse_move":
        return client.request("/input/mouse/move", method="POST", payload=args)

    elif tool_name == "vm_mouse_drag":
        return client.request("/input/mouse/drag", method="POST", payload=args)

    elif tool_name == "vm_mouse_scroll":
        return client.request("/input/mouse/scroll", method="POST", payload=args)

    elif tool_name == "vm_keyboard_type":
        return client.request("/input/keyboard/type", method="POST", payload=args)

    elif tool_name == "vm_keyboard_press":
        return client.request("/input/keyboard/press", method="POST", payload=args)

    elif tool_name == "vm_screenshot":
        params = {
            "region": args.get("region"),
            "format": args.get("format", "png"),
            "annotate_grid": args.get("annotate_grid", False),
        }
        img_bytes, mime = client.fetch_binary("/screen/capture", params=params)
        if img_bytes:
            b64_str = base64.b64encode(img_bytes).decode("ascii")
            return {
                "content": [
                    {"type": "image", "data": b64_str, "mimeType": mime}
                ]
            }
        return {"status": "error", "message": f"Failed to capture screenshot ({mime})"}

    elif tool_name == "vm_video_record":
        return client.request("/video/record", method="POST", payload=args)

    elif tool_name == "vm_list_windows":
        return client.request("/ui/windows", method="GET", params=args)

    elif tool_name == "vm_find_element":
        return client.request("/ui/find", method="GET", params=args)

    elif tool_name == "vm_focus_window":
        return client.request("/ui/focus", method="POST", payload=args)

    elif tool_name == "vm_blender_eval":
        # Dispatched to guest daemon Blender proxy endpoint
        return client.request("/blender/eval", method="POST", payload=args)

    elif tool_name == "vm_session_reset":
        snapshot = str(args.get("snapshot_name", "golden_base")).strip()
        # Strict alphanumeric and safe symbol validation
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", snapshot) or not re.match(r"^[a-zA-Z0-9_\-\.]+$", DEFAULT_VM_NAME):
            return {"status": "error", "message": "Invalid snapshot or VM name (allowed: alphanumeric, _, -, .)"}

        ps_cmd = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"Restore-VMSnapshot -VMName '{DEFAULT_VM_NAME}' -Name '{snapshot}' -Confirm:$false; Start-VM -Name '{DEFAULT_VM_NAME}' -ErrorAction SilentlyContinue"
        ]
        try:
            res = subprocess.run(ps_cmd, shell=False, capture_output=True, text=True, timeout=15)
            return {"status": "success", "snapshot": snapshot, "output": res.stdout.strip()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "vm_health_check":
        return client.request("/health", method="GET")

    return {"status": "unknown_tool", "tool": tool_name}


def run_stdio_server():
    """Runs the standard MCP stdio JSON-RPC loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except Exception:
            continue

        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            call_result = handle_tool_call(tool_name, tool_args)

            # Check if result is already formatted content (e.g. image)
            if isinstance(call_result, dict) and "content" in call_result:
                content_payload = call_result["content"]
            else:
                content_payload = [{"type": "text", "text": json.dumps(call_result, indent=2)}]

            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": content_payload},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list-tools":
        print(json.dumps(TOOLS, indent=2))
    else:
        run_stdio_server()
