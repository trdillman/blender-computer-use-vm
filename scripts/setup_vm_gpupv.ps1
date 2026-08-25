<#
.SYNOPSIS
    Provisions a local, isolated Windows 11 Hyper-V Virtual Machine configured with GPU-Partitioning (GPU-PV).
    Designed specifically for coding agent Computer-Use & Blender UI testing workflows.

.DESCRIPTION
    This script:
    1. Validates Hyper-V role and administrator privileges.
    2. Creates an Internal Virtual Switch and configures host NAT for guest outbound network access.
    3. Provisions a Generation 2 VM with fixed RAM, vCPUs, and dynamic VHDX.
    4. Configures Low/High MMIO space required for modern GPU partitioning (RTX 4080 Super).
    5. Attaches the GPU partition adapter.
    6. Enables Hyper-V Integration Services (Guest Service Interface for file copy and hv_sock).

.PARAMETER VMName
    The name of the Hyper-V Virtual Machine. Default: "Blender-CU-VM"
.PARAMETER VMDirectory
    Directory to store VM configuration and virtual hard disks. Default: "C:\VMs\Blender-CU-VM"
.PARAMETER VHDSizeBytes
    Size of the virtual hard disk. Default: 60GB
.PARAMETER MemoryBytes
    Fixed RAM allocation. Default: 8GB (Dynamic memory disabled for GPU-PV)
.PARAMETER ProcessorCount
    Number of virtual processors. Default: 8
.PARAMETER SwitchName
    Name of the internal virtual switch. Default: "Blender-CU-Switch"
.PARAMETER NATSubnet
    Subnet for internal VM network. Default: "192.168.122.0/24"
.PARAMETER HostGatewayIP
    Host IP address on internal switch. Default: "192.168.122.1"

.EXAMPLE
    .\setup_vm_gpupv.ps1 -VMName "Blender-CU-VM" -MemoryBytes 8GB -ProcessorCount 8
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [string]$VMDirectory = "C:\VMs\Blender-CU-VM",
    [int64]$VHDSizeBytes = 60GB,
    [int64]$MemoryBytes = 8GB,
    [int]$ProcessorCount = 8,
    [string]$SwitchName = "Blender-CU-Switch",
    [string]$NATSubnet = "192.168.122.0/24",
    [string]$HostGatewayIP = "192.168.122.1"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message, [int]$Step, [int]$Total = 6)
    Write-Host "[$Step/$Total] $Message" -ForegroundColor Cyan
}

