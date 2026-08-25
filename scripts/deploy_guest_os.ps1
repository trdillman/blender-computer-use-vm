<#
.SYNOPSIS
    One-command unattended guest OS deployment for Blender-CU-VM.

.DESCRIPTION
    Full cutover pipeline, start to finish:
      1. Validates prerequisites (admin, Hyper-V module, Windows 11 ISO).
      2. Ensures the VM exists (invokes setup_vm_gpupv.ps1 if missing).
      3. Builds the unattended bootstrap ISO (build_bootstrap_media.ps1).
      4. Attaches the Windows 11 ISO + bootstrap ISO as DVD drives and sets
         the firmware first-boot device to the Windows install DVD.
      5. Starts the VM (Windows Setup runs fully unattended via autounattend.xml;
         after OOBE auto-logon the FirstLogonCommand chain runs bootstrap.cmd,
         which runs guest\install_guest.ps1: static IP + daemon).
      6. Optionally polls the guest daemon health endpoint until reachable.

    Watch the unattended install graphically with:
        vmconnect.exe localhost Blender-CU-VM

.EXAMPLE
    .\deploy_guest_os.ps1 -WindowsISO "C:\ISOs\Win11_24H2_English_x64.iso"

.EXAMPLE
    .\deploy_guest_os.ps1 -WindowsISO "C:\ISOs\Win11.iso" -SkipHealthWait
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WindowsISO,
    [string]$VMName = "Blender-CU-VM",
    [int]$HealthWaitMinutes = 90,
    [int]$PollIntervalSeconds = 30,
    [switch]$SkipHealthWait
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GuestHealthUrl = "http://192.168.122.100:8000/health"

function Test-AdminPrivileges {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Host "=== Blender-CU-VM Unattended Guest OS Deployment ===" -ForegroundColor Cyan

# --- 1. Prerequisites --------------------------------------------------------
if (-not (Test-AdminPrivileges)) { throw "Administrative privileges required. Run from an elevated PowerShell." }
if (-not (Get-Command Start-VM -ErrorAction SilentlyContinue)) { throw "Hyper-V module not available. Enable the Hyper-V role first." }
if (-not (Test-Path $WindowsISO)) { throw "Windows 11 installation ISO not found at: $WindowsISO" }
if ((Get-Item $WindowsISO).Extension -ne ".iso") { throw "Expected an .iso file, got: $WindowsISO" }
Write-Host "  + Prerequisites OK (admin, Hyper-V, ISO present)." -ForegroundColor Green

# --- 2. Ensure VM exists -----------------------------------------------------
$VM = Get-VM -Name $VMName -ErrorAction SilentlyContinue
if (-not $VM) {
    Write-Host "  + VM '$VMName' not found; provisioning hardware first..." -ForegroundColor Yellow
    & (Join-Path $ScriptDir "setup_vm_gpupv.ps1") -VMName $VMName
    $VM = Get-VM -Name $VMName -ErrorAction Stop
}

# --- 3. Build bootstrap ISO ---------------------------------------------------
Write-Host "`n[3/6] Building unattended bootstrap ISO..." -ForegroundColor Cyan
& (Join-Path $ScriptDir "build_bootstrap_media.ps1") -VMName $VMName
$BootstrapISO = "C:\VMs\Blender-CU-VM\Bootstrap\unattend.iso"
if (-not (Test-Path $BootstrapISO)) { throw "Bootstrap ISO missing after build: $BootstrapISO" }

# --- 4. Attach DVD drives -----------------------------------------------------
Write-Host "`n[4/6] Attaching installation media to '$VMName'..." -ForegroundColor Cyan
$DvdDrives = @(Get-VMDvdDrive -VMName $VMName)
if ($DvdDrives.Count -ge 2) {
    Set-VMDvdDrive -VMName $VMName -ControllerNumber $DvdDrives[0].ControllerNumber -ControllerLocation $DvdDrives[0].ControllerLocation -Path $WindowsISO
    Set-VMDvdDrive -VMName $VMName -ControllerNumber $DvdDrives[1].ControllerNumber -ControllerLocation $DvdDrives[1].ControllerLocation -Path $BootstrapISO
} elseif ($DvdDrives.Count -eq 1) {
    Set-VMDvdDrive -VMName $VMName -ControllerNumber $DvdDrives[0].ControllerNumber -ControllerLocation $DvdDrives[0].ControllerLocation -Path $WindowsISO
    Add-VMDvdDrive -VMName $VMName -Path $BootstrapISO
} else {
    Add-VMDvdDrive -VMName $VMName -Path $WindowsISO
    Add-VMDvdDrive -VMName $VMName -Path $BootstrapISO
}
$InstallDvd = Get-VMDvdDrive -VMName $VMName | Where-Object { $_.Path -eq $WindowsISO } | Select-Object -First 1
Write-Host "  + Windows ISO  : $($InstallDvd.ControllerNumber):$($InstallDvd.ControllerLocation)" -ForegroundColor Green
Write-Host "  + Bootstrap ISO: $BootstrapISO" -ForegroundColor Green

# --- 5. Boot order + start ----------------------------------------------------
Write-Host "`n[5/6] Setting DVD as first boot device and starting VM..." -ForegroundColor Cyan
if ($VM.State -ne "Off") {
    Write-Host "  VM is '$($VM.State)'; saving/stopping for boot-order change..." -ForegroundColor Yellow
    if ($VM.State -eq "Running") { Stop-VM -Name $VMName -Force -TurnOff }
}
Set-VMFirmware -VMName $VMName -FirstBootDevice $InstallDvd -EnableSecureBoot On -SecureBootTemplate "MicrosoftWindows"
Start-VM -Name $VMName
Write-Host "  + VM started. Windows Setup is running unattended." -ForegroundColor Green
Write-Host "  + Watch graphically:  vmconnect.exe localhost $VMName" -ForegroundColor Cyan

if ($SkipHealthWait) {
    Write-Host "`n=== Deployment launched (-SkipHealthWait). Poll manually with: ===" -ForegroundColor Cyan
    Write-Host "    python .\scripts\check_guest_health.py" -ForegroundColor Cyan
    return
}

# --- 6. Poll guest daemon health ----------------------------------------------
Write-Host "`n[6/6] Waiting for guest daemon at $GuestHealthUrl" -ForegroundColor Cyan
Write-Host "      (unattended Win11 install typically takes 20-45 min in a VM)..." -ForegroundColor Gray
$HealthScript = Join-Path $ScriptDir "check_guest_health.py"
$Deadline = (Get-Date).AddMinutes($HealthWaitMinutes)
$Attempt = 0
while ((Get-Date) -lt $Deadline) {
    $Attempt++
    $Result = & python $HealthScript --url "http://192.168.122.100:8000" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n  + Guest daemon is HEALTHY after $Attempt poll(s)." -ForegroundColor Green
        Write-Host "`n=== Deployment complete. Next: create the golden snapshot ===" -ForegroundColor Green
        Write-Host "    .\scripts\manage_golden_snapshot.ps1 -VMName $VMName -SnapshotName golden_base -Action Create" -ForegroundColor Cyan
        return
    }
    Write-Host "  [$Attempt] not ready (next poll in ${PollIntervalSeconds}s)..." -ForegroundColor DarkGray
    Start-Sleep -Seconds $PollIntervalSeconds
}
throw "Guest daemon did not become healthy within $HealthWaitMinutes minutes. Inspect the VM console (vmconnect.exe localhost $VMName) and C:\BlenderCU guest logs."
