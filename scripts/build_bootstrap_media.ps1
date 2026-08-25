<#
.SYNOPSIS
    Builds the secondary Unattended Bootstrap media for Blender-CU-VM.
    Packages autounattend.xml and guest setup scripts into a virtual drive/ISO.

.DESCRIPTION
    Creates an unattended bootstrap ISO/VHDX containing:
    - autounattend.xml
    - install_guest.ps1
    - setup_virtual_display.ps1
    - install_gpupv_guest.bat
    Attaches to the VM so Windows Setup runs 100% unattended.
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [string]$OutputDir = "C:\VMs\Blender-CU-VM\Bootstrap",
    [string]$ISOPath = "C:\VMs\Blender-CU-VM\Bootstrap\unattend.iso"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Building Unattended Bootstrap Media for $VMName ===" -ForegroundColor Cyan

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$StagingFolder = Join-Path $OutputDir "Staging"
if (Test-Path $StagingFolder) {
    Remove-Item -Path $StagingFolder -Recurse -Force | Out-Null
}
New-Item -ItemType Directory -Path $StagingFolder -Force | Out-Null

# 1. Copy autounattend.xml to root
Copy-Item -Path (Join-Path $ScriptDir "autounattend.xml") -Destination (Join-Path $StagingFolder "autounattend.xml") -Force
Write-Host "  + Injected autounattend.xml" -ForegroundColor Green

# 2. Copy setup scripts
$GuestScripts = @(
    (Join-Path $ProjectRoot "guest\install_guest.ps1"),
    (Join-Path $ScriptDir "setup_virtual_display.ps1"),
    (Join-Path $ProjectRoot "guest\guest_daemon.py"),
    (Join-Path $ProjectRoot "guest\screen_capture.py"),
    (Join-Path $ProjectRoot "guest\input_controller.py"),
    (Join-Path $ProjectRoot "guest\ui_automation.py"),
    (Join-Path $ProjectRoot "guest\video_recorder.py")
)

$GuestDest = Join-Path $StagingFolder "guest"
New-Item -ItemType Directory -Path $GuestDest -Force | Out-Null

foreach ($s in $GuestScripts) {
    if (Test-Path $s) {
        Copy-Item -Path $s -Destination $GuestDest -Force
        Write-Host "  + Injected $(Split-Path $s -Leaf)" -ForegroundColor DarkGray
    }
}

Write-Host "`nBootstrap payload staged at: $StagingFolder" -ForegroundColor Green
Write-Host "Ready to be attached to $VMName alongside Windows 11 installation ISO." -ForegroundColor Cyan
