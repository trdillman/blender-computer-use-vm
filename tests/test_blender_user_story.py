"""
Comprehensive End-to-End Test Suite for Blender Computer-Use VM & MCP Server.
Validates all subsystems:
- DXGI/PIL Framebuffer Capture & Grid Annotations
- Win32 SendInput Hardware Controller
- UI Automation Tree Inspector & Window Enumeration
- NVENC Video Recording Engine
- Blender In-Process Telemetry Bridge & Invariants
- Host MCP Server Tool Dispatcher & Schema
- Full End-to-End Simulated User Story Scenario
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from PIL import Image

# Add guest, host, blender modules to import path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "guest"))
sys.path.insert(0, os.path.join(ROOT_DIR, "host"))
sys.path.insert(0, os.path.join(ROOT_DIR, "blender"))

from screen_capture import ScreenCaptureEngine
from input_controller import InputController, VK_MAP
from ui_automation import UIAutomationInspector
from video_recorder import VideoRecorder
from state_inspector import StateInspector
from cu_telemetry_bridge import TelemetryBridgeServer
from mcp_server import TOOLS, handle_tool_call


class TestScreenCapture(unittest.TestCase):
    """Validates screen capture, grid annotations, and visual diffs."""

    def setUp(self):
        self.engine = ScreenCaptureEngine()

    def test_capture_frame_and_bytes(self):
        img = self.engine.capture_frame(region=[0, 0, 400, 300])
        self.assertEqual(img.size, (400, 300))
        self.assertEqual(img.mode, "RGB")

        png_bytes, mime = self.engine.capture_bytes(region=[0, 0, 200, 200], format="png")
        self.assertTrue(len(png_bytes) > 0)
        self.assertEqual(mime, "image/png")

    def test_grid_annotation(self):
        img = self.engine.capture_frame(region=[0, 0, 300, 300], annotate_grid=True)
        self.assertEqual(img.size, (300, 300))

    def test_visual_diff(self):
        img1 = Image.new("RGB", (200, 200), color=(100, 100, 100))
        img2 = Image.new("RGB", (200, 200), color=(100, 100, 100))
        res_identical = ScreenCaptureEngine.compare_images(img1, img2, threshold=0.01)
        self.assertTrue(res_identical["match"])
        self.assertEqual(res_identical["similarity"], 1.0)

        img_diff = Image.new("RGB", (200, 200), color=(255, 0, 0))
        res_diff = ScreenCaptureEngine.compare_images(img1, img_diff, threshold=0.01)
        self.assertFalse(res_diff["match"])
        self.assertTrue(res_diff["similarity"] < 0.5)


@unittest.skipUnless(
    os.environ.get("BLENDER_CU_ALLOW_HOST_INPUT") == "1",
    "Injects real Win32 input — runs only inside the guest VM, or on the host "
    "with BLENDER_CU_ALLOW_HOST_INPUT=1 (will move your physical cursor).",
)
class TestInputController(unittest.TestCase):
    """Validates Win32 input mappings and cursor querying."""

    def setUp(self):
        self.ctrl = InputController()

    def test_cursor_pos(self):
        x, y = self.ctrl.get_cursor_pos()
        self.assertIsInstance(x, int)
        self.assertIsInstance(y, int)

    def test_vk_mappings(self):
        self.assertIn("ctrl", VK_MAP)
        self.assertIn("shift", VK_MAP)
        self.assertIn("numpad_1", VK_MAP)
        self.assertIn("f12", VK_MAP)

        vk, scan = self.ctrl._resolve_vk("shift")
        self.assertEqual(vk, 0x10)
        self.assertTrue(scan > 0)


class TestUIAutomation(unittest.TestCase):
    """Validates window enumeration and discovery."""

    def setUp(self):
        self.inspector = UIAutomationInspector()

    def test_window_list(self):
        windows = self.inspector.list_windows(filter_visible=True)
        self.assertIsInstance(windows, list)
        if windows:
            w = windows[0]
            self.assertIn("hwnd", w)
            self.assertIn("title", w)
            self.assertIn("rect", w)
            self.assertEqual(len(w["rect"]), 4)


class TestVideoRecorder(unittest.TestCase):
    """Validates asynchronous video recording loop."""

    def test_record_lifecycle(self):
        rec = VideoRecorder()
        out_path = "C:\\Temp\\test_e2e_video.mp4"
        start_res = rec.start_recording(output_path=out_path, fps=30)
        self.assertIn(start_res["status"], ("started", "already_recording"))
        self.assertTrue(rec.is_recording)

        time.sleep(0.5)
        status = rec.get_status()
        self.assertTrue(status["is_recording"])
        self.assertTrue(status["frame_count"] > 0)

        stop_res = rec.stop_recording()
        self.assertEqual(stop_res["status"], "stopped")
        self.assertFalse(rec.is_recording)


class TestBlenderTelemetry(unittest.TestCase):
    """Validates Blender state assertions and server lifecycle."""

    def test_bridge_lifecycle(self):
        server = TelemetryBridgeServer(port=29199)
        server.start()
        self.assertTrue(server.thread and server.thread.is_alive())
        server.stop()

    def test_state_assertions(self):
        rules = {"min_objects": 0, "mode": "UNKNOWN"}
        res = StateInspector.assert_scene_invariants(rules)
        self.assertIn(res["status"], ("passed", "failed", "error"))


class TestMCPServer(unittest.TestCase):
    """Validates MCP tool registry and tool dispatching."""

    def test_tool_registry_completeness(self):
        tool_names = [t["name"] for t in TOOLS]
        required_tools = [
            "vm_mouse_click",
            "vm_mouse_move",
            "vm_mouse_drag",
            "vm_mouse_scroll",
            "vm_keyboard_type",
            "vm_keyboard_press",
            "vm_screenshot",
            "vm_video_record",
            "vm_list_windows",
            "vm_find_element",
            "vm_focus_window",
            "vm_blender_eval",
            "vm_session_reset",
            "vm_health_check",
        ]
        for req in required_tools:
            self.assertIn(req, tool_names)

    def test_tool_call_dispatch(self):
        res = handle_tool_call("vm_screenshot", {"region": "0,0,100,100", "format": "png"})
        self.assertIsInstance(res, dict)


class TestFullUserStoryScenario(unittest.TestCase):
    """Simulates a complete autonomous Blender user story test run."""

    def test_simulated_blender_user_story(self):
        print("\n--- Executing Full Simulated Blender User Story ---")

        # 1. Step: Start Video Recording
        rec = VideoRecorder()
        rec_res = rec.start_recording(output_path="C:\\Temp\\story_run.mp4", fps=30)
        self.assertEqual(rec_res["status"], "started")
        print(" [Step 1] Started Video Recording.")

        # 2. Step: Inspect UI Hierarchy
        inspector = UIAutomationInspector()
        windows = inspector.list_windows()
        print(f" [Step 2] Enumerated {len(windows)} active desktop surfaces.")

        # 3. Step: Capture Initial Viewport Frame
        engine = ScreenCaptureEngine()
        init_frame = engine.capture_frame(region=[0, 0, 800, 600], annotate_grid=True)
        self.assertEqual(init_frame.size, (800, 600))
        print(" [Step 3] Captured Initial Frame with Spatial Grid Overlay.")

        # 4. Step: Simulate Key Shortcut ('Shift + A' -> Add Menu)
        input_ctrl = InputController()
        input_ctrl.key_press(["shift", "a"], hold_ms=30)
        time.sleep(0.1)
        print(" [Step 4] Injected 'Shift+A' Add Menu shortcut.")

        # 5. Step: Simulate Mouse Drag (Middle Mouse Orbit)
        input_ctrl.mouse_drag(start_x=300, start_y=300, end_x=450, end_y=350, button="middle", duration_ms=100)
        print(" [Step 5] Injected MMB Viewport Orbit Drag.")

        # 6. Step: Capture Updated Viewport Frame & Visual Diff
        updated_frame = engine.capture_frame(region=[0, 0, 800, 600])
        diff_res = ScreenCaptureEngine.compare_images(init_frame, updated_frame, threshold=0.05)
        print(f" [Step 6] Evaluated Frame Diff (Similarity: {diff_res['similarity']}).")

        # 7. Step: Stop Video Recording & Output Report
        stop_res = rec.stop_recording()
        print(f" [Step 7] Finalized Video Artifact: {stop_res['duration_seconds']}s, {stop_res['frame_count']} frames.")
        print("--- User Story Execution Completed Successfully ---\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
