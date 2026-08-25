# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An isolated, GPU-partitioned Windows 11 Hyper-V VM controlled over MCP, so AI agents can do Blender UI testing / Computer-Use without touching the host desktop. The commercial layer (v1.1+, licensing, tray app, MSI, storefront) is branded **GhostCanvas 3D** — that name in `host/licensing.py`, `host/tray_app.py`, `blender/agent_studio_pro.py`, and `scripts/build_msi.py` refers to this same product.

## Commands

```powershell
# Run test suites (unittest-based, each file has a __main__ entry)
python tests/test_blender_user_story.py    # E2E: capture, input, UIA, NVENC, telemetry, MCP dispatch
python tests/test_commercial_suite.py      # licensing crypto, HWID node-lock, tray, MSI builder
python tests/verify_isolation.py           # static proof that host layer never injects input

# Single test (unittest.main accepts names as argv)
python tests/test_blender_user_story.py TestScreenCapture.test_grid_annotation

# MCP server (stdio JSON-RPC; what agents connect to)
python host/mcp_server.py

# Installer: registers MCP into ~/.claude.json + ~/.omp config, deploys skill, runs tests
python install.py --all          # or granular: --register-mcp --deploy-skill --verify
.\install.ps1                    # master host installer (prereqs, VM provisioning, registration)

# Packaging
python scripts/package_release.py
python scripts/build_msi.py

# VM lifecycle (admin PowerShell; see README §4 for full provisioning flow)
.\scripts\setup_vm_gpupv.ps1 -VMName "Blender-CU-VM" -MemoryBytes 8GB -ProcessorCount 8
.\scripts\stage_gpupv_drivers.ps1 -VMName "Blender-CU-VM" -Mode "Stage"
.\scripts\manage_golden_snapshot.ps1 -VMName "Blender-CU-VM" -SnapshotName "golden_base" -Action "Create"
```

Note: Before running `test_blender_user_story.py`, see the `BLENDER_CU_ALLOW_HOST_INPUT` safety guidance in Repo conventions below.

## Architecture

Three tiers, strictly one-directional:

1. **Host tier** — `host/mcp_server.py`: stdio JSON-RPC server exposing 16 `vm_*` tools (input, screenshot, UIA, `vm_blender_eval`, `vm_session_reset`, `vm_license_status`, `vm_activate_license`). Routes calls through `hv_transport.py` (AF_HYPERV HV-SOCK, auto-fallback to HTTP at `BLENDER_GUEST_URL`). `vm_controller.py` drives Hyper-V via PowerShell WMI; `vm_session_reset` restores the `golden_base` snapshot for sub-2s clean-slate rollback. `asset_sync.py` stages .blend/addon files into the guest and pulls renders/dumps back.

2. **Guest tier** — `guest/guest_daemon.py`: FastAPI daemon on `0.0.0.0:8000` (`GUEST_DAEMON_PORT`), token-authenticated via `GUEST_DAEMON_SECRET`. All actual Win32 work happens here: `input_controller.py` (SendInput, Bézier drags), `screen_capture.py` (DXGI duplication + grid overlays), `ui_automation.py` (ctypes UIA tree), `video_recorder.py` (NVENC MP4).

3. **Blender tier** — `blender/cu_telemetry_bridge.py`: runs inside Blender's embedded Python; TCP server on port 9199 (`BLENDER_BRIDGE_PORT`). All `bpy` access is marshaled to Blender's main thread via `bpy.app.timers` — never touch bpy from the listener thread. `vm_blender_eval` flows: MCP → guest daemon → this bridge. `state_inspector.py` does declarative scene-invariant checks, `crash_interceptor.py` tees C-level stdout/stderr.

**Critical invariant:** the host tier must never import or call Win32 input/capture APIs — every computer-use action is a network payload to the guest. `tests/verify_isolation.py` enforces this; keep it passing when refactoring `host/`.

### Repo conventions

- **Windows-only codebase** (Win32 ctypes, Hyper-V, PowerShell). Primary shell is PowerShell.
- **Host safety (mandatory review gate every iteration):** before commit/push,
  audit changed files for host-destructive operations — disk wipe/format,
  `Remove-Item -Recurse` outside project paths, Winlogon/registry mutation,
  input injection on the host, wholesale overwrite of user config
  (`~/.claude.json`, `~/.omp`). Flag findings in the loop progress doc and
  neutralize (runtime guard or move to `quarantine/`) before proceeding.
- `scripts/autounattend.xml` sets `WillWipeDisk=true` — it erases Disk 0 of
  whatever machine consumes it. Guest-VM-only by design: never write the
  bootstrap ISO to physical media or boot it on real hardware.
- Guest-config scripts (`scripts/setup_virtual_display.ps1`,
  `guest/install_guest.ps1`) abort unless run inside the VM
  (`COMPUTERNAME -eq "BLENDER-CU-VM"`) or `BLENDER_CU_ALLOW_HOST=1` is set.
- `install.py` refuses to touch `~/.claude.json` on parse failure and always
  writes a timestamped `.backup-*` copy before modifying it.
- Direct Win32 input test classes skip by default and require
  `BLENDER_CU_ALLOW_HOST_INPUT=1`, which must only be enabled inside the guest.
  Default mocked route/isolation tests do not inject input; capture/video tests may
  observe the desktop and write temporary artifacts.
- `staging/` holds multi-GB untracked payloads (Blender 5.2, NVIDIA GPU-PV drivers) — gitignored; never stage them. Test artifacts go to `C:\Temp` (also gitignored).
- The skill `blender-computer-use-vm/SKILL.md` exists in **three mirror copies** — `skills/` (canonical, used by `.claude-plugin/plugin.json`), `.claude/skills/`, and `.skills/` (for OMP) — so different loaders pick it up zero-config. Update all three together.
- Version strings live in `package.json`, `marketplace.json`, and `.claude-plugin/plugin.json` — bump all three together.
- MCP registration config is duplicated in `.mcp.json` and `mcp-config.json` (`BLENDER_VM_NAME`, `BLENDER_GUEST_URL` env).
- When driving the live VM, prefer the `blender-computer-use-vm` skill (project skill) for the tool reference and the standard user-story execution protocol.
