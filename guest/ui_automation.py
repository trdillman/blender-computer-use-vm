"""
Windows UI Automation & Window Hierarchy Inspector for Computer-Use VM.
Provides structured UI tree inspection, window enumeration, responsiveness checks,
and coordinate discovery with explicit 64-bit ctypes Win32 ABI signatures.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
from typing import Any, Dict, List, Optional, Tuple


# --- Win32 Structures & Function Types ---
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class UIAutomationInspector:
    """Inspects Windows desktop windows, controls, and accessibility elements."""

    def __init__(self):
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

        # 64-bit explicit Win32 API signatures
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self._user32.GetWindowRect.restype = wintypes.BOOL

        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL

        self._user32.IsHungAppWindow.argtypes = [wintypes.HWND]
        self._user32.IsHungAppWindow.restype = wintypes.BOOL

        self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self._user32.GetWindowTextLengthW.restype = ctypes.c_int

        self._user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetWindowTextW.restype = ctypes.c_int

        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        self._user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        self._user32.EnumWindows.restype = wintypes.BOOL

        self._user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
        self._user32.EnumChildWindows.restype = wintypes.BOOL

        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.SetForegroundWindow.restype = wintypes.BOOL

        self._user32.IsIconic.argtypes = [wintypes.HWND]
        self._user32.IsIconic.restype = wintypes.BOOL

        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL

        self._user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetClassNameW.restype = ctypes.c_int

    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        rect = RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def is_window_visible(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindowVisible(hwnd))

    def is_window_responsive(self, hwnd: int) -> bool:
        return not bool(self._user32.IsHungAppWindow(hwnd))

    def get_window_title(self, hwnd: int) -> str:
        length = self._user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buff = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value

    def get_window_pid(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def list_windows(self, filter_visible: bool = True) -> List[Dict[str, Any]]:
        windows: List[Dict[str, Any]] = []

        def enum_callback(hwnd: int, _lparam: int) -> bool:
            if filter_visible and not self.is_window_visible(hwnd):
                return True

            title = self.get_window_title(hwnd)
            if filter_visible and not title.strip():
                return True

            x, y, w, h = self.get_window_rect(hwnd)
            if w <= 0 or h <= 0:
                return True

            pid = self.get_window_pid(hwnd)
            responsive = self.is_window_responsive(hwnd)

            windows.append({
                "hwnd": hwnd,
                "title": title,
                "pid": pid,
                "rect": [x, y, w, h],
                "center": [x + w // 2, y + h // 2],
                "responsive": responsive,
            })
            return True

        self._user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return windows

    def find_window(self, pattern: str) -> Optional[Dict[str, Any]]:
        windows = self.list_windows(filter_visible=True)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for win in windows:
            if regex.search(win["title"]):
                return win
        return None

    def focus_window(self, hwnd: int) -> bool:
        if self._user32.IsIconic(hwnd):
            self._user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(self._user32.SetForegroundWindow(hwnd))

    def inspect_child_elements(self, parent_hwnd: int) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []

        def enum_child_callback(hwnd: int, _lparam: int) -> bool:
            if not self.is_window_visible(hwnd):
                return True

            title = self.get_window_title(hwnd)
            x, y, w, h = self.get_window_rect(hwnd)
            if w <= 0 or h <= 0:
                return True

            class_buff = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(hwnd, class_buff, 256)
            class_name = class_buff.value

            elements.append({
                "hwnd": hwnd,
                "title": title,
                "class_name": class_name,
                "rect": [x, y, w, h],
                "center": [x + w // 2, y + h // 2],
            })
            return True

        self._user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(enum_child_callback), 0)
        return elements

    def find_element(self, query: str, parent_hwnd: Optional[int] = None) -> Optional[Dict[str, Any]]:
        try:
            regex = re.compile(query, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(query), re.IGNORECASE)

        if parent_hwnd:
            elements = self.inspect_child_elements(parent_hwnd)
        else:
            elements = self.list_windows(filter_visible=True)

        for elem in elements:
            if regex.search(elem.get("title", "")) or regex.search(elem.get("class_name", "")):
                return elem
        return None


if __name__ == "__main__":
    inspector = UIAutomationInspector()
    wins = inspector.list_windows()
    print(f"Discovered {len(wins)} visible top-level windows.")
