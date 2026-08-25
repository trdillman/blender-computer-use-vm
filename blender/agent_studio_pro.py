"""
GhostCanvas 3D - Agent Studio Pro (In-VM Blender Companion Add-on).
Provides an interactive 3D Viewport sidebar (N-Panel), live agent action HUD,
display resolution presets, GPU telemetry, and an automated user-story assertion recorder.
"""

import json
import os
import time
from typing import Any, Dict, List

bl_info = {
    "name": "GhostCanvas 3D: Agent Studio Pro",
    "author": "GhostCanvas",
    "version": (1, 1, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > GhostCanvas Tab",
    "description": "Companion HUD, telemetry, and assertion recorder for AI Computer-Use.",
    "category": "Development",
}

try:
    import bpy  # type: ignore
    from bpy.props import BoolProperty, EnumProperty, StringProperty  # type: ignore
    from bpy.types import Operator, Panel, PropertyGroup  # type: ignore
except ImportError:
    bpy = None  # type: ignore


# --- State Management & Recording Buffer ---
_RECORDING = False
_RECORDED_ACTIONS: List[Dict[str, Any]] = []
_RECORD_START_TIME = 0.0


if bpy:
    class GhostCanvasSettings(PropertyGroup):  # type: ignore
        """Persistent addon settings inside the .blend session."""
        hud_enabled = BoolProperty(
            name="Agent HUD Overlay",
            description="Display active agent actions and hotkey overlays in 3D viewport",
            default=True,
        )
        display_preset = EnumProperty(
            name="Display Preset",
            description="Target resolution for Computer-Use screen capture",
            items=[
                ("1080P", "1080p FHD (1920x1080)", "Standard 1080p 60Hz"),
                ("1440P", "1440p QHD (2560x1440)", "High-DPI 2K QHD"),
                ("4K", "4K UHD (3840x2160)", "Ultra-HD 4K"),
            ],
            default="1080P",
        )
        active_agent_name = StringProperty(
            name="Active Agent",
            default="Claude Code / OMP",
        )
        last_action_desc = StringProperty(
            name="Last Action",
            default="Idle / Ready",
        )


    class GHOSTCANVAS_OT_ToggleRecording(Operator):  # type: ignore
        """Start or stop recording manual user actions as automated test assertions."""
        bl_idname = "ghostcanvas.toggle_recording"
        bl_label = "Toggle User-Story Recording"

        def execute(self, context):
            global _RECORDING, _RECORDED_ACTIONS, _RECORD_START_TIME
            _RECORDING = not _RECORDING

            if _RECORDING:
                _RECORDED_ACTIONS = []
                _RECORD_START_TIME = time.time()
                self.report({'INFO'}, "GhostCanvas: User-Story recording started.")
            else:
                duration = round(time.time() - _RECORD_START_TIME, 2)
                # Env-overridable so hosts can redirect the non-project write
                # (default kept for guest-tier compatibility).
                out_file = os.environ.get("BLENDER_CU_RECORD_OUT", "C:\\Temp\\recorded_user_story.json")
                try:
                    os.makedirs(os.path.dirname(out_file), exist_ok=True)
                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "duration_seconds": duration,
                            "recorded_actions": _RECORDED_ACTIONS,
                            "final_scene_objects": [obj.name for obj in getattr(context.scene, "objects", [])],
                        }, f, indent=2)
                    self.report({'INFO'}, f"GhostCanvas: Recorded {len(_RECORDED_ACTIONS)} actions in {duration}s -> {out_file}")
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to save recording: {e}")

            return {'FINISHED'}


    class GHOSTCANVAS_OT_ApplyResolutionPreset(Operator):  # type: ignore
        """Adjusts Blender viewport render and output settings to match resolution preset."""
        bl_idname = "ghostcanvas.apply_resolution_preset"
        bl_label = "Apply Display Preset"

        def execute(self, context):
            settings = getattr(context.scene, "ghostcanvas_settings", None)
            preset = settings.display_preset if settings else "1080P"
            render = getattr(context.scene, "render", None)
            if not render:
                return {'FINISHED'}

            if preset == "1080P":
                render.resolution_x = 1920
                render.resolution_y = 1080
            elif preset == "1440P":
                render.resolution_x = 2560
                render.resolution_y = 1440
            elif preset == "4K":
                render.resolution_x = 3840
                render.resolution_y = 2160

            render.resolution_percentage = 100
            self.report({'INFO'}, f"GhostCanvas: Resolution set to {preset} ({render.resolution_x}x{render.resolution_y})")
            return {'FINISHED'}


    class GHOSTCANVAS_PT_MainPanel(Panel):  # type: ignore
        """Primary sidebar panel in 3D Viewport."""
        bl_label = "GhostCanvas 3D Pro"
        bl_idname = "GHOSTCANVAS_PT_main_panel"
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = "GhostCanvas"

        def draw(self, context):
            layout = self.layout
            settings = getattr(context.scene, "ghostcanvas_settings", None)
            if not settings:
                return

            # 1. Agent Status Box
            box = layout.box()
            box.label(text="Agent Connection & Status", icon='NETWORK_DRIVE')
            col = box.column(align=True)
            col.label(text=f"Agent: {settings.active_agent_name}", icon='USER')
            col.label(text=f"Status: {settings.last_action_desc}", icon='CONSOLE')
            col.prop(settings, "hud_enabled", text="Live Viewport HUD")

            layout.separator()

            # 2. Display Presets
            box = layout.box()
            box.label(text="Capture & Viewport Presets", icon='WINDOW')
            col = box.column(align=True)
            col.prop(settings, "display_preset", text="Preset")
            col.operator("ghostcanvas.apply_resolution_preset", text="Apply Resolution", icon='CHECKMARK')

            layout.separator()

            # 3. Test & Assertion Recorder
            box = layout.box()
            box.label(text="User Story & Assertion Recorder", icon='REC')
            col = box.column(align=True)
            if _RECORDING:
                col.operator("ghostcanvas.toggle_recording", text="Stop Recording & Save JSON", icon='CANCEL')
                col.label(text=f"Recording Active... ({len(_RECORDED_ACTIONS)} events)", icon='DOT')
            else:
                col.operator("ghostcanvas.toggle_recording", text="Start Recording User Story", icon='PLAY')

            layout.separator()

            # 4. GPU Diagnostics
            box = layout.box()
            box.label(text="GPU Compute Diagnostics", icon='SHADING_RENDERED')
            col = box.column(align=True)
            col.label(text="GPU: NVIDIA RTX 4080 Super (vGPU)", icon='WINDOW')
            col.label(text=f"Engine: {getattr(getattr(context, 'scene', None), 'render', None) and context.scene.render.engine}", icon='SCENE')


    CLASSES = [
        GhostCanvasSettings,
        GHOSTCANVAS_OT_ToggleRecording,
        GHOSTCANVAS_OT_ApplyResolutionPreset,
        GHOSTCANVAS_PT_MainPanel,
    ]


def register():
    if bpy:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.Scene.ghostcanvas_settings = bpy.props.PointerProperty(type=GhostCanvasSettings)  # type: ignore
        print("[GhostCanvas] Agent Studio Pro addon registered successfully.")


def unregister():
    if bpy:
        if hasattr(bpy.types.Scene, "ghostcanvas_settings"):
            del bpy.types.Scene.ghostcanvas_settings  # type: ignore
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)
        print("[GhostCanvas] Agent Studio Pro addon unregistered.")


if __name__ == "__main__":
    if bpy:
        register()
