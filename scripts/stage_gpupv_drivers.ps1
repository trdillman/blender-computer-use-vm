<#
.SYNOPSIS
    Extracts, packages, and stages NVIDIA GPU-PV drivers from host to guest VM.
    Enables hardware-accelerated DirectX, OpenGL, Vulkan, and CUDA/OptiX inside the Hyper-V VM.

.DESCRIPTION
    1. Identifies the active NVIDIA display driver store on the Windows 11 host.
    2. Collects critical CUDA, OptiX, NVENC, and Direct3D runtime user-mode driver DLLs.
    3. Supports:
       - Mode 'Stage': Packages driver files into a clean staging folder with guest installer script.
       - Mode 'MountVHD': Mounts offline VHDX, injects HostDriverStore, and dismounts.
       - Mode 'OnlineCopy': Uses Hyper-V Copy-VMFile integration to inject drivers into live VM.

.PARAMETER VMName
    Target Hyper-V VM name. Default: "Blender-CU-VM"
.PARAMETER VHDXPath
    Path to guest VHDX file (for offline injection).
.PARAMETER StagingDir
    Host directory to stage driver package. Default: "C:\VMs\Blender-CU-VM\Staging\NvidiaDrivers"
.PARAMETER Mode
    Operation mode: "Stage", "MountVHD", or "OnlineCopy". Default: "Stage"
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [string]$VHDXPath = "C:\VMs\Blender-CU-VM\Virtual Hard Disks\Blender-CU-VM.vhdx",
    [string]$StagingDir = "C:\VMs\Blender-CU-VM\Staging\NvidiaDrivers",
    [ValidateSet("Stage", "MountVHD", "OnlineCopy")]
    [string]$Mode = "Stage"
)

$ErrorActionPreference = "Stop"

# List of critical user-mode display, CUDA, and Vulkan driver DLLs from System32
$System32NvidiaDlls = @(
    "nvapi64.dll",
    "nvcuda.dll",
    "nvcuda_loader64.dll",
    "nvcuvid64.dll",
    "nvencodeapi64.dll",
    "nvfatbinaryLoader.dll",
    "nvinfo.pub",
    "nvml.dll",
    "nvopencl64.dll",
    "nvoptix.dll",
    "nvptxJitCompiler.dll",
    "nvrtum64.dll",
    "nvwgf2umx.dll",
    "nvwgf2umx_cfg.ini",
    "nvldumx.dll",
    "nvldumd.dll"
)

Write-Host "=== GPU-PV Driver Staging for $VMName (Mode: $Mode) ===" -ForegroundColor Cyan

# 1. Locate Host DriverStore folder dynamically from active GPU Controller
$DriverRepoBase = "C:\Windows\System32\DriverStore\FileRepository"
$ActiveDriver = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" } | Select-Object -First 1

if ($ActiveDriver -and $ActiveDriver.InstalledDisplayDrivers) {
    $FirstDriverPath = ($ActiveDriver.InstalledDisplayDrivers -split ',')[0]
    $ActiveDriverDir = Split-Path -Parent $FirstDriverPath
    $NvidiaDriverDirs = @(Get-Item -Path $ActiveDriverDir -ErrorAction SilentlyContinue)
} else {
    $NvidiaDriverDirs = Get-ChildItem -Path $DriverRepoBase -Filter "nv*.inf_amd64_*" -Directory -ErrorAction SilentlyContinue
}

if (-not $NvidiaDriverDirs) {
    throw "No NVIDIA display driver repository found in $DriverRepoBase. Ensure NVIDIA graphics driver is installed on host."
}

$LatestDriverDir = $NvidiaDriverDirs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Found Host NVIDIA Driver Repository: $($LatestDriverDir.FullName)" -ForegroundColor Green

# 2. Stage Drivers Locally
if (-not (Test-Path $StagingDir)) {
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
}

$HostDriverStoreDest = Join-Path $StagingDir "HostDriverStore\FileRepository\$($LatestDriverDir.Name)"
$System32Dest = Join-Path $StagingDir "System32"

New-Item -ItemType Directory -Path $HostDriverStoreDest -Force | Out-Null
New-Item -ItemType Directory -Path $System32Dest -Force | Out-Null

Write-Host "Copying FileRepository directory to staging..." -ForegroundColor Gray
Copy-Item -Path "$($LatestDriverDir.FullName)\*" -Destination $HostDriverStoreDest -Recurse -Force

