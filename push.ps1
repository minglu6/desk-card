# Push a rendered PNG to Likebook and display it fullscreen via Android gallery.
#
# Usage:
#   .\push.ps1                       # pushes ./out/current.png
#   .\push.ps1 -Path other.png       # pushes a specific file
#   .\push.ps1 -NoDisplay            # push only, do not open viewer

param(
    [string]$Path = (Join-Path $PSScriptRoot "out\current.png"),
    [switch]$NoDisplay
)

$ErrorActionPreference = "Stop"

$env:Path = "D:\Program Files\adb-fastboot;" + $env:Path

if (-not (Test-Path $Path)) {
    Write-Error "PNG not found: $Path"
    exit 1
}

$RemoteDir = "/sdcard/DeskCard"
$RemoteFile = "$RemoteDir/current.png"

# Ensure remote dir exists
adb shell "mkdir -p $RemoteDir" | Out-Null

# Push
Write-Host "→ push $Path" -ForegroundColor Cyan
adb push $Path $RemoteFile | Out-Null

if ($NoDisplay) {
    Write-Host "✓ pushed (display skipped)" -ForegroundColor Green
    exit 0
}

# Open in gallery. Try VIEW intent first (system picks viewer).
Write-Host "→ display" -ForegroundColor Cyan
$intent = "am start -a android.intent.action.VIEW -d file://$RemoteFile -t image/png"
$out = adb shell $intent 2>&1
if ($LASTEXITCODE -ne 0 -or $out -match "Error") {
    Write-Host "VIEW intent failed, falling back to direct gallery launch" -ForegroundColor Yellow
    Write-Host $out
    adb shell "am start -n com.android.gallery/com.android.gallery.ViewImage -d file://$RemoteFile" | Out-Null
}

Write-Host "✓ displayed on Likebook" -ForegroundColor Green
