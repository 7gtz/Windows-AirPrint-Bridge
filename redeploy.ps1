# redeploy.ps1 - Rebuild, stop, replace, and restart the AirPrintBridge service.
#
# For iterating on airprint_bridge.py while it's running as an installed Windows
# service: this handles the whole "the exe is locked, the service won't die
# cleanly, something orphaned is still squatting on port 631" dance in one place.
#
# Must be run from an elevated (Administrator) PowerShell - Stop-Service /
# Start-Service require it.
#
# Usage:
#   .\redeploy.ps1              # rebuild + redeploy + restart
#   .\redeploy.ps1 -SkipBuild   # just redeploy the exe already in .\dist, restart

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# ---- Adjust these if your paths differ ----
$ServiceName = "AirPrintBridge"
$DevDir      = "E:\Windows-AirPrint-Bridge"
$InstallDir  = "D:\Programs\AirPrintBridge"
$IppPort     = 631
# --------------------------------------------

$SourceExe = Join-Path $DevDir "dist\AirPrintBridge.exe"
$TargetExe = Join-Path $InstallDir "AirPrintBridge.exe"

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "Not running elevated. Right-click PowerShell -> Run as administrator, then re-run this script."
        exit 1
    }
}

function Stop-AirPrintBridge {
    Write-Host "Stopping service '$ServiceName' ..." -ForegroundColor Cyan
    try {
        Stop-Service -Name $ServiceName -Force -ErrorAction Stop
    } catch {
        Write-Host "  (Stop-Service reported: $_ - continuing, will force-kill below)" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 2

    # Whatever's actually bound to the IPP port is the real thing to kill -
    # more reliable than trusting the service's reported status or matching
    # by image name, both of which have been wrong before on this box.
    $conn = Get-NetTCPConnection -LocalPort $IppPort -ErrorAction SilentlyContinue
    foreach ($c in $conn) {
        Write-Host "  Killing PID $($c.OwningProcess) still bound to port $IppPort ..." -ForegroundColor Yellow
        taskkill /F /PID $c.OwningProcess 2>$null | Out-Null
    }

    # Belt-and-suspenders: catch anything named AirPrintBridge.exe that isn't
    # holding the port for whatever reason (e.g. mid-startup).
    Get-Process -Name "AirPrintBridge" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  Killing PID $($_.Id) (AirPrintBridge.exe) ..." -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 1
    $stillThere = Get-NetTCPConnection -LocalPort $IppPort -ErrorAction SilentlyContinue
    if ($stillThere) {
        Write-Error "Port $IppPort is still occupied by PID $($stillThere.OwningProcess) - investigate before continuing."
        exit 1
    }
    Write-Host "  Confirmed: nothing running, port $IppPort free." -ForegroundColor Green
}

Assert-Admin

if (-not $SkipBuild) {
    Write-Host "=== Building ===" -ForegroundColor Cyan
    Push-Location $DevDir
    try {
        & .\build.ps1
        if ($LASTEXITCODE -ne 0) { throw "build.ps1 failed" }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $SourceExe)) {
    Write-Error "Build output not found at $SourceExe"
    exit 1
}

Stop-AirPrintBridge

Write-Host "=== Deploying ===" -ForegroundColor Cyan
Copy-Item $SourceExe $TargetExe -Force
Write-Host "  Copied $SourceExe -> $TargetExe" -ForegroundColor Green

Write-Host "=== Starting ===" -ForegroundColor Cyan
Start-Service -Name $ServiceName
Start-Sleep -Seconds 1
Get-Service $ServiceName

Write-Host "=== Last 10 log lines ===" -ForegroundColor Cyan
Get-Content (Join-Path $InstallDir "airprint_bridge.log") -Tail 10