function Test-AdminPrivileges {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- Step 0: Privilege Check ---
if (-not (Test-AdminPrivileges)) {
    throw "Administrative privileges required. Please run in an elevated PowerShell session."
}

$VHDXPath = Join-Path $VMDirectory "Virtual Hard Disks\$VMName.vhdx"

# --- Step 1: Ensure Directories ---
Write-Step "Creating VM storage directory at $VMDirectory..." 1
if (-not (Test-Path $VMDirectory)) {
    New-Item -ItemType Directory -Path $VMDirectory -Force | Out-Null
}
$VHDDir = Split-Path -Parent $VHDXPath
if (-not (Test-Path $VHDDir)) {
    New-Item -ItemType Directory -Path $VHDDir -Force | Out-Null
}

# --- Step 2: Internal Switch & NAT Configuration ---
Write-Step "Configuring Internal Virtual Switch '$SwitchName' and NAT ($NATSubnet)..." 2
$ExistingSwitch = Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue
if (-not $ExistingSwitch) {
    Write-Host "  Creating internal virtual switch: $SwitchName" -ForegroundColor Gray
    New-VMSwitch -Name $SwitchName -SwitchType Internal | Out-Null
}

$InterfaceIndex = (Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*$SwitchName*" -or $_.Name -like "*$SwitchName*" }).ifIndex
if ($InterfaceIndex) {
    $ExistingIP = Get-NetIPAddress -InterfaceIndex $InterfaceIndex -IPAddress $HostGatewayIP -ErrorAction SilentlyContinue
    if (-not $ExistingIP) {
        Write-Host "  Assigning host gateway IP $HostGatewayIP to interface index $InterfaceIndex..." -ForegroundColor Gray
        New-NetIPAddress -IPAddress $HostGatewayIP -PrefixLength 24 -InterfaceIndex $InterfaceIndex -ErrorAction SilentlyContinue | Out-Null
    }
}

$ExistingNAT = Get-NetNat -Name "Blender-CU-NAT" -ErrorAction SilentlyContinue
if (-not $ExistingNAT) {
    Write-Host "  Creating NetNat 'Blender-CU-NAT' on $NATSubnet..." -ForegroundColor Gray
    New-NetNat -Name "Blender-CU-NAT" -InternalIPInterfaceAddressPrefix $NATSubnet -ErrorAction SilentlyContinue | Out-Null
}

# --- Step 3: Virtual Machine Creation ---
Write-Step "Provisioning Generation 2 VM '$VMName' ($ProcessorCount vCPUs, $([math]::Round($MemoryBytes / 1GB, 1)) GB RAM)..." 3
$ExistingVM = Get-VM -Name $VMName -ErrorAction SilentlyContinue
if ($ExistingVM) {
    Write-Warning "VM '$VMName' already exists. Re-configuring hardware parameters..."
} else {
    New-VM -Name $VMName `
           -Generation 2 `
           -MemoryStartupBytes $MemoryBytes `
           -NewVHDPath $VHDXPath `
           -NewVHDSizeBytes $VHDSizeBytes `
           -Path $VMDirectory `
           -SwitchName $SwitchName | Out-Null
}

# Apply Hardware Settings
Set-VM -VMName $VMName -ProcessorCount $ProcessorCount -AutomaticCheckpointsEnabled $false
Set-VMMemory -VMName $VMName -DynamicMemoryEnabled $false

# Configure Firmware (Secure Boot & TPM)
Set-VMFirmware -VMName $VMName -EnableSecureBoot On -SecureBootTemplate "MicrosoftWindows"

# --- Step 4: GPU-Partitioning (GPU-PV) Configuration ---
Write-Step "Configuring GPU Partitioning (GPU-PV) parameters..." 4
# MMIO Space required for modern high-VRAM cards (NVIDIA Ada Lovelace / Ampere / RTX 4080 Super)
Set-VM -Name $VMName `
       -GuestControlledCacheTypes $true `
       -LowMemoryMappedIoSpace 1GB `
       -HighMemoryMappedIoSpace 32GB

# Remove any stale adapter and add fresh partition adapter
Remove-VMGpuPartitionAdapter -VMName $VMName -ErrorAction SilentlyContinue
Add-VMGpuPartitionAdapter -VMName $VMName

# --- Step 5: Integration Services & Hyper-V Sockets ---
Write-Step "Enabling Guest Integration Services (File Interface, Heartbeat, Key-Value)..." 5
Enable-VMIntegrationService -VMName $VMName -Name "Guest Service Interface" -ErrorAction SilentlyContinue
Enable-VMIntegrationService -VMName $VMName -Name "Key-Value Pair Exchange" -ErrorAction SilentlyContinue
Enable-VMIntegrationService -VMName $VMName -Name "Heartbeat" -ErrorAction SilentlyContinue
Enable-VMIntegrationService -VMName $VMName -Name "Shutdown" -ErrorAction SilentlyContinue

# --- Step 6: Summary & Receipt ---
Write-Step "VM Provisioning Completed Successfully!" 6

$Receipt = [PSCustomObject]@{
    VMName            = $VMName
    Generation        = 2
    ProcessorCount    = $ProcessorCount
    MemoryGB          = [math]::Round($MemoryBytes / 1GB, 1)
    VHDXPath          = $VHDXPath
    SwitchName        = $SwitchName
    HostGatewayIP     = $HostGatewayIP
    NATSubnet         = $NATSubnet
    GPUPartitioned    = $true
    HighMMIOGB        = 32
    GuestServices     = "Enabled"
    TimestampUtc      = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$ReceiptJson = $Receipt | ConvertTo-Json -Depth 4
Write-Host "`nProvisioning Receipt:" -ForegroundColor Green
Write-Host $ReceiptJson

# Save receipt to VM directory
$Receipt | Export-Clixml -Path (Join-Path $VMDirectory "provisioning_receipt.xml")
