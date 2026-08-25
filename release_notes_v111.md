# GhostCanvas 3D v1.1.1 - Swarm Hardened Commercial Release

Complete hardened production release resolving all 8-lane swarm review findings:
- **Asymmetric Security & Licensing:** Removed client-shipped private signing keys; enforced 256-bit signature tags and strict payload schemas; eliminated PowerShell string injection in `vm_session_reset`.
- **IPC Route Realignment:** Added missing `POST /blender/eval` proxy in `guest_daemon.py`; added message length framing.
- **Blender 5.2 Thread Safety:** Marshaled all `bpy` state mutations to the Blender main thread via `bpy.app.timers.register` (100 Hz queue); updated `CyclesPreferences` device enumeration for Blender 5.2 LTS compatibility.
- **Hyper-V & VHDX Protection:** Added VM `State == Off` checks prior to offline VHDX mounting; added bounded status polling and mutex locks for snapshot restoration.
- **Win32 & Capture Hardening:** Added explicit 64-bit ctypes `argtypes`/`restype` signatures in `ui_automation.py`; added `KEYEVENTF_SCANCODE` flags in `input_controller.py`; added thread generation tracking in `video_recorder.py`.
- **Packaging & MSI Verification:** Completed WiX XML component directory definitions; fixed VBScript and Inno Setup quote escaping.
- **Test Suite:** 20/20 unit, integration, and Blender 5.2 headless execution tests passing.
