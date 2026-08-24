---
name: blender-computer-use-vm
description: Control isolated Blender Computer-Use VM over MCP for UI testing, user-story automation, and viewport interaction without host disturbance.
metadata:
  skill_class: execution
  run_mode: explicit
  selection:
    allow_implicit_invocation: true
    use_when:
      - automated Blender UI testing or user-story execution
      - testing Blender add-ons or viewport shaders without stealing host cursor/focus
      - running computer-use workflows in an isolated local GPU-accelerated VM
    avoid_when:
      - packaging-only Python work
      - pure background deterministic CLI batch rendering with no GUI
  tags: [blender, computer-use, vm, mcp, hyper-v, gpu-pv, e2e-testing]
---

# Blender Computer-Use Isolated VM & MCP Control

Use this skill when asked to perform automated Blender UI testing, user-story execution, viewport interaction, add-on visual validation, or computer-use workflows that must not disturb the host desktop.

## Canonical Architecture

The isolated environment connects over the `blender-cu-vm` Model Context Protocol (MCP) server:

- **Host MCP Server:** `C:\tmp\blender-cu-vm\host\mcp_server.py`
- **Guest API Daemon:** `http://192.168.122.100:8000` (or Hyper-V Socket `AF_HYPERV`)
- **Virtual Display:** Fixed 1920x1080 @ 60Hz, 100% DPI (96 DPI)
- **Target OS:** Windows 11 Hyper-V VM with NVIDIA GPU-PV (RTX 4080 Super vGPU)
- **Target Blender:** Blender 5.2 / 5.1 / 4.2 LTS

---

## MCP Tool Reference

| Tool Name | Action | Key Parameters |
|---|---|---|
| `vm_mouse_click` | Clicks at coordinates | `x`, `y`, `button` ("left"/"right"/"middle"), `clicks`, `modifiers` |
| `vm_mouse_move` | Moves cursor smoothly | `x`, `y`, `duration_ms` |
| `vm_mouse_drag` | Drags mouse from start to end (for Blender Viewport orbit/pan/zoom or node wires) | `start_x`, `start_y`, `end_x`, `end_y`, `button`, `modifiers` |
| `vm_mouse_scroll` | Scrolls vertical/horizontal wheel | `x`, `y`, `delta_y` (+120 up, -120 down) |
| `vm_keyboard_type` | Types unicode text string | `text`, `cpm` (characters per minute) |
| `vm_keyboard_press` | Presses key or hotkey combo | `keys` (e.g. `["shift", "a"]`, `["ctrl", "s"]`, `["f12"]`, `["numpad_1"]`) |
| `vm_screenshot` | Captures desktop framebuffer | `region` ("x,y,w,h"), `format` ("png"/"jpeg"), `annotate_grid` (bool) |
| `vm_video_record` | Controls hardware video recording | `action` ("start"/"stop"/"status"), `output_path` |
| `vm_list_windows` | Enumerates open desktop windows | `filter_visible` (bool) |
| `vm_find_element` | Finds UI element bounding box | `query` (label/class name), `hwnd` |
| `vm_focus_window` | Brings window to foreground | `hwnd` |
| `vm_blender_eval` | Evaluates Python expr in Blender | `expression` (e.g. `bpy.context.active_object.name`) |
| `vm_session_reset` | Instantly rolls VM back to golden snapshot | `snapshot_name` (default: "golden_base") |
| `vm_health_check` | Checks VM & daemon health | (no parameters) |

---

## Standard User-Story Execution Protocol

When testing a Blender UI feature or add-on:

1. **Pre-flight & Reset:**
   - Call `vm_session_reset(snapshot_name="golden_base")` to guarantee clean state.
   - Call `vm_health_check()` to confirm 1920x1080 resolution and daemon connectivity.

2. **Session Recording:**
   - Call `vm_video_record(action="start", output_path="C:\\Temp\\run_story.mp4")`.

3. **Spatial Navigation & Computer Use:**
   - Call `vm_screenshot(annotate_grid=True)` to see coordinates and UI elements.
   - Use `vm_find_element(query="...")` for exact control bounding boxes.
   - Use `vm_keyboard_press` and `vm_mouse_drag` for Blender navigation:
     - Viewport Orbit: `vm_mouse_drag(button="middle")`
     - Viewport Pan: `vm_mouse_drag(button="middle", modifiers=["shift"])`
     - Add Menu: `vm_keyboard_press(keys=["shift", "a"])`
     - View Numpad: `vm_keyboard_press(keys=["numpad_1"])` or `["numpad_7"]`

4. **Analytical State Verification:**
   - Call `vm_blender_eval(expression="...")` to verify internal data invariants (`modifiers`, `frame`, `materials`, `nodes`).

5. **Finalize & Artifact Export:**
   - Call `vm_screenshot(format="png")` for visual proof.
   - Call `vm_video_record(action="stop")` to finalize MP4 recording.
   - Report pass/fail with structured metrics and video link.
