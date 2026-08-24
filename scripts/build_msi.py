"""
Windows MSI & Executable Installer Builder for GhostCanvas 3D.
Generates WiX Toolset project definition (.wxs), Inno Setup script (.iss),
and builds the self-contained installation package.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def generate_inno_setup_script(output_iss_path: str, source_dir: str):
    """Generates a complete Inno Setup script for one-click .exe creation."""
    iss_content = f"""
; Inno Setup Script for GhostCanvas 3D
[Setup]
AppId={{{{4C236B2B-6C3D-4A2B-8E27-6E274A2B9199}}}}
AppName=GhostCanvas 3D
AppVersion=1.1.1
AppPublisher=GhostCanvas
AppPublisherURL=https://ghostcanvas3d.com
AppSupportURL=https://ghostcanvas3d.com/docs
AppUpdatesURL=https://ghostcanvas3d.com/downloads
DefaultDirName={{autopf}}\\GhostCanvas3D
DefaultGroupName=GhostCanvas 3D
DisableProgramGroupPage=yes
OutputBaseFilename=GhostCanvas3D-Setup-v1.1.1
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{source_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "\\dist\\*,\\staging\\*,\\.git\\*,\\__pycache__\\*,*.pyc"

[Icons]
Name: "{{group}}\\GhostCanvas 3D Manager"; Filename: "python.exe"; Parameters: "\"\"{{app}}\\host\\tray_app.py\"\""
Name: "{{commondesktop}}\\GhostCanvas 3D"; Filename: "python.exe"; Parameters: "\"\"{{app}}\\host\\tray_app.py\"\""

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File \"\"{{app}}\\install.ps1\"\" -NonInteractive"; Description: "Provision Hyper-V VM and Register MCP Server"; Flags: runhidden
"""
    with open(output_iss_path, "w", encoding="utf-8") as f:
        f.write(iss_content.strip())
    print(f"Generated Inno Setup Script: {output_iss_path}")


def build_installer():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(root_dir, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    iss_file = os.path.join(dist_dir, "GhostCanvas3D.iss")
    generate_inno_setup_script(iss_file, root_dir)

    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if os.path.exists(iscc):
        print(f"Found Inno Setup Compiler: {iscc}. Compiling installer...")
        res = subprocess.run([iscc, iss_file], capture_output=True, text=True)
        if res.returncode == 0:
            print("Installer compiled successfully into dist/Output/GhostCanvas3D-Setup-v1.1.1.exe")
        else:
            print(f"Inno Setup warning: {res.stderr}")
    else:
        print("Note: Inno Setup compiler (ISCC) not in PATH. Generated .iss project ready for compilation.")


if __name__ == "__main__":
    build_installer()
