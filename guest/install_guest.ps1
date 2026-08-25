<#
.SYNOPSIS
    One-Command Setup Script for Guest VM.
    Configures static internal-switch IP, NVIDIA GPU-PV drivers, 1080p Virtual
    Display Adapter, AutoLogon startup task, and launches the Guest Agent Daemon.

.DESCRIPTION
    Designed to run inside the Guest Windows 11 VM as Administrator, directly
    from the read-only bootstrap DVD (autonomous FirstLogonCommand chain) or
    from an already-staged local copy:

        powershell -ExecutionPolicy Bypass -File .\install_guest.ps1

    Behavior:
    1. If launched from removable media (bootstrap DVD), mirrors the payload
       to C:\BlenderCU\guest first and re-launches from there so the startup
       shortcut and daemon never depend on a DVD drive letter.
    2. Assigns static IP 192.168.122.100 (the internal Blender-CU-Switch has
       NO DHCP server - without this the guest is unreachable from the host).
    3. Installs staged GPU-PV drivers if present at C:\Temp\NvidiaDrivers.
    4. Configures the 1080p virtual display adapter.
    5. Registers a hidden daemon startup shortcut + starts the daemon now.
#>

[CmdletBinding()]
param(
    [string]$BlenderPath = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    [int]$DaemonPort = 8000,
    [string]$GuestIP = "192.168.122.100",
    [string]$GatewayIP = "192.168.122.1",
    [string]$DnsServer = "1.1.1.1",
    [string]$TargetRoot = "C:\BlenderCU",
    [string]$DaemonSecret = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- HOST-SAFETY GUARD ------------------------------------------------------
# Reconfigures network adapters, Winlogon auto-logon, and startup tasks.
# Guest-VM-only by design; refuse on any other machine.
if ($env:COMPUTERNAME -ne "BLENDER-CU-VM" -and $env:BLENDER_CU_ALLOW_HOST -ne "1") {
    throw "SAFETY ABORT: '$($env:COMPUTERNAME)' is not the guest VM (BLENDER-CU-VM). install_guest.ps1 must run inside the guest only (set BLENDER_CU_ALLOW_HOST=1 to override)."
}

function Write-Step {
    param([string]$Message, [int]$Step, [int]$Total = 5)
    Write-Host "[$Step/$Total] $Message" -ForegroundColor Cyan
}

# --- Step 0: Relocate payload off removable media --------------------------
Write-Step "Preparing guest payload..." 0
$TargetGuestDir = Join-Path $TargetRoot "guest"
if ($ScriptDir -ne $TargetGuestDir) {
    Write-Host "  Copying payload from '$ScriptDir' to '$TargetGuestDir' (source may be read-only DVD)..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path $TargetGuestDir -Force | Out-Null
    Copy-Item -Path (Join-Path $ScriptDir "*") -Destination $TargetGuestDir -Recurse -Force
    Write-Host "  Re-launching installer from local copy..." -ForegroundColor Gray
    $localInstaller = Join-Path $TargetGuestDir "install_guest.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $localInstaller `
        -BlenderPath $BlenderPath -DaemonPort $DaemonPort -GuestIP $GuestIP `
        -GatewayIP $GatewayIP -DnsServer $DnsServer -TargetRoot $TargetRoot `
        -DaemonSecret $DaemonSecret
    exit $LASTEXITCODE
}
$ScriptDir = $TargetGuestDir

# --- Step 1: Static IP on internal switch (NO DHCP exists) ------------------
Write-Step "Assigning static IP $GuestIP (gateway $GatewayIP)..." 1
$Adapter = Get-NetAdapter -Physical | Where-Object { $_.Status -eq "Up" } | Sort-Object ifIndex | Select-Object -First 1
if (-not $Adapter) {
    Write-Warning "No active network adapter found; skipping static IP assignment."
} else {
    # Idempotent: clear any stale IPv4 config on the adapter, then apply ours.
    Get-NetIPAddress -InterfaceIndex $Adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -ne $GuestIP -and $_.IPAddress -notlike "169.254.*" } |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    $Already = Get-NetIPAddress -InterfaceIndex $Adapter.ifIndex -IPAddress $GuestIP -ErrorAction SilentlyContinue
    if (-not $Already) {
        New-NetIPAddress -InterfaceIndex $Adapter.ifIndex -IPAddress $GuestIP -PrefixLength 24 -DefaultGateway $GatewayIP | Out-Null
    }
    Set-DnsClientServerAddress -InterfaceIndex $Adapter.ifIndex -ServerAddresses $DnsServer
    Write-Host "  + Static IP bound to '$($Adapter.Name)' (ifIndex $($Adapter.ifIndex))." -ForegroundColor Green
}

