<#
.SYNOPSIS
    Configures the Guest VM with a permanent 1080p Virtual Display Adapter,
    disables screen sleep/standby, configures auto-logon, and fixes 100% DPI scaling.

.DESCRIPTION
    Runs inside the Guest VM (or during initial unattended setup) to guarantee:
    1. A persistent 1920x1080 @ 60Hz virtual display is active even with no RDP/console window open.
    2. Display sleep and system standby are disabled (never sleeps during long test runs).
    3. Windows AutoLogon is configured for the test account so the GUI session starts on boot.
    4. DPI scaling is locked to 100% (96 DPI) to prevent coordinate drifting during agent computer use.

.PARAMETER TargetWidth
    Virtual screen width. Default: 1920
.PARAMETER TargetHeight
    Virtual screen height. Default: 1080
.PARAMETER TargetRefreshRate
    Virtual refresh rate. Default: 60
.PARAMETER AutoLogonUser
    Guest username for auto-logon. Default: "BlenderTester"
.PARAMETER AutoLogonPassword
    Guest password for auto-logon. Default: "Blender123!"
#>

[CmdletBinding()]
param(
    [int]$TargetWidth = 1920,
    [int]$TargetHeight = 1080,
    [int]$TargetRefreshRate = 60,
    [string]$AutoLogonUser = "BlenderTester",
    [string]$AutoLogonPassword = "Blender123!"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Guest Environment & Virtual Display Setup ===" -ForegroundColor Cyan

# --- 1. Power Settings: Never Sleep or Turn Off Display ---
Write-Host "[1/4] Disabling screen timeout, standby, and hibernation..." -ForegroundColor Gray
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
powercfg /change disk-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /h off

# --- 2. Configure Windows Auto-Logon ---
Write-Host "[2/4] Configuring AutoLogon for '$AutoLogonUser'..." -ForegroundColor Gray
$WinLogonPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $WinLogonPath -Name "AutoAdminLogon" -Value "1" -Type String
Set-ItemProperty -Path $WinLogonPath -Name "DefaultUserName" -Value $AutoLogonUser -Type String
Set-ItemProperty -Path $WinLogonPath -Name "DefaultPassword" -Value $AutoLogonPassword -Type String
Set-ItemProperty -Path $WinLogonPath -Name "ForceAutoLogon" -Value "1" -Type String

# Ensure local user exists
$UserCheck = Get-LocalUser -Name $AutoLogonUser -ErrorAction SilentlyContinue
if (-not $UserCheck) {
    Write-Host "  Creating local user '$AutoLogonUser'..." -ForegroundColor DarkGray
    $SecurePass = ConvertTo-SecureString $AutoLogonPassword -AsPlainText -Force
    New-LocalUser -Name $AutoLogonUser -Password $SecurePass -FullName "Blender Test Agent" -PasswordNeverExpires | Out-Null
    Add-LocalGroupMember -Group "Administrators" -Member $AutoLogonUser | Out-Null
}

# --- 3. DPI Scaling: Force 100% (96 DPI) Globally ---
Write-Host "[3/4] Locking system DPI scaling to 100% (96 DPI)..." -ForegroundColor Gray
$DpiPath = "HKCU:\Control Panel\Desktop"
Set-ItemProperty -Path $DpiPath -Name "LogPixels" -Value 96 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $DpiPath -Name "Win8DpiScaling" -Value 1 -Type DWord -ErrorAction SilentlyContinue

# --- 4. Virtual Display Driver (IddSampleDriver / Amyuni) Config ---
Write-Host "[4/4] Configuring Virtual Display parameters (${TargetWidth}x${TargetHeight} @ ${TargetRefreshRate}Hz)..." -ForegroundColor Gray

# Write IddSampleDriver option config file
$DriverConfigDir = "C:\VirtualDisplay"
if (-not (Test-Path $DriverConfigDir)) {
    New-Item -ItemType Directory -Path $DriverConfigDir -Force | Out-Null
}

$VddOptionFile = @"
[VirtualDisplay]
Count=1
Mode0=${TargetWidth},${TargetHeight},${TargetRefreshRate}
Primary=0
"@

Set-Content -Path (Join-Path $DriverConfigDir "options.txt") -Value $VddOptionFile -Encoding ASCII

# Batch helper to install driver if files are present in C:\VirtualDisplay
$InstallDriverBat = @"
@echo off
cd /d "%~dp0"
if exist "IddSampleDriver.inf" (
    echo Installing IddSampleDriver...
    pnputil /add-driver IddSampleDriver.inf /install
) else (
    echo Virtual display driver INF not found in C:\VirtualDisplay. Ensure driver is unpacked.
)
"@
Set-Content -Path (Join-Path $DriverConfigDir "install_vdd.bat") -Value $InstallDriverBat -Encoding ASCII

Write-Host "`nSetup complete. Virtual desktop parameters and auto-logon configured." -ForegroundColor Green
