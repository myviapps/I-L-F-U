<#
.SYNOPSIS
  Removes the I-L-F-U call transcriber installed by install.ps1.

.DESCRIPTION
  Deletes the app, its downloaded models, the Start Menu shortcut and the Settings > Apps entry.
  Your recordings and transcripts (Documents\ILFU) are kept unless you ask to delete them.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'ILFU'),
    [switch]$Quiet,
    [switch]$RemoveData
)

$ErrorActionPreference = 'Stop'

# Run from a temporary copy so the install folder (which holds this script) can be deleted.
if ($PSCommandPath -and $PSCommandPath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) {
    $tmp = Join-Path $env:TEMP 'ilfu-uninstall.ps1'
    Copy-Item $PSCommandPath $tmp -Force
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $tmp, '-InstallDir', $InstallDir)
    if ($Quiet) { $argList += '-Quiet' }
    if ($RemoveData) { $argList += '-RemoveData' }
    & powershell.exe @argList
    exit $LASTEXITCODE
}

$dataDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ILFU'

Write-Host '== I-L-F-U uninstaller ==' -ForegroundColor Cyan
if (-not $Quiet) {
    $answer = Read-Host "Remove I-L-F-U from this computer? (y/N)"
    if ($answer -notmatch '^[yY]') { Write-Host 'Cancelled. Nothing was removed.'; exit 0 }
    if ((Test-Path $dataDir) -and -not $RemoveData) {
        $answer = Read-Host "Also delete your recordings and transcripts in $dataDir ? (y/N)"
        if ($answer -match '^[yY]') { $RemoveData = $true }
    }
}

# Stop the app if it is running.
Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and $_.Path.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# Start Menu shortcut and Settings > Apps entry.
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'I-L-F-U Call Transcriber.lnk'
if (Test-Path $shortcut) { Remove-Item $shortcut -Force }
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ILFU'
if (Test-Path $regPath) { Remove-Item $regPath -Recurse -Force }

# The app, its environment and its downloaded models.
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }

if ($RemoveData -and (Test-Path $dataDir)) {
    Remove-Item $dataDir -Recurse -Force
    Write-Host "Deleted $dataDir"
} elseif (Test-Path $dataDir) {
    Write-Host "Kept your recordings and transcripts in $dataDir"
}

Write-Host 'I-L-F-U has been removed.' -ForegroundColor Green
if (-not $Quiet) { Read-Host 'Press Enter to close' | Out-Null }
