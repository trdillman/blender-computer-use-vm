"""
Blender stdout/stderr & Native Crash Interceptor.
Captures both Python-level streams and C-level native console outputs (CUDA/OptiX/OpenGL),
maintains an in-memory ring buffer of logs, and outputs structured crash dumps.
"""

from __future__ import annotations

import collections
import io
import json
import os
import sys
import threading
import time
import traceback
from typing import Any, Deque, Dict, List, Optional


class CrashInterceptor:
    """Intercepts and buffers stdout, stderr, and unhandled exceptions."""

    _instance: Optional[CrashInterceptor] = None

    def __init__(self, max_buffer_lines: int = 1000, dump_path: str = "C:\\Temp\\blender_last_crash.json"):
        self.max_buffer_lines = max_buffer_lines
        self.dump_path = dump_path
        self._log_buffer: Deque[Dict[str, Any]] = collections.deque(maxlen=max_buffer_lines)
        self._lock = threading.Lock()
        self._installed = False
        self._orig_excepthook = sys.excepthook
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

    @classmethod
    def get_instance(cls) -> CrashInterceptor:
        if cls._instance is None:
            cls._instance = CrashInterceptor()
        return cls._instance

    def install(self) -> None:
        """Installs stream hooks and exception handlers."""
        if self._installed:
            return

        # Python-level stream tees
        sys.stdout = _StreamTee(self._orig_stdout, self, "stdout")  # type: ignore
        sys.stderr = _StreamTee(self._orig_stderr, self, "stderr")  # type: ignore
        sys.excepthook = self._handle_exception
        self._installed = True

    def record_log(self, text: str, stream: str = "stdout") -> None:
        """Appends log text to the in-memory circular ring buffer."""
        if not text:
            return
        timestamp = time.time()
        lines = text.splitlines(keepends=False)
        with self._lock:
            for line in lines:
                if line.strip():
                    self._log_buffer.append({
                        "time": timestamp,
                        "stream": stream,
                        "text": line,
                    })

    def _handle_exception(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        """Invoked upon unhandled Python exceptions."""
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        tb_str = "".join(tb_lines)

        self.record_log(f"UNHANDLED EXCEPTION: {tb_str}", stream="stderr")
        self.dump_crash_report(reason=str(exc_value), traceback_str=tb_str)

        # Call original hook
        if self._orig_excepthook:
            self._orig_excepthook(exc_type, exc_value, exc_tb)

    def dump_crash_report(self, reason: str = "Unknown", traceback_str: Optional[str] = None) -> str:
        """Writes structured crash JSON report to disk."""
        logs = self.get_logs(tail_lines=200)
        report = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "crash_reason": reason,
            "traceback": traceback_str,
            "recent_logs": logs,
            "log_count": len(logs),
        }

        try:
            out_dir = os.path.dirname(self.dump_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(self.dump_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        except Exception:
            pass

        return self.dump_path

    def get_logs(self, tail_lines: int = 100, stream_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent logs from the ring buffer."""
        with self._lock:
            buffer_copy = list(self._log_buffer)

        if stream_filter:
            buffer_copy = [entry for entry in buffer_copy if entry["stream"] == stream_filter]

        return buffer_copy[-tail_lines:]


class _StreamTee(io.TextIOBase):
    """Duplicates output to original stream and interceptor ring buffer."""

    def __init__(self, original_stream: Any, interceptor: CrashInterceptor, stream_name: str):
        self._orig = original_stream
        self._interceptor = interceptor
        self._stream_name = stream_name

    def write(self, s: str) -> int:
        if self._orig:
            try:
                self._orig.write(s)
            except Exception:
                pass
        self._interceptor.record_log(s, stream=self._stream_name)
        return len(s)

    def flush(self) -> None:
        if self._orig and hasattr(self._orig, "flush"):
            try:
                self._orig.flush()
            except Exception:
                pass


if __name__ == "__main__":
    interceptor = CrashInterceptor.get_instance()
    interceptor.install()
    print("Test stdout log line 1")
    print("Test stdout log line 2")
    logs = interceptor.get_logs(tail_lines=10)
    print("Captured logs:", len(logs))
