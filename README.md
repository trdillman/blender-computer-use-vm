# Blender Computer-Use Isolated Virtual Machine & MCP Server

An isolated, GPU-partitioned local Windows 11 Virtual Machine environment connected via Model Context Protocol (MCP) specifically engineered for AI coding agents to perform automated Blender UI testing, user-story validation, and Computer-Use workflows without disturbing your host desktop.

---

## 1. System Architecture

```
+---------------------------------------------------------------------------------------------+
|                          Coding Agents (Claude Code / OMP / Codex)                          |
+---------------------------------------------------------------------------------------------+
                                              │
                                              │ (MCP JSON-RPC via stdio)
                                              ▼
+─────────────────────────────────────────────────────────────────────────────────────────────+
|                         Host Layer: `blender-cu-vm-mcp` Server                             |
|  - MCP Tool Handler (Computer Use, Analytical Inspection, Blender Telemetry, File Staging)   |
|  - VM Lifecycle Manager (Hyper-V Socket / PowerShell WMI / Sub-2s Snapshot Reset)           |
+─────────────────────────────────────────────────────────────────────────────────────────────+
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │ Hyper-V Socket (HV-SOCK) / Internal VMSwitch  │
                      ▼                                               ▼
+───────────────────────────────────────────────+   +─────────────────────────────────────────+
|      Windows 11 Guest VM (Hyper-V)            |   |   Secondary (Fast CI): WSL2 Container   |
|  - NVIDIA GPU-PV (RTX 4080 Super vGPU: 8GB)   |   |   - Mesa / Direct3D 12 GPU Accel        |
|  - Virtual Display Driver (1080p Fixed 60Hz)  |   |   - Virtual X11 Display (Xvfb/Weston)   |
|  - Guest Agent Daemon (FastAPI / gRPC)        |   |   - Guest Agent Daemon (Linux)          |
|  - In-Process Blender Telemetry Bridge (bpy)  |   |   - Blender bpy IPC Bridge              |
+───────────────────────────────────────────────+   +─────────────────────────────────────────+
```

---

## 2. Key Features

- **Zero Host Disturbance:** Synthetic mouse movements, drags, clicks, and keystrokes are executed exclusively inside the guest OS. Your real cursor and window focus remain completely untouched.
- **Hardware-Accelerated GPU Rendering:** NVIDIA GPU-PV gives the guest VM near-native access to the host RTX 4080 Super (DirectX 12, Vulkan, OpenGL, and CUDA/OptiX).
- **Deterministic 1080p Display:** Open-source Virtual Display Driver (`IddSampleDriver`) locks the virtual screen to 1920x1080 @ 60Hz with 100% (96 DPI) scaling—preventing coordinate drift and sleeping monitors.
- **Hybrid Multimodal Feedback:** Agents receive:
  1. *Visual:* Framebuffer screenshots with optional coordinate grid overlays.
  2. *Analytical:* Windows UI Automation tree, bounding boxes, and window responsiveness.
  3. *Deep Telemetry:* Blender `bpy` state, active modifiers, node tree connections, and real-time `stdout`/`stderr` logs.
- **Sub-2-Second State Rollback:** Fast Hyper-V snapshot restoration resets the VM to a clean golden base after destructive or experimental runs.

---

## 3. Directory Layout

```
blender-cu-vm/
├── host/                     # Host MCP Server & Hyper-V Controller
│   ├── mcp_server.py         # Stdio JSON-RPC MCP server with 14 tools
│   ├── hv_transport.py       # Hyper-V Socket (AF_HYPERV) & HTTP transport
│   ├── vm_controller.py      # PowerShell WMI lifecycle & snapshot manager
│   └── asset_sync.py         # Bi-directional file and addon staging
├── guest/                    # Guest Agent Daemon (runs inside VM)
│   ├── guest_daemon.py       # FastAPI HTTP/HV-SOCK unified server
│   ├── screen_capture.py     # DXGI Desktop Duplication & visual diffs
│   ├── input_controller.py   # Win32 SendInput (clicks, drags, typing)
│   ├── ui_automation.py      # Windows UI Automation tree inspector
│   └── video_recorder.py     # Hardware-accelerated NVENC MP4 recorder
├── blender/                  # Blender Embedded Runtime Bridge
│   ├── cu_telemetry_bridge.py # Non-blocking TCP telemetry server
│   ├── crash_interceptor.py  # C-level stdout/stderr stream tee
│   └── state_inspector.py    # Declarative scene invariant checker
├── scripts/                  # Automated Setup & Provisioning
│   ├── setup_vm_gpupv.ps1    # Automated Hyper-V Gen2 VM creator
│   ├── stage_gpupv_drivers.ps1 # NVIDIA GPU-PV driver packaging & injection
│   ├── setup_virtual_display.ps1 # Virtual display & autologon configuration
│   └── manage_golden_snapshot.ps1 # Instant snapshot creation & rollback
├── tests/                    # Verification & E2E Test Suite
│   ├── test_blender_user_story.py # 12-stage automated test suite
│   └── verify_isolation.py   # Zero host disturbance verification
├── mcp-config.json           # Registration snippet for Claude Code / OMP
└── README.md
```

---

## 4. Setup & Installation Guide

### Step 1: Provision the VM on Host (PowerShell as Administrator)
```powershell
cd C:\tmp\blender-cu-vm\scripts
.\setup_vm_gpupv.ps1 -VMName "Blender-CU-VM" -MemoryBytes 8GB -ProcessorCount 8
```

### Step 2: Stage NVIDIA GPU-PV Drivers
```powershell
.\stage_gpupv_drivers.ps1 -VMName "Blender-CU-VM" -Mode "Stage"
```

### Step 3: Install Guest OS & Run Environment Setup
Inside the guest VM (via PowerShell as Administrator):
```powershell
# 1. Install GPU-PV drivers from staged directory
C:\Temp\NvidiaDrivers\install_gpupv_guest.bat

# 2. Configure Virtual Display & Auto-Logon
.\setup_virtual_display.ps1 -TargetWidth 1920 -TargetHeight 1080

# 3. Start Guest Daemon on boot
python C:\blender-cu-vm\guest\guest_daemon.py
```

### Step 4: Create the Golden Base Snapshot
```powershell
.\manage_golden_snapshot.ps1 -VMName "Blender-CU-VM" -SnapshotName "golden_base" -Action "Create"
```

---

## 5. Connecting AI Coding Agents via MCP

Add the following to your `~/.claude.json` or `~/.omp/agent/config.yml`:

```json
{
  "mcpServers": {
    "blender-cu-vm": {
      "command": "python",
      "args": [
        "C:\\tmp\\blender-cu-vm\\host\\mcp_server.py"
      ],
      "env": {
        "BLENDER_VM_NAME": "Blender-CU-VM",
        "BLENDER_GUEST_URL": "http://192.168.122.100:8000"
      }
    }
  }
}
```

---

## 6. Running Verification Tests

To verify all subsystems and run the simulated Blender user story:
```bash
python blender-cu-vm/tests/test_blender_user_story.py
python blender-cu-vm/tests/verify_isolation.py
```
