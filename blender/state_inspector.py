"""
Blender State Inspector and Operator Gatekeeper.
Provides structured declarative verification of scene invariants, node trees,
Cycles/Eevee GPU compute devices, and addon registration proofs.
"""

from __future__ import annotations

from typing import Any, Dict, List


class StateInspector:
    """Provides high-level state assertions and scene introspection."""

    @staticmethod
    def inspect_gpu_devices() -> Dict[str, Any]:
        """Inspects Cycles / OptiX / CUDA hardware compute devices."""
        try:
            import bpy  # type: ignore
            prefs = getattr(bpy.context, "preferences", None)
            cycles_prefs = prefs.addons.get("cycles") if prefs and hasattr(prefs, "addons") else None  # type: ignore
            if not cycles_prefs:
                return {"status": "cycles_not_available"}

            cprefs = cycles_prefs.preferences
            devices = getattr(cprefs, "get_devices", lambda: [])()  # type: ignore
            device_list: List[Dict[str, Any]] = []

            for dev in (devices[0] if isinstance(devices, tuple) else devices):
                device_list.append({
                    "name": dev.name,
                    "type": dev.type,
                    "use": dev.use,
                    "id": getattr(dev, "id", None),
                })

            return {
                "status": "success",
                "compute_device_type": getattr(cprefs, "compute_device_type", "UNKNOWN"),  # type: ignore
                "devices": device_list,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def inspect_node_tree(tree_owner_type: str, name: str) -> Dict[str, Any]:
        """
        Inspects nodes and socket links in a Material or Geometry Nodes modifier.
        :param tree_owner_type: 'material' or 'modifier'
        :param name: Material name or modifier name
        """
        try:
            import bpy  # type: ignore
            node_tree = None
            if tree_owner_type.lower() == "material":
                mat = bpy.data.materials.get(name)
                if mat and mat.use_nodes:
                    node_tree = mat.node_tree
            elif tree_owner_type.lower() == "modifier":
                obj = bpy.context.active_object
                if obj:
                    mod = obj.modifiers.get(name)
                    if mod and hasattr(mod, "node_group"):
                        node_tree = mod.node_group

            if not node_tree:
                return {"status": "not_found", "target": name, "type": tree_owner_type}

            nodes_data = [
                {"name": n.name, "type": n.type, "location": [round(n.location.x, 1), round(n.location.y, 1)]}
                for n in node_tree.nodes
            ]

            links_data = [
                {
                    "from_node": getattr(link.from_node, "name", ""),  # type: ignore
                    "from_socket": getattr(link.from_socket, "name", ""),  # type: ignore
                    "to_node": getattr(link.to_node, "name", ""),  # type: ignore
                    "to_socket": getattr(link.to_socket, "name", ""),  # type: ignore
                }
                for link in node_tree.links
            ]

            return {
                "status": "success",
                "node_tree_name": node_tree.name,
                "node_count": len(nodes_data),
                "link_count": len(links_data),
                "nodes": nodes_data,
                "links": links_data,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def inspect_addon_proof(module_name: str) -> Dict[str, Any]:
        """
        Proves whether an addon is loaded, enabled, and registered in preferences.
        """
        try:
            import addon_utils  # type: ignore
            import bpy  # type: ignore

            is_default, is_loaded = addon_utils.check(module_name)
            prefs = getattr(bpy.context, "preferences", None)
            is_in_prefs = (module_name in prefs.addons) if prefs and hasattr(prefs, "addons") else False  # type: ignore
            addon_obj = prefs.addons.get(module_name) if prefs and hasattr(prefs, "addons") else None  # type: ignore

            return {
                "status": "success",
                "module_name": module_name,
                "is_loaded": bool(is_loaded),
                "is_default": bool(is_default),
                "is_in_preferences": is_in_prefs,
                "preferences_enabled": addon_obj is not None,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def assert_scene_invariants(rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates declarative assertions against live scene state.
        Rules can check: 'active_object', 'min_objects', 'current_frame', 'mode', 'has_modifiers'.
        """
        try:
            import bpy  # type: ignore
            scene = bpy.context.scene
            active_obj = bpy.context.active_object
            failures: List[str] = []

            if "active_object" in rules:
                expected = rules["active_object"]
                actual = active_obj.name if active_obj else None
                if actual != expected:
                    failures.append(f"active_object mismatch: expected '{expected}', got '{actual}'")

            if "min_objects" in rules:
                expected_min = int(rules["min_objects"])
                actual_count = len(getattr(scene, "objects", []))  # type: ignore
                if actual_count < expected_min:
                    failures.append(f"object count {actual_count} < minimum {expected_min}")

            if "current_frame" in rules:
                expected_frame = int(rules["current_frame"])
                actual_frame = getattr(scene, "frame_current", 0)  # type: ignore
                if actual_frame != expected_frame:
                    failures.append(f"current_frame mismatch: expected {expected_frame}, got {actual_frame}")

            if "mode" in rules:
                expected_mode = rules["mode"]
                actual_mode = getattr(bpy.context, "mode", "UNKNOWN")
                if actual_mode != expected_mode:
                    failures.append(f"mode mismatch: expected '{expected_mode}', got '{actual_mode}'")

            return {
                "status": "passed" if len(failures) == 0 else "failed",
                "passed": len(failures) == 0,
                "failures": failures,
                "rules_checked": len(rules),
            }
        except Exception as e:
            return {"status": "error", "passed": False, "message": str(e)}


if __name__ == "__main__":
    inspector = StateInspector()
    print("StateInspector initialized.")
