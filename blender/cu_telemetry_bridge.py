"""
Blender Computer-Use In-Process Telemetry Bridge Addon.
Runs inside Blender's embedded Python runtime to expose deep scene state,
operator execution metrics, and console errors to the Guest Daemon & Host MCP Server.
Marshals all `bpy` access to Blender's Main Thread via bpy.app.timers.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import traceback
from typing import Any, Dict, Optional

bl_info = {
    "name": "Computer-Use Telemetry Bridge",
    "author": "GhostCanvas",
    "version": (1, 1, 1),
    "blender": (3, 6, 0),
    "location": "Background Service",
    "description": "Exposes in-process scene telemetry and eval RPC to Computer-Use agents.",
    "category": "Development",
}

try:
    import bpy  # type: ignore
except ImportError:
    bpy = None  # type: ignore

_BRIDGE_SERVER: Optional[TelemetryBridgeServer] = None


class TelemetryBridgeServer:
    """Thread-safe TCP socket listener inside Blender with main-thread timer marshaling."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9199):
        self.host = host
        self.port = port
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.request_queue: queue.Queue = queue.Queue()
        self.timer_registered = False

    def start(self):
        self.stop_event.clear()
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.server_sock.settimeout(0.5)

        # Register Main-Thread Timer in Blender
        if bpy and hasattr(bpy, "app") and hasattr(bpy.app, "timers") and not self.timer_registered:
            bpy.app.timers.register(self._process_main_thread_queue, persistent=True)
            self.timer_registered = True

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"[GhostCanvas-Bridge] Telemetry bridge listening on {self.host}:{self.port}")

    def stop(self):
        self.stop_event.set()
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            self.thread = None

        if bpy and hasattr(bpy, "app") and hasattr(bpy.app, "timers") and self.timer_registered:
            try:
                if bpy.app.timers.is_registered(self._process_main_thread_queue):
                    bpy.app.timers.unregister(self._process_main_thread_queue)
            except Exception:
                pass
            self.timer_registered = False

        print("[GhostCanvas-Bridge] Telemetry bridge stopped.")

    def _listen_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self.server_sock:
                    break
                client_sock, _ = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket):
        try:
            client_sock.settimeout(5.0)
            data = client_sock.recv(65536)
            if not data:
                return

            req = json.loads(data.decode("utf-8"))
            action = req.get("action", "ping")

            if action == "ping":
                resp = {"status": "ok", "message": "pong"}
            else:
                # Dispatch to Blender Main Thread
                resp_event = threading.Event()
                result_holder: Dict[str, Any] = {}
                self.request_queue.put((action, req, resp_event, result_holder))

                # Wait for main-thread timer execution
                if resp_event.wait(timeout=4.0):
                    resp = result_holder.get("response", {"status": "error", "message": "No response"})
                else:
                    resp = {"status": "timeout", "message": "Main thread execution timed out"}

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

    def _process_main_thread_queue(self) -> float:
        """Executed on Blender Main Thread by bpy.app.timers at 100 Hz."""
        while not self.request_queue.empty():
            try:
                action, req, resp_event, result_holder = self.request_queue.get_nowait()
                result_holder["response"] = self._dispatch_main_thread(action, req)
                resp_event.set()
            except queue.Empty:
                break
            except Exception:
                pass
        return 0.01  # Poll again in 10ms

    def _dispatch_main_thread(self, action: str, req: Dict[str, Any]) -> Dict[str, Any]:
        """Runs safely on Blender Main Thread."""
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
        try:
            scope = {"bpy": bpy, "context": getattr(bpy, "context", None), "data": getattr(bpy, "data", None)}
            val = eval(expr, scope)
            try:
                json.dumps(val)
                serialized = val
            except (TypeError, ValueError):
                serialized = repr(val)
            return {"status": "success", "result": serialized}
        except Exception as e:
            return {"status": "eval_error", "error": str(e), "traceback": traceback.format_exc()}

    def _safe_exec(self, code: str) -> Dict[str, Any]:
        try:
            scope = {"bpy": bpy, "context": getattr(bpy, "context", None), "data": getattr(bpy, "data", None)}
            exec(code, scope)
            return {"status": "success"}
        except Exception as e:
            return {"status": "exec_error", "error": str(e), "traceback": traceback.format_exc()}

    def _get_scene_info(self) -> Dict[str, Any]:
        try:
            ctx = getattr(bpy, "context", None) if bpy else None
            scene = getattr(ctx, "scene", None) if ctx else None
            if not scene:
                return {"status": "no_active_scene"}

            objects = [obj.name for obj in getattr(scene, "objects", [])]
            active_name = ctx.active_object.name if ctx and hasattr(ctx, "active_object") and ctx.active_object else None

            # Blender 5.1/5.2 window animation playback detection
            is_playing = False
            wm = getattr(ctx, "window_manager", None) if ctx else None
            if wm and hasattr(wm, "windows"):
                for win in wm.windows:
                    if hasattr(win, "find_playing_scene") and win.find_playing_scene():
                        is_playing = True
                        break
            if not is_playing and ctx and hasattr(ctx, "screen"):
                is_playing = bool(getattr(ctx.screen, "is_animation_playing", False))

            return {
                "status": "success",
                "scene_name": getattr(scene, "name", "Scene"),
                "current_frame": getattr(scene, "frame_current", 1),
                "frame_start": getattr(scene, "frame_start", 1),
                "frame_end": getattr(scene, "frame_end", 250),
                "fps": getattr(getattr(scene, "render", None), "fps", 24),
                "is_animation_playing": is_playing,
                "active_object": active_name,
                "object_count": len(objects),
                "objects": objects[:50],
                "active_mode": getattr(ctx, "mode", "UNKNOWN") if ctx else "UNKNOWN",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_active_object_info(self) -> Dict[str, Any]:
        try:
            obj = getattr(bpy.context, "active_object", None) if bpy else None
            if not obj:
                return {"status": "no_active_object"}

            modifiers = [
                {"name": m.name, "type": m.type, "show_viewport": m.show_viewport}
                for m in getattr(obj, "modifiers", [])
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
