"""
Hardware Video Recorder & Ring Buffer for Computer-Use VM.
Records virtual desktop sessions to high-efficiency MP4 video using NVIDIA NVENC
hardware acceleration (h264_nvenc) with thread generation tracking and clean teardowns.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional
from PIL import Image

try:
    from screen_capture import ScreenCaptureEngine
except ImportError:
    from .screen_capture import ScreenCaptureEngine  # type: ignore


class VideoRecorder:
    """Records the virtual desktop to an MP4 video artifact."""

    def __init__(self, screen_engine: Optional[ScreenCaptureEngine] = None):
        self.screen_engine = screen_engine or ScreenCaptureEngine()
        self._is_recording = False
        self._generation_id = 0
        self._thread: Optional[threading.Thread] = None
        self._ffmpeg_process: Optional[subprocess.Popen[bytes]] = None
        self._output_path: Optional[str] = None
        self._fps: int = 30
        self._start_time: float = 0.0
        self._frame_count: int = 0
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(
        self,
        output_path: str = "C:\\Temp\\session_record.mp4",
        fps: int = 30,
        use_nvenc: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._is_recording:
                return {
                    "status": "already_recording",
                    "output_path": self._output_path,
                    "elapsed_seconds": round(time.time() - self._start_time, 2),
                }

            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            self._generation_id += 1
            gen_id = self._generation_id
            self._output_path = output_path
            self._fps = fps
            self._frame_count = 0
            self._start_time = time.time()
            self._is_recording = True

            encoder = "h264_nvenc" if use_nvenc else "libx264"
            ffmpeg_bin = shutil.which("ffmpeg")

            if ffmpeg_bin:
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-f", "rawvideo",
                    "-vcodec", "rawvideo",
                    "-s", f"{self.screen_engine.default_width}x{self.screen_engine.default_height}",
                    "-pix_fmt", "rgb24",
                    "-r", str(fps),
                    "-i", "-",
                    "-c:v", encoder,
                    "-pix_fmt", "yuv420p",
                    "-preset", "p4",
                    "-b:v", "5M",
                    output_path,
                ]
                try:
                    self._ffmpeg_process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    self._ffmpeg_process = None

            self._thread = threading.Thread(target=self._capture_loop, args=(gen_id,), daemon=True)
            self._thread.start()

            return {
                "status": "started",
                "output_path": self._output_path,
                "fps": self._fps,
                "encoder": encoder if self._ffmpeg_process else "frame_sequence",
            }

    def _capture_loop(self, gen_id: int) -> None:
        interval = 1.0 / self._fps

        while self._is_recording and self._generation_id == gen_id:
            loop_start = time.time()
            frame = self.screen_engine.capture_frame()

            proc = self._ffmpeg_process
            if proc and proc.stdin and not proc.stdin.closed:
                try:
                    if frame.size != (self.screen_engine.default_width, self.screen_engine.default_height):
                        frame = frame.resize(
                            (self.screen_engine.default_width, self.screen_engine.default_height),
                            Image.Resampling.BILINEAR,
                        )
                    raw_bytes = frame.convert("RGB").tobytes()
                    proc.stdin.write(raw_bytes)
                except Exception:
                    break

            self._frame_count += 1
            elapsed = time.time() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop_recording(self) -> Dict[str, Any]:
        with self._lock:
            if not self._is_recording:
                return {"status": "not_recording"}

            self._is_recording = False
            self._generation_id += 1

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._ffmpeg_process:
            if self._ffmpeg_process.stdin and not self._ffmpeg_process.stdin.closed:
                try:
                    self._ffmpeg_process.stdin.close()
                except Exception:
                    pass
            try:
                self._ffmpeg_process.wait(timeout=3.0)
            except Exception:
                self._ffmpeg_process.kill()
            self._ffmpeg_process = None

        duration = time.time() - self._start_time
        file_size = os.path.getsize(self._output_path) if self._output_path and os.path.exists(self._output_path) else 0

        return {
            "status": "stopped",
            "output_path": self._output_path,
            "duration_seconds": round(duration, 2),
            "frame_count": self._frame_count,
            "average_fps": round(self._frame_count / max(0.1, duration), 1),
            "file_size_bytes": file_size,
        }

    def get_status(self) -> Dict[str, Any]:
        if not self._is_recording:
            return {"is_recording": False}

        duration = time.time() - self._start_time
        return {
            "is_recording": True,
            "output_path": self._output_path,
            "elapsed_seconds": round(duration, 2),
            "frame_count": self._frame_count,
            "current_fps": round(self._frame_count / max(0.1, duration), 1),
        }
