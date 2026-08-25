$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$hyperv = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -ErrorAction SilentlyContinue).State
$gpu = (Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }).Name
$cpu = (Get-CimInstance Win32_Processor).Name

Write-Host "IsAdministrator: $isAdmin"
Write-Host "HyperVState:     $hyperv"
Write-Host "HostGPU:         $gpu"
Write-Host "HostCPU:         $cpu"
