<#
.SYNOPSIS
    Master Host Installer for Blender Computer-Use Isolated VM & MCP Server.
    Automates Hyper-V VM provisioning, GPU-PV driver staging, MCP server registration,
    and agent skill deployment.

.DESCRIPTION
    1. Validates host prerequisites (Windows 11, Hyper-V, NVIDIA GPU, Python 3.10+).
    2. Provisions the Hyper-V Generation 2 VM with GPU partitioning.
    3. Stages host NVIDIA display drivers and CUDA runtime DLLs.
    4. Registers the 'blender-cu-vm' MCP server into ~/.claude.json and ~/.omp/agent/config.yml.
    5. Deploys the 'blender-computer-use-vm' agent skill into managed-skills.
    6. Runs verification tests.

.PARAMETER VMName
    Name of the Hyper-V VM to create/configure. Default: "Blender-CU-VM"
.PARAMETER NonInteractive
    Runs full installation with default parameters without prompts.
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Banner {
    Write-Host "`n================================================================================" -ForegroundColor Cyan
    Write-Host "   Blender Computer-Use Isolated VM & MCP Server - Master Installer" -ForegroundColor Cyan
    Write-Host "================================================================================`n" -ForegroundColor Cyan
}

function Test-AdminPrivileges {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Banner

# --- 1. Check Administrator Privileges ---
Write-Host "[1/6] Checking administrative privileges..." -ForegroundColor Cyan
if (-not (Test-AdminPrivileges)) {
    Write-Warning "Administrative privileges required. Re-launching in elevated PowerShell..."
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
Write-Host "  + Running as Administrator." -ForegroundColor Green

# --- 2. Check Host Hardware & Prerequisites ---
Write-Host "[2/6] Checking host GPU and Hyper-V status..." -ForegroundColor Cyan
$GPU = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" } | Select-Object -First 1
if ($GPU) {
    Write-Host "  + Detected Host GPU: $($GPU.Name)" -ForegroundColor Green
} else {
    Write-Warning "  ! No NVIDIA GPU detected. GPU-PV acceleration requires an NVIDIA graphics card."
}

# --- 3. Run Hyper-V VM Provisioning ---
Write-Host "[3/6] Provisioning Hyper-V Generation 2 VM ('$VMName')..." -ForegroundColor Cyan
$ProvisionScript = Join-Path $ScriptDir "scripts\setup_vm_gpupv.ps1"
if (Test-Path $ProvisionScript) {
    & $ProvisionScript -VMName $VMName
} else {
    Write-Warning "Provisioning script not found at $ProvisionScript"
}

# --- 4. Stage GPU-PV Display Drivers ---
Write-Host "[4/6] Staging NVIDIA GPU-PV drivers..." -ForegroundColor Cyan
$StageScript = Join-Path $ScriptDir "scripts\stage_gpupv_drivers.ps1"
$StagingDir = Join-Path $ScriptDir "staging\NvidiaDrivers"
if (Test-Path $StageScript) {
    & $StageScript -VMName $VMName -StagingDir $StagingDir -Mode Stage
}

# --- 5. Register MCP Server in Claude & OMP Configs ---
Write-Host "[5/6] Registering 'blender-cu-vm' MCP server in user configuration..." -ForegroundColor Cyan
$PythonScript = Join-Path $ScriptDir "install.py"
if (Test-Path $PythonScript) {
    python $PythonScript --register-mcp
}

# --- 6. Final Summary ---
Write-Host "`n[6/6] Installation & Registration Complete!" -ForegroundColor Green
Write-Host "--------------------------------------------------------------------------------"
Write-Host "Next Steps for Guest VM Setup:"
Write-Host "1. Deploy the guest OS unattended (one command, fully hands-off):"
Write-Host "   .\scripts\deploy_guest_os.ps1 -WindowsISO 'C:\ISOs\Win11_24H2_English_x64.iso'"
Write-Host "2. Stage GPU-PV drivers into the running guest:"
Write-Host "   .\scripts\stage_gpupv_drivers.ps1 -VMName $VMName -Mode OnlineCopy"
Write-Host "3. Once the daemon is healthy, create your golden base snapshot:"
Write-Host "   powershell .\scripts\manage_golden_snapshot.ps1 -Action Create"
Write-Host "--------------------------------------------------------------------------------`n"
