"""
Unified Guest Computer-Use Daemon Server for Isolated VM.
Exposes REST/JSON & binary endpoints for:
- Framebuffer capture (DXGI / PNG / JPEG / Grid annotations)
- Hardware input injection (clicks, drags, scroll, text, hotkeys)
- UI Automation tree inspection & window focus
- NVENC video recording
- System health and GPU status metrics
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

try:
    from input_controller import InputController
    from screen_capture import ScreenCaptureEngine
    from ui_automation import UIAutomationInspector
    from video_recorder import VideoRecorder
except ImportError:
    from .input_controller import InputController  # type: ignore
    from .screen_capture import ScreenCaptureEngine  # type: ignore
    from .ui_automation import UIAutomationInspector  # type: ignore
    from .video_recorder import VideoRecorder  # type: ignore

app = FastAPI(
    title="Blender Computer-Use Guest Daemon",
    version="1.0.0",
    description="Low-latency API daemon for isolated desktop and Blender UI automation.",
)

# Instantiate core engines
screen_engine = ScreenCaptureEngine()
input_ctrl = InputController()
ui_inspector = UIAutomationInspector()
video_rec = VideoRecorder(screen_engine=screen_engine)


# --- Pydantic Request Models ---
class MouseClickRequest(BaseModel):
    x: Optional[int] = Field(None, description="Target X coordinate")
    y: Optional[int] = Field(None, description="Target Y coordinate")
    button: str = Field("left", description="Mouse button: left, right, middle")
    clicks: int = Field(1, ge=1, le=5, description="Number of clicks")
    modifiers: Optional[List[str]] = Field(None, description="Modifier keys to hold: ['ctrl', 'shift', 'alt']")


class MouseDragRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    button: str = "left"
    duration_ms: int = Field(200, ge=10, le=5000)
    steps: int = Field(15, ge=2, le=100)
    modifiers: Optional[List[str]] = None


class MouseScrollRequest(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    delta_y: int = 120
    delta_x: int = 0


class TypeTextRequest(BaseModel):
    text: str
    cpm: int = Field(400, ge=50, le=1200)


class KeyPressRequest(BaseModel):
    keys: List[str] = Field(..., description="Key or key combination: ['ctrl', 's'], ['f12'], ['shift', 'a']")
    hold_ms: int = Field(50, ge=10, le=2000)


class VideoRecordRequest(BaseModel):
    action: str = Field(..., description="'start', 'stop', or 'status'")
    output_path: str = "C:\\Temp\\session_record.mp4"
    fps: int = 30
    use_nvenc: bool = True


# --- Endpoints ---
@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Returns guest daemon status, display metrics, and engine health."""
    cursor_x, cursor_y = input_ctrl.get_cursor_pos()
    return {
        "status": "ready",
        "display": {
            "width": screen_engine.default_width,
            "height": screen_engine.default_height,
        },
        "cursor": {"x": cursor_x, "y": cursor_y},
        "video_recording": video_rec.is_recording,
    }


@app.get("/screen/capture")
def capture_screen(
    region: Optional[str] = Query(None, description="ROI crop 'x,y,w,h'"),
    format: str = Query("png", description="png, jpeg, webp"),
    quality: int = Query(85, ge=10, le=100),
    annotate_grid: bool = Query(False, description="Overlay labeled coordinate grid"),
) -> Response:
    """Captures and returns compressed frame bytes."""
    crop_rect = None
    if region:
        try:
            parts = [int(p.strip()) for p in region.split(",")]
            if len(parts) == 4:
                crop_rect = parts
        except ValueError:
            pass

    img_bytes, mime = screen_engine.capture_bytes(
        region=crop_rect,
        format=format,
        quality=quality,
        annotate_grid=annotate_grid,
    )
    return Response(content=img_bytes, media_type=mime)


@app.post("/input/mouse/click")
def api_mouse_click(req: MouseClickRequest) -> Dict[str, Any]:
    input_ctrl.mouse_click(
        x=req.x,
        y=req.y,
        button=req.button,
        clicks=req.clicks,
        modifiers=req.modifiers,
    )
    return {"status": "success", "action": "mouse_click", "params": req.model_dump()}


@app.post("/input/mouse/drag")
def api_mouse_drag(req: MouseDragRequest) -> Dict[str, Any]:
    input_ctrl.mouse_drag(
        start_x=req.start_x,
        start_y=req.start_y,
        end_x=req.end_x,
        end_y=req.end_y,
        button=req.button,
        duration_ms=req.duration_ms,
        steps=req.steps,
        modifiers=req.modifiers,
    )
    return {"status": "success", "action": "mouse_drag", "params": req.model_dump()}


@app.post("/input/mouse/scroll")
def api_mouse_scroll(req: MouseScrollRequest) -> Dict[str, Any]:
    input_ctrl.mouse_scroll(x=req.x, y=req.y, delta_y=req.delta_y, delta_x=req.delta_x)
    return {"status": "success", "action": "mouse_scroll", "params": req.model_dump()}


@app.post("/input/keyboard/type")
def api_type_text(req: TypeTextRequest) -> Dict[str, Any]:
    input_ctrl.type_text(text=req.text, cpm=req.cpm)
    return {"status": "success", "action": "type_text", "length": len(req.text)}


@app.post("/input/keyboard/press")
def api_key_press(req: KeyPressRequest) -> Dict[str, Any]:
    input_ctrl.key_press(keys=req.keys, hold_ms=req.hold_ms)
    return {"status": "success", "action": "key_press", "keys": req.keys}


@app.get("/ui/windows")
def api_list_windows(filter_visible: bool = True) -> Dict[str, Any]:
    windows = ui_inspector.list_windows(filter_visible=filter_visible)
    return {"status": "success", "count": len(windows), "windows": windows}


@app.get("/ui/find")
def api_find_ui_element(query: str, hwnd: Optional[int] = None) -> JSONResponse:
    elem = ui_inspector.find_element(query=query, parent_hwnd=hwnd)
    if elem:
        return JSONResponse({"status": "found", "element": elem})
    return JSONResponse({"status": "not_found", "query": query}, status_code=404)


@app.post("/ui/focus")
def api_focus_window(hwnd: int) -> Dict[str, Any]:
    success = ui_inspector.focus_window(hwnd)
    return {"status": "success" if success else "failed", "hwnd": hwnd}


@app.post("/video/record")
def api_video_record(req: VideoRecordRequest) -> Dict[str, Any]:
    action = req.action.lower()
    if action == "start":
        return video_rec.start_recording(
            output_path=req.output_path,
            fps=req.fps,
            use_nvenc=req.use_nvenc,
        )
    elif action == "stop":
        return video_rec.stop_recording()
    else:
        return video_rec.get_status()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("GUEST_DAEMON_PORT", 8000))
    print(f"Starting Blender Computer-Use Guest Daemon on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
