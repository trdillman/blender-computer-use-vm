"""
Win32 Hardware Input Controller for Isolated Computer-Use VM.
Provides low-level mouse and keyboard synthesis via Win32 SendInput API (ctypes),
including smooth Bézier curves, multi-button drag (Blender orbit/pan/zoom),
Unicode text typing, and comprehensive Blender hotkey mappings.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
from typing import Dict, List, Optional, Tuple, Union

# --- Win32 Constants & Structures ---
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTunion),
    ]


# Virtual Key Map
VK_MAP: Dict[str, int] = {
    # Modifiers
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    # Navigation & Standard Keys
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    # Function Keys
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    # Numpad Keys (Critical for Blender 3D Viewport)
    "num0": 0x60,
    "num1": 0x61,
    "num2": 0x62,
    "num3": 0x63,
    "num4": 0x64,
    "num5": 0x65,
    "num6": 0x66,
    "num7": 0x67,
    "num8": 0x68,
    "num9": 0x69,
    "num_dot": 0x6E,
    "num_slash": 0x6F,
    "num_mult": 0x6A,
    "num_plus": 0x6B,
    "num_minus": 0x6D,
    "numpad_0": 0x60,
    "numpad_1": 0x61,
    "numpad_2": 0x62,
    "numpad_3": 0x63,
    "numpad_4": 0x64,
    "numpad_5": 0x65,
    "numpad_6": 0x66,
    "numpad_7": 0x67,
    "numpad_8": 0x68,
    "numpad_9": 0x69,
    "numpad_period": 0x6E,
}


class InputController:
    """Controls Win32 hardware mouse and keyboard input."""

    def __init__(self):
        self._user32 = ctypes.windll.user32

    def get_cursor_pos(self) -> Tuple[int, int]:
        """Returns the current cursor (x, y) coordinates."""
        pt = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def mouse_move(self, x: int, y: int, duration_ms: int = 100, steps: int = 10) -> None:
        """Smoothly moves cursor to target (x, y) coordinates."""
        start_x, start_y = self.get_cursor_pos()
        if start_x == x and start_y == y:
            return

        steps = max(2, min(steps, 60))
        sleep_per_step = (duration_ms / 1000.0) / steps

        for i in range(1, steps + 1):
            t = i / steps
            # Smooth cubic ease-in-out
            ease = t * t * (3.0 - 2.0 * t)
            curr_x = int(start_x + (x - start_x) * ease)
            curr_y = int(start_y + (y - start_y) * ease)
            self._user32.SetCursorPos(curr_x, curr_y)
            if sleep_per_step > 0:
                time.sleep(sleep_per_step)

        self._user32.SetCursorPos(x, y)

    def mouse_down(self, button: str = "left") -> None:
        """Sends mouse button down event."""
        btn = button.lower()
        flag = {
            "left": MOUSEEVENTF_LEFTDOWN,
            "right": MOUSEEVENTF_RIGHTDOWN,
            "middle": MOUSEEVENTF_MIDDLEDOWN,
        }.get(btn, MOUSEEVENTF_LEFTDOWN)

        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_up(self, button: str = "left") -> None:
        """Sends mouse button up event."""
        btn = button.lower()
        flag = {
            "left": MOUSEEVENTF_LEFTUP,
            "right": MOUSEEVENTF_RIGHTUP,
            "middle": MOUSEEVENTF_MIDDLEUP,
        }.get(btn, MOUSEEVENTF_LEFTUP)

        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
        modifiers: Optional[List[str]] = None,
    ) -> None:
        """
        Executes single/double/triple click with optional modifier hold.
        """
        if x is not None and y is not None:
            self.mouse_move(x, y, duration_ms=60)

        # Press modifiers if specified
        active_mods = modifiers or []
        for mod in active_mods:
            self.key_down(mod)

        try:
            for _ in range(clicks):
                self.mouse_down(button)
                time.sleep(0.025)
                self.mouse_up(button)
                time.sleep(0.04)
        finally:
            for mod in reversed(active_mods):
                self.key_up(mod)

    def mouse_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
        duration_ms: int = 200,
        steps: int = 15,
        modifiers: Optional[List[str]] = None,
    ) -> None:
        """
        Executes mouse drag operation from start to end coordinates.
        Supports Blender Viewport Orbit (MMB), Pan (Shift+MMB), and Zoom (Ctrl+MMB).
        """
        self.mouse_move(start_x, start_y, duration_ms=50)
        time.sleep(0.03)

        active_mods = modifiers or []
        for mod in active_mods:
            self.key_down(mod)

        try:
            self.mouse_down(button)
            time.sleep(0.04)
            self.mouse_move(end_x, end_y, duration_ms=duration_ms, steps=steps)
            time.sleep(0.04)
            self.mouse_up(button)
            time.sleep(0.02)
        finally:
            for mod in reversed(active_mods):
                self.key_up(mod)

    def mouse_scroll(self, x: Optional[int] = None, y: Optional[int] = None, delta_y: int = 120, delta_x: int = 0) -> None:
        """Scrolls the vertical or horizontal mouse wheel."""
        if x is not None and y is not None:
            self.mouse_move(x, y, duration_ms=40)

        if delta_y != 0:
            inp = INPUT(type=INPUT_MOUSE)
            inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=int(delta_y), dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)
            self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        if delta_x != 0:
            inp = INPUT(type=INPUT_MOUSE)
            inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=int(delta_x), dwFlags=MOUSEEVENTF_HWHEEL, time=0, dwExtraInfo=0)
            self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _resolve_vk(self, key: str) -> Tuple[int, int]:
        """Resolves key string to (vk_code, scan_code)."""
        key_lower = key.lower()
        if key_lower in VK_MAP:
            vk = VK_MAP[key_lower]
            scan = self._user32.MapVirtualKeyW(vk, 0)
            return vk, scan

        # Single character
        if len(key) == 1:
            res = self._user32.VkKeyScanW(ord(key))
            if res != -1:
                vk = res & 0xFF
                scan = self._user32.MapVirtualKeyW(vk, 0)
                return vk, scan

        return 0, 0

    def key_down(self, key: str) -> None:
        """Sends key down event."""
        vk, scan = self._resolve_vk(key)
        if vk == 0:
            return
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=0, time=0, dwExtraInfo=0)
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def key_up(self, key: str) -> None:
        """Sends key up event."""
        vk, scan = self._resolve_vk(key)
        if vk == 0:
            return
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def key_press(self, keys: Union[str, List[str]], hold_ms: int = 50) -> None:
        """
        Presses single key or hotkey combination (e.g. ['ctrl', 's'], ['shift', 'a']).
        """
        key_list = [keys] if isinstance(keys, str) else keys
        for k in key_list:
            self.key_down(k)
            time.sleep(0.01)

        time.sleep(max(0.01, hold_ms / 1000.0))

        for k in reversed(key_list):
            self.key_up(k)
            time.sleep(0.01)

    def type_text(self, text: str, cpm: int = 400) -> None:
        """
        Types Unicode text accurately via KEYEVENTF_UNICODE.
        """
        delay = 60.0 / max(50, cpm)
        for char in text:
            code = ord(char)
            # Down
            inp_down = INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
            self._user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))

            time.sleep(0.01)

            # Up
            inp_up = INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            self._user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

            if delay > 0.01:
                time.sleep(delay - 0.01)


if __name__ == "__main__":
    controller = InputController()
    pos = controller.get_cursor_pos()
    print(f"InputController initialized. Current cursor: {pos}")
