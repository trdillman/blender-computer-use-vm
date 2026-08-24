<#
.SYNOPSIS
    One-Command Setup Script for Guest VM.
    Configures NVIDIA GPU-PV drivers, 1080p Virtual Display Adapter,
    AutoLogon, and starts the Guest Agent Daemon.

.DESCRIPTION
    Run this script inside the Guest Windows 11 VM as Administrator:
    powershell -ExecutionPolicy Bypass -File .\install_guest.ps1
#>

[CmdletBinding()]
param(
    [string]$BlenderPath = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    [int]$DaemonPort = 8000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "   Blender Computer-Use Guest VM - One-Command Environment Setup" -ForegroundColor Cyan
Write-Host "================================================================================`n" -ForegroundColor Cyan

# 1. Install GPU-PV Drivers if staged
Write-Host "[1/4] Installing staged GPU-PV Display Drivers..." -ForegroundColor Cyan
$DriverBat = "C:\Temp\NvidiaDrivers\install_gpupv_guest.bat"
if (Test-Path $DriverBat) {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$DriverBat`"" -Wait -NoNewWindow
    Write-Host "  + GPU-PV Drivers installed." -ForegroundColor Green
} else {
    Write-Host "  ! Staged drivers not found at $DriverBat (skipping or already installed)." -ForegroundColor Yellow
}

# 2. Configure Virtual Display & Auto-Logon
Write-Host "[2/4] Configuring 1080p Virtual Display, DPI scaling, and Auto-Logon..." -ForegroundColor Cyan
$VddScript = Join-Path (Split-Path -Parent $ScriptDir) "scripts\setup_virtual_display.ps1"
if (Test-Path $VddScript) {
    & $VddScript -TargetWidth 1920 -TargetHeight 1080
}

# 3. Create Windows Startup Shortcut for Guest Daemon
Write-Host "[3/4] Registering Guest Agent Daemon startup task..." -ForegroundColor Cyan
$StartupFolder = [System.Environment]::GetFolderPath('Startup')
$DaemonScript = Join-Path $ScriptDir "guest_daemon.py"

$VbsLauncher = Join-Path $ScriptDir "start_daemon_hidden.vbs"
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """python"" """ & "$DaemonScript" & """", 0, False
"@
Set-Content -Path $VbsLauncher -Value $VbsContent -Encoding ASCII

$ShortcutPath = Join-Path $StartupFolder "BlenderCUDaemon.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = "`"$VbsLauncher`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Save()
Write-Host "  + Registered Startup shortcut at: $ShortcutPath" -ForegroundColor Green

# 4. Verification
Write-Host "[4/4] Verifying display and Python environment..." -ForegroundColor Cyan
$Width = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width
$Height = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height
Write-Host "  + Primary Screen Resolution: ${Width}x${Height}" -ForegroundColor Green

Write-Host "`n=== Guest Setup Complete! Starting Daemon on port $DaemonPort... ===" -ForegroundColor Green
Start-Process python -ArgumentList "`"$DaemonScript`"" -WorkingDirectory $ScriptDir
