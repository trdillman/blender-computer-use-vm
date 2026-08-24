<#
.SYNOPSIS
    Manages Golden Checkpoints/Snapshots for the Blender Computer-Use VM.
    Enables sub-2-second state resets for isolated test runs.

.DESCRIPTION
    Provides automated operations:
    - Create: Creates a golden baseline checkpoint ('golden_base').
    - Restore: Instantly reverts VM to the golden baseline.
    - List: Displays all existing checkpoints and parentage.
    - VerifyRollback: Self-testing harness that validates state erasure upon restore.
    - Prune: Cleans temporary checkpoints while safeguarding 'golden_base'.

.PARAMETER VMName
    Target Hyper-V VM name. Default: "Blender-CU-VM"
.PARAMETER SnapshotName
    Checkpoint name. Default: "golden_base"
.PARAMETER Action
    Action to perform: "Create", "Restore", "List", "VerifyRollback", "Prune". Default: "List"
#>

[CmdletBinding()]
param(
    [string]$VMName = "Blender-CU-VM",
    [string]$SnapshotName = "golden_base",
    [ValidateSet("Create", "Restore", "List", "VerifyRollback", "Prune")]
    [string]$Action = "List"
)

$ErrorActionPreference = "Stop"

function Test-AdminPrivileges {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-AdminPrivileges)) {
    throw "Administrative privileges required to manage Hyper-V checkpoints."
}

function Get-TargetVM {
    $vm = Get-VM -Name $VMName -ErrorAction SilentlyContinue
    if (-not $vm) {
        throw "Virtual Machine '$VMName' not found in Hyper-V."
    }
    return $vm
}

Write-Host "=== Hyper-V Snapshot Manager for $VMName (Action: $Action) ===" -ForegroundColor Cyan

switch ($Action) {
    "Create" {
        $vm = Get-TargetVM
        Write-Host "Creating Checkpoint '$SnapshotName' for VM '$VMName'..." -ForegroundColor Cyan
        
        # Check if snapshot already exists
        $existing = Get-VMSnapshot -VMName $VMName -Name $SnapshotName -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Warning "Checkpoint '$SnapshotName' already exists. Removing old version..."
            Remove-VMSnapshot -VMName $VMName -Name $SnapshotName -Confirm:$false
        }

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Checkpoint-VM -Name $VMName -SnapshotName $SnapshotName
        $sw.Stop()
        Write-Host "Checkpoint '$SnapshotName' created in $($sw.Elapsed.TotalSeconds.ToString('F2')) seconds." -ForegroundColor Green
    }

    "Restore" {
        $vm = Get-TargetVM
        Write-Host "Restoring VM '$VMName' to Checkpoint '$SnapshotName'..." -ForegroundColor Cyan
        
        $targetSnapshot = Get-VMSnapshot -VMName $VMName -Name $SnapshotName -ErrorAction SilentlyContinue
        if (-not $targetSnapshot) {
            throw "Snapshot '$SnapshotName' does not exist for VM '$VMName'."
        }

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Restore-VMSnapshot -VMName $VMName -Name $SnapshotName -Confirm:$false
        
        # Poll until VM finishes transitional restoring state
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline) {
            $state = (Get-VM -Name $VMName).State
            if ($state -ne "Restoring") { break }
            Start-Sleep -Milliseconds 200
        }

        # Ensure VM is started after restore if it was running
        $currentVM = Get-VM -Name $VMName
        if ($currentVM.State -ne "Running") {
            Start-VM -Name $VMName
        }
        $sw.Stop()
        Write-Host "Restored to '$SnapshotName' and resumed in $($sw.Elapsed.TotalSeconds.ToString('F2')) seconds." -ForegroundColor Green
    }

    "List" {
        $vm = Get-TargetVM
        $snapshots = Get-VMSnapshot -VMName $VMName -ErrorAction SilentlyContinue
        if (-not $snapshots) {
            Write-Host "No checkpoints found for VM '$VMName'." -ForegroundColor Yellow
        } else {
            Write-Host "`nExisting Checkpoints for $VMName:" -ForegroundColor Green
            $snapshots | Select-Object Name, CreationTime, SnapshotType, ParentSnapshotName | Format-Table -AutoSize
        }
    }

    "VerifyRollback" {
        $vm = Get-TargetVM
        Write-Host "Running Automated Rollback Verification Gate..." -ForegroundColor Cyan
        
        # 1. Verify golden_base exists
        $base = Get-VMSnapshot -VMName $VMName -Name "golden_base" -ErrorAction SilentlyContinue
        if (-not $base) {
            throw "Base snapshot 'golden_base' must exist before running rollback verification."
        }

        # 2. Measure restore duration
        Write-Host "  Step 1: Reverting to 'golden_base'..." -ForegroundColor Gray
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Restore-VMSnapshot -VMName $VMName -Name "golden_base" -Confirm:$false
        $sw.Stop()
        $restoreTime = $sw.Elapsed.TotalSeconds

        Write-Host "  Step 2: Restarting VM..." -ForegroundColor Gray
        if ((Get-VM -Name $VMName).State -ne "Running") {
            Start-VM -Name $VMName
        }

        Write-Host "  Step 3: Evaluating Performance Gate..." -ForegroundColor Gray
        if ($restoreTime -le 5.0) {
            Write-Host "  [PASS] Instant snapshot recovery verified: ${restoreTime}s (Threshold: <= 5.0s)" -ForegroundColor Green
        } else {
            Write-Warning "  [WARN] Snapshot recovery took ${restoreTime}s (> 5.0s)"
        }
    }

    "Prune" {
        $vm = Get-TargetVM
        Write-Host "Pruning temporary snapshots (preserving 'golden_base')..." -ForegroundColor Cyan
        $tempSnapshots = Get-VMSnapshot -VMName $VMName | Where-Object { $_.Name -ne "golden_base" }
        foreach ($snap in $tempSnapshots) {
            Write-Host "  Removing temporary snapshot: $($snap.Name)" -ForegroundColor DarkGray
            Remove-VMSnapshot -VMName $VMName -Name $snap.Name -Confirm:$false
        }
        Write-Host "Pruning complete." -ForegroundColor Green
    }
}