# --- Step 2: Install GPU-PV drivers if staged -------------------------------
Write-Step "Installing staged GPU-PV display drivers..." 2
$DriverBat = "C:\Temp\NvidiaDrivers\install_gpupv_guest.bat"
if (Test-Path $DriverBat) {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$DriverBat`"" -Wait -NoNewWindow
    Write-Host "  + GPU-PV drivers installed." -ForegroundColor Green
} else {
    Write-Host "  ! Staged drivers not found at $DriverBat (skipping; run scripts\stage_gpupv_drivers.ps1 -Mode OnlineCopy from the host)." -ForegroundColor Yellow
}

# --- Step 3: Configure Virtual Display & resolution lock -------------------
Write-Step "Configuring 1080p virtual display, DPI scaling, and Auto-Logon..." 3
# Bootstrap media layout puts setup_virtual_display.ps1 BESIDE this script in
# guest\; the legacy repo layout uses <repo>\scripts\. Check both.
$VddScript = Join-Path $ScriptDir "setup_virtual_display.ps1"
if (-not (Test-Path $VddScript)) {
    $VddScript = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\setup_virtual_display.ps1"
}
if (Test-Path $VddScript) {
    & $VddScript -TargetWidth 1920 -TargetHeight 1080
} else {
    Write-Host "  ! setup_virtual_display.ps1 not found (checked beside script and repo scripts\); skipping." -ForegroundColor Yellow
}

# --- Step 4: Register hidden daemon startup + launch ------------------------
Write-Step "Registering guest agent daemon startup task..." 4

# Resolve the daemon auth secret BEFORE launching anything. Precedence:
#   explicit -DaemonSecret param > daemon_secret.txt staged beside this script
#   (bootstrap ISO payload) > already-persisted Machine env (rerun-safe)
#   > freshly generated GUID. Empty secret means auth disabled (dev mode).
$SecretFile = Join-Path $ScriptDir "daemon_secret.txt"
if (-not $DaemonSecret -and (Test-Path $SecretFile)) {
    $DaemonSecret = (Get-Content -Path $SecretFile -Raw).Trim()
}
if (-not $DaemonSecret) {
    $DaemonSecret = [Environment]::GetEnvironmentVariable("GUEST_DAEMON_SECRET", "Machine")
}
if ($DaemonSecret -and $DaemonSecret -notmatch '^[A-Za-z0-9_.\-]{16,128}$') {
    Write-Warning "Daemon secret failed charset validation; generating a fresh one."
    $DaemonSecret = ""
}
if (-not $DaemonSecret) {
    $DaemonSecret = [Guid]::NewGuid().ToString("N")
}
# Persist Machine-wide so the Startup shortcut's hidden daemon inherits it on
# every logon; also export into THIS session for the immediate launch below.
[Environment]::SetEnvironmentVariable("GUEST_DAEMON_SECRET", $DaemonSecret, "Machine")
$env:GUEST_DAEMON_SECRET = $DaemonSecret
Write-Host "  + Daemon auth ENABLED (GUEST_DAEMON_SECRET persisted Machine-wide)." -ForegroundColor Green

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning "python.exe not on PATH in guest. Install Python 3.10+ (ticked 'Add to PATH') before the daemon can run."
}
$DaemonScript = Join-Path $ScriptDir "guest_daemon.py"
$VbsLauncher = Join-Path $ScriptDir "start_daemon_hidden.vbs"
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python """ & "$DaemonScript" & """", 0, False
"@
Set-Content -Path $VbsLauncher -Value $VbsContent -Encoding ASCII

$StartupFolder = [System.Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupFolder "BlenderCUDaemon.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = "`"$VbsLauncher`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Save()
Write-Host "  + Registered startup shortcut at: $ShortcutPath" -ForegroundColor Green

# --- Step 5: Verify display + start the daemon ------------------------------
Write-Step "Verifying display and starting daemon on port $DaemonPort..." 5
try {
    Add-Type -AssemblyName System.Windows.Forms
    $Width = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width
    $Height = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height
    Write-Host "  + Primary Screen Resolution: ${Width}x${Height}" -ForegroundColor Green
    if ($Width -ne 1920 -or $Height -ne 1080) {
        Write-Host "  ! Resolution not locked to 1920x1080 yet (virtual display adapter may still be installing)." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ! Display query unavailable in this session context: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "`n=== Guest Setup Complete! Starting daemon on port $DaemonPort... ===" -ForegroundColor Green
Start-Process python -ArgumentList "`"$DaemonScript`"" -WorkingDirectory $ScriptDir
Write-Host "Daemon launched from $DaemonScript. Health endpoint: http://${GuestIP}:$DaemonPort/health" -ForegroundColor Green
