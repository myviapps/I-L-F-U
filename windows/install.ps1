<#
.SYNOPSIS
  Installs the I-L-F-U call transcriber for the current Windows user. No administrator rights needed.

.DESCRIPTION
  Creates a private Python environment in %LOCALAPPDATA%\ILFU, installs the app into it, adds a
  Start Menu shortcut, and registers an entry in Settings > Apps so it can be uninstalled there.
  Run it from a copy of this repository (the folder that contains "engine").

.EXAMPLE
  Right-click install.ps1 > Run with PowerShell
#>
[CmdletBinding()]
param(
    [string]$Source,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'ILFU'),
    [switch]$NoShortcut,
    [switch]$NoAsr
)

$ErrorActionPreference = 'Stop'

function Find-Python {
    $candidates = @(
        @('py', '-3.12'), @('py', '-3.13'), @('py', '-3.11'), @('python')
    )
    foreach ($c in $candidates) {
        try {
            $exe = $c[0]
            $rest = @()
            if ($c.Length -gt 1) { $rest = $c[1..($c.Length - 1)] }
            $ver = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver -and [version]$ver -ge [version]'3.11') {
                return , $c
            }
        } catch { }
    }
    return $null
}

Write-Host '== I-L-F-U installer ==' -ForegroundColor Cyan

# 1. Find the app source.
if (-not $Source) { $Source = Split-Path $PSScriptRoot -Parent }
if (Test-Path (Join-Path $Source 'engine\pyproject.toml')) {
    $EngineDir = Join-Path $Source 'engine'
} elseif (Test-Path (Join-Path $Source 'pyproject.toml')) {
    $EngineDir = $Source
} else {
    throw "Cannot find the app source in '$Source'. Run this script from the downloaded repository folder."
}

# 2. Find Python 3.11+ (offer to install it with winget).
$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3.11 or newer was not found.' -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'Installing Python 3.12 with winget...'
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $py = Find-Python
    }
}
if (-not $py) {
    throw 'Please install Python 3.12 from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run this script again.'
}
$pyExe = $py[0]
$pyArgs = @()
if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }

# 3. Create the private environment.
$venv = Join-Path $InstallDir 'venv'
Write-Host "Installing into $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
& $pyExe @pyArgs -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
$venvPython = Join-Path $venv 'Scripts\python.exe'
$venvPythonW = Join-Path $venv 'Scripts\pythonw.exe'

& $venvPython -m pip install --upgrade pip --quiet
$extras = if ($NoAsr) { 'windows' } else { 'asr,windows' }
Write-Host 'Installing the app and its speech engine (this can take a few minutes)...'
& $venvPython -m pip install "$EngineDir[$extras]" --quiet
if ($LASTEXITCODE -ne 0) { throw 'Installing the app failed.' }

$version = (& $venvPython -c 'import ilfu; print(ilfu.__version__)').Trim()

# 4. Marker file, uninstaller, Start Menu shortcut, Settings > Apps entry.
@{ version = $version; installed = (Get-Date).ToString('s'); source = $EngineDir } |
    ConvertTo-Json | Set-Content -Path (Join-Path $InstallDir 'ilfu-install.json') -Encoding UTF8
Copy-Item (Join-Path $PSScriptRoot 'uninstall.ps1') (Join-Path $InstallDir 'uninstall.ps1') -Force

if (-not $NoShortcut) {
    $programs = [Environment]::GetFolderPath('Programs')
    $shortcutPath = Join-Path $programs 'I-L-F-U Call Transcriber.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($shortcutPath)
    $lnk.TargetPath = $venvPythonW
    $lnk.Arguments = '-m ilfu.gui'
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = 'Free, local call transcriber'
    $lnk.Save()
}

$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ILFU'
New-Item -Path $regPath -Force | Out-Null
$uninstallCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'uninstall.ps1')`" -InstallDir `"$InstallDir`""
Set-ItemProperty $regPath DisplayName 'I-L-F-U Call Transcriber'
Set-ItemProperty $regPath DisplayVersion $version
Set-ItemProperty $regPath Publisher 'I-L-F-U contributors'
Set-ItemProperty $regPath InstallLocation $InstallDir
Set-ItemProperty $regPath UninstallString $uninstallCmd
Set-ItemProperty $regPath NoModify 1 -Type DWord
Set-ItemProperty $regPath NoRepair 1 -Type DWord

# 5. Quick self-check.
Write-Host 'Checking the install...'
& (Join-Path $venv 'Scripts\ilfu.exe') tier
if ($LASTEXITCODE -ne 0) { throw 'The installed app did not start correctly.' }

Write-Host ''
Write-Host "Done. Open 'I-L-F-U Call Transcriber' from the Start Menu." -ForegroundColor Green
Write-Host 'To remove it: Settings > Apps > I-L-F-U Call Transcriber > Uninstall, or Help > Uninstall in the app.'
