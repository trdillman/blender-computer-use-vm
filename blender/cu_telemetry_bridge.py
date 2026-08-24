"""
Blender Computer-Use In-Process Telemetry Bridge Addon.
Runs inside Blender's embedded Python runtime to expose deep scene state,
operator execution metrics, and console errors to the Guest Daemon & Host MCP Server.
"""

import json
import socket
import threading
import traceback
from typing import Any, Dict

bl_info = {
    "name": "Computer-Use Telemetry Bridge",
    "author": "Autonomous Agent",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Background Service",
    "description": "Exposes in-process scene telemetry and eval RPC to Computer-Use agents.",
    "category": "Development",
}

# Global server reference
_BRIDGE_SERVER = None
_RUNNING = False


class TelemetryBridgeServer:
    """Non-blocking TCP socket listener inside Blender process."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9199):
        self.host = host
        self.port = port
        self.server_sock = None
        self.thread = None
        self.last_errors = []

    def start(self):
        global _RUNNING
        _RUNNING = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"[CU-Bridge] Telemetry bridge listening on {self.host}:{self.port}")

    def stop(self):
        global _RUNNING
        _RUNNING = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        print("[CU-Bridge] Telemetry bridge stopped.")

    def _listen_loop(self):
        global _RUNNING
        while _RUNNING:
            try:
                if not self.server_sock:
                    break
                client_sock, _ = self.server_sock.accept()  # type: ignore
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket):
        try:
            client_sock.settimeout(5.0)
            data = client_sock.recv(65536).decode("utf-8")
            if not data:
                return

            req = json.loads(data)
            action = req.get("action", "ping")
            resp = self._dispatch(action, req)
            client_sock.sendall(json.dumps(resp).encode("utf-8"))
        except Exception as e:
            err_resp = {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
            try:
                client_sock.sendall(json.dumps(err_resp).encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _dispatch(self, action: str, req: Dict[str, Any]) -> Dict[str, Any]:
        """Routes requests to specific internal state inspectors."""
        if action == "ping":
            return {"status": "ok", "message": "pong"}

        if action == "eval":
            expr = req.get("expression", "")
            return self._safe_eval(expr)

        if action == "exec":
            code = req.get("code", "")
            return self._safe_exec(code)

        if action == "scene_info":
            return self._get_scene_info()

        if action == "active_object":
            return self._get_active_object_info()

        return {"status": "unknown_action", "action": action}

    def _safe_eval(self, expr: str) -> Dict[str, Any]:
        """Evaluates a Python expression in Blender context."""
        try:
            import bpy  # type: ignore
            scope = {"bpy": bpy, "context": bpy.context, "data": bpy.data}
            val = eval(expr, scope)
            # Try to serialize or stringify
            try:
                json.dumps(val)
                serialized = val
            except (TypeError, ValueError):
                serialized = repr(val)

            return {"status": "success", "result": serialized}
        except Exception as e:
            return {"status": "eval_error", "error": str(e), "traceback": traceback.format_exc()}

    def _safe_exec(self, code: str) -> Dict[str, Any]:
        """Executes a block of Python code in Blender context."""
        try:
            import bpy  # type: ignore
            scope = {"bpy": bpy, "context": bpy.context, "data": bpy.data}
            exec(code, scope)
            return {"status": "success"}
        except Exception as e:
            return {"status": "exec_error", "error": str(e), "traceback": traceback.format_exc()}

    def _get_scene_info(self) -> Dict[str, Any]:
        """Collects high-level scene metrics."""
        try:
            import bpy  # type: ignore
            scene = bpy.context.scene
            if not scene:
                return {"status": "no_active_scene"}

            objects = [obj.name for obj in getattr(scene, "objects", [])]
            active_name = bpy.context.active_object.name if bpy.context.active_object else None

            return {
                "status": "success",
                "scene_name": getattr(scene, "name", "Scene"),
                "current_frame": getattr(scene, "frame_current", 1),
                "frame_start": getattr(scene, "frame_start", 1),
                "frame_end": getattr(scene, "frame_end", 250),
                "fps": getattr(getattr(scene, "render", None), "fps", 24),
                "is_animation_playing": bool(getattr(bpy.context.screen, "is_animation_playing", False)),
                "active_object": active_name,
                "object_count": len(objects),
                "objects": objects[:50],  # capped for bandwidth
                "active_mode": getattr(bpy.context, "mode", "UNKNOWN"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_active_object_info(self) -> Dict[str, Any]:
        """Collects deep inspection metrics for the currently selected object."""
        try:
            import bpy  # type: ignore
            obj = bpy.context.active_object
            if not obj:
                return {"status": "no_active_object"}

            modifiers = [
                {"name": m.name, "type": m.type, "show_viewport": m.show_viewport}
                for m in obj.modifiers
            ]

            return {
                "status": "success",
                "name": obj.name,
                "type": obj.type,
                "location": [round(v, 4) for v in obj.location],
                "rotation_euler": [round(v, 4) for v in obj.rotation_euler],
                "scale": [round(v, 4) for v in obj.scale],
                "modifiers": modifiers,
                "modifier_count": len(modifiers),
                "vertex_count": len(getattr(obj.data, "vertices", [])) if getattr(obj, "data", None) and hasattr(obj.data, "vertices") else None,
                "polygon_count": len(getattr(obj.data, "polygons", [])) if getattr(obj, "data", None) and hasattr(obj.data, "polygons") else None,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


def register():
    global _BRIDGE_SERVER
    if _BRIDGE_SERVER is None:
        _BRIDGE_SERVER = TelemetryBridgeServer()
        _BRIDGE_SERVER.start()


def unregister():
    global _BRIDGE_SERVER
    if _BRIDGE_SERVER:
        _BRIDGE_SERVER.stop()
        _BRIDGE_SERVER = None


if __name__ == "__main__":
    register()
