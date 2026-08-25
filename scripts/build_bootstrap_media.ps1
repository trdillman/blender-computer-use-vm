<#
.SYNOPSIS
    Builds the unattended bootstrap ISO for Blender-CU-VM guest deployment.

.DESCRIPTION
    Stages the unattended payload (autounattend.xml at root, bootstrap.cmd at
    root, guest\ scripts) and authors a real ISO9660+Joliet image using the
    built-in Windows IMAPI2 COM API (no ADK/oscdimg dependency).

    Windows Setup only reads autounattend.xml from the ROOT of attached
    removable/ISO media, so this ISO is what makes installation hands-off:
    attach it as a second DVD drive alongside the Windows 11 install ISO.

    Root bootstrap.cmd self-locates its own drive letter (%~d0) and launches
    guest\install_guest.ps1 hidden; autounattend.xml invokes it via a
    FirstLogonCommand drive-letter scan.
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [string]$OutputDir = "C:\VMs\Blender-CU-VM\Bootstrap",
    [string]$ISOPath = "",
    [string]$DaemonSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
if (-not $ISOPath) { $ISOPath = Join-Path $OutputDir "unattend.iso" }

Write-Host "=== Building Unattended Bootstrap Media for $VMName ===" -ForegroundColor Cyan

# --- 1. Stage payload folder ------------------------------------------------
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
$StagingFolder = Join-Path $OutputDir "Staging"
if (Test-Path $StagingFolder) {
    Remove-Item -Path $StagingFolder -Recurse -Force | Out-Null
}
New-Item -ItemType Directory -Path $StagingFolder -Force | Out-Null

Copy-Item -Path (Join-Path $ScriptDir "autounattend.xml") -Destination (Join-Path $StagingFolder "autounattend.xml") -Force
Write-Host "  + Injected autounattend.xml" -ForegroundColor Green

$GuestScripts = @(
    "install_guest.ps1",
    "guest_daemon.py",
    "screen_capture.py",
    "input_controller.py",
    "ui_automation.py",
    "video_recorder.py"
)
$GuestDest = Join-Path $StagingFolder "guest"
New-Item -ItemType Directory -Path $GuestDest -Force | Out-Null
foreach ($name in $GuestScripts) {
    $src = Join-Path $ProjectRoot "guest\$name"
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $GuestDest -Force
        Write-Host "  + Injected guest\$name" -ForegroundColor DarkGray
    } else {
        throw "Required guest payload missing: $src"
    }
}
# setup_virtual_display.ps1 travels INSIDE guest\ so install_guest.ps1 finds
# it beside itself on the DVD.
Copy-Item -Path (Join-Path $ScriptDir "setup_virtual_display.ps1") -Destination $GuestDest -Force
Write-Host "  + Injected guest\setup_virtual_display.ps1" -ForegroundColor DarkGray

# Optional daemon auth secret: travels beside install_guest.ps1 on the ISO and
# a host-side copy is kept next to the ISO for MCP callers (env var still wins).
if ($DaemonSecret) {
    if ($DaemonSecret -notmatch '^[A-Za-z0-9_.\-]{16,128}$') {
        throw "DaemonSecret failed charset validation (allowed: alphanumeric, '_', '-', '.'; 16-128 chars)."
    }
    Set-Content -Path (Join-Path $GuestDest "daemon_secret.txt") -Value $DaemonSecret -Encoding ASCII
    Set-Content -Path (Join-Path $OutputDir "guest_daemon_secret.txt") -Value $DaemonSecret -Encoding ASCII
    Write-Host "  + Injected guest\daemon_secret.txt (host copy: $(Join-Path $OutputDir 'guest_daemon_secret.txt'))" -ForegroundColor DarkGray
}

# --- 2. Root bootstrap.cmd (self-locating launcher) -------------------------
$BootstrapCmd = Join-Path $StagingFolder "bootstrap.cmd"
@"
@echo off
rem Blender-CU-VM guest bootstrap launcher (autonomous FirstLogonCommand).
rem %~d0 resolves to this DVD's drive letter regardless of assignment.
setlocal
set "PAYLOAD=%~d0\guest\install_guest.ps1"
if not exist "%PAYLOAD%" (
    echo [bootstrap] payload not found: %PAYLOAD% 1>&2
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%PAYLOAD%'"
endlocal
"@ | Set-Content -Path $BootstrapCmd -Encoding ASCII
Write-Host "  + Injected bootstrap.cmd" -ForegroundColor Green

# --- 3. Author ISO via built-in IMAPI2FS --------------------------------------
Write-Host "`nAuthoring ISO via IMAPI2: $ISOPath" -ForegroundColor Cyan
if (Test-Path $ISOPath) { Remove-Item -Path $ISOPath -Force }

# The image arrives as a COM IStream; late-bound .Read is not exposed via
# IDispatch, so pump it through a proper interop definition.
if (-not ([System.Management.Automation.PSTypeName]'BlenderCuVm.IsoWriter').Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace BlenderCuVm {
    [ComImport]
    [Guid("0000000C-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IStreamInterop {
        int Read([MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 1)] byte[] pv, int cb, IntPtr pcbRead);
    }

    public static class IsoWriter {
        public static void WriteIStreamToFile(object comStream, string path) {
            var stream = (IStreamInterop)comStream;
            using (var file = new System.IO.FileStream(path, System.IO.FileMode.Create, System.IO.FileAccess.Write)) {
                var buffer = new byte[2 * 1024 * 1024];
                var readPtr = Marshal.AllocHGlobal(4);
                try {
                    while (true) {
                        Marshal.ThrowExceptionForHR(stream.Read(buffer, buffer.Length, readPtr));
                        int read = Marshal.ReadInt32(readPtr);
                        if (read <= 0) break;
                        file.Write(buffer, 0, read);
                    }
                } finally {
                    Marshal.FreeHGlobal(readPtr);
                }
            }
        }
    }
}
"@
}

$fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fsi.VolumeName = "BCUVMBTSTRP"
$fsi.FileSystemsToCreate = 3   # ISO9660 + Joliet (long filenames for .ps1/.py)
$fsi.Root.AddTree($StagingFolder, $false)
$result = $fsi.CreateResultImage()
[BlenderCuVm.IsoWriter]::WriteIStreamToFile($result.ImageStream, $ISOPath)
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($result) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($fsi) | Out-Null

if (-not (Test-Path $ISOPath) -or (Get-Item $ISOPath).Length -lt 64KB) {
    throw "ISO authoring failed or produced a suspiciously small image: $ISOPath"
}

$Hash = (Get-FileHash -Path $ISOPath -Algorithm SHA256).Hash
$SizeMB = [math]::Round((Get-Item $ISOPath).Length / 1MB, 2)
Write-Host "`nBootstrap ISO authored successfully:" -ForegroundColor Green
Write-Host ("  Path   : {0}" -f $ISOPath)
Write-Host ("  Size   : {0} MB" -f $SizeMB)
Write-Host ("  SHA256 : {0}" -f $Hash)
Write-Host "`nAttach it as a second DVD drive alongside the Windows 11 install ISO," -ForegroundColor Cyan
Write-Host "or run scripts\deploy_guest_os.ps1 to do the whole cutover in one command." -ForegroundColor Cyan