Write-Host "Copying System32 runtime DLLs to staging..." -ForegroundColor Gray
foreach ($dll in $System32NvidiaDlls) {
    $srcPath = Join-Path "C:\Windows\System32" $dll
    if (Test-Path $srcPath) {
        Copy-Item -Path $srcPath -Destination $System32Dest -Force
        Write-Host "  + $dll" -ForegroundColor DarkGray
    }
}

# 3. Create Guest-Side Installer Script in Staging
$GuestInstallerBat = @"
@echo off
echo [GPU-PV Guest Setup] Installing NVIDIA GPU-PV Drivers...

:: 1. Create HostDriverStore directories
if not exist "C:\Windows\System32\HostDriverStore\FileRepository\$($LatestDriverDir.Name)" (
    mkdir "C:\Windows\System32\HostDriverStore\FileRepository\$($LatestDriverDir.Name)"
)

:: 2. Copy DriverStore contents
xcopy /s /e /y /q "%~dp0HostDriverStore\FileRepository\$($LatestDriverDir.Name)\*" "C:\Windows\System32\HostDriverStore\FileRepository\$($LatestDriverDir.Name)\"

:: 3. Copy System32 runtime binaries
xcopy /y /q "%~dp0System32\*" "C:\Windows\System32\"

echo [GPU-PV Guest Setup] Driver files staged. Verifying Device Manager...
powershell -Command "Get-PnpDevice -Class Display | Select-Object FriendlyName, Status, Present"
echo [GPU-PV Guest Setup] Done.
"@

Set-Content -Path (Join-Path $StagingDir "install_gpupv_guest.bat") -Value $GuestInstallerBat -Encoding ASCII

# 4. Handle Execution Modes
if ($Mode -eq "MountVHD") {
    Write-Host "`nMounting VHDX for offline driver injection: $VHDXPath" -ForegroundColor Cyan
    $TargetVM = Get-VM -Name $VMName -ErrorAction SilentlyContinue
    if ($TargetVM -and $TargetVM.State -ne "Off") {
        throw "Cannot perform offline VHDX injection while VM '$VMName' is in '$($TargetVM.State)' state. Stop the VM first."
    }

    if (-not (Test-Path $VHDXPath)) {
        throw "VHDX file not found at: $VHDXPath"
    }

    $MountResult = Mount-VHD -Path $VHDXPath -PassThru
    $DriveLetter = ($MountResult | Get-Disk | Get-Partition | Where-Object { $_.DriveLetter } | Select-Object -First 1).DriveLetter
    
    if (-not $DriveLetter) {
        Dismount-VHD -Path $VHDXPath
        throw "Could not determine mounted drive letter for VHDX."
    }

    $GuestWindows = "${DriveLetter}:\Windows\System32"
    Write-Host "Injecting into ${DriveLetter}:\Windows..." -ForegroundColor Green
    
    $GuestHDS = "${GuestWindows}\HostDriverStore\FileRepository\$($LatestDriverDir.Name)"
    New-Item -ItemType Directory -Path $GuestHDS -Force | Out-Null
    Copy-Item -Path "$HostDriverStoreDest\*" -Destination $GuestHDS -Recurse -Force
    Copy-Item -Path "$System32Dest\*" -Destination $GuestWindows -Force

    Dismount-VHD -Path $VHDXPath
    Write-Host "Offline VHDX Driver Injection Complete and Dismounted." -ForegroundColor Green
}
elseif ($Mode -eq "OnlineCopy") {
    Write-Host "`nCopying drivers to running VM via Hyper-V Guest Service Interface..." -ForegroundColor Cyan
    $VM = Get-VM -Name $VMName -ErrorAction Stop
    if ($VM.State -ne "Running") {
        throw "VM '$VMName' must be in Running state for OnlineCopy mode."
    }

    Copy-VMFile -VMName $VMName -SourcePath $StagingDir -DestinationPath "C:\Temp\NvidiaDrivers" -CreateFullPath -FileSource Host
    Write-Host "Driver package pushed to VM at C:\Temp\NvidiaDrivers. Execute install_gpupv_guest.bat inside guest." -ForegroundColor Green
}

Write-Host "`nStaging summary saved at: $StagingDir" -ForegroundColor Green
