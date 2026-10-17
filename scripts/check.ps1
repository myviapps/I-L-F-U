<#
.SYNOPSIS
  Runs the GitHub CI checks on a Windows machine, for when Actions minutes are out.

.DESCRIPTION
  Mirrors .github/workflows/ci.yml. By default runs the offline jobs: engine lint and tests,
  and the web interface browser tests. The other jobs are behind switches.

.PARAMETER Full
  Also run the jobs that download models from Hugging Face (speech smoke test, benchmarks).

.PARAMETER Installer
  Also run the "windows-installer" job: install with windows\install.ps1, check it, run the
  app with the tiny and base models, then uninstall. It uses %LOCALAPPDATA%\ILFU, so it
  refuses to run if I-L-F-U is already installed there. Needs network.

.PARAMETER SetupExe
  Also run the "windows-setup-exe" job: build ILFU-Setup.exe with Inno Setup 6 (install it
  first, for example "choco install innosetup"), install it silently, check it, uninstall.

.PARAMETER NoVenv
  Use the current Python instead of creating .venv.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\check.ps1
#>
[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$Installer,
    [switch]$SetupExe,
    [switch]$NoVenv
)

$Root = Split-Path -Parent $PSScriptRoot
$Work = Join-Path $Root '.ci-local'  # reports, generated audio and the benchmark clip cache
New-Item -ItemType Directory -Force $Work | Out-Null
Set-Location $Root

# Pick a Python 3.11+ (CI tests 3.11 and 3.12).
if ($NoVenv) {
    $Py = (Get-Command python).Source
} else {
    $Py = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path $Py)) {
        Write-Host 'Creating .venv'
        $made = $false
        foreach ($v in '-3.12', '-3.11', '-3.13') {
            & py $v -m venv (Join-Path $Root '.venv') 2>$null
            if ($LASTEXITCODE -eq 0) { $made = $true; break }
        }
        if (-not $made) {
            & python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer not found' }
            & python -m venv (Join-Path $Root '.venv')
        }
        if (-not (Test-Path $Py)) { throw 'Could not create .venv (need Python 3.11 or newer)' }
    }
    $env:PATH = (Join-Path $Root '.venv\Scripts') + ';' + $env:PATH
}
Write-Host "Using $(& $Py --version) at $Py"

$Results = [ordered]@{}
$Failed = $false

# Runs a block, records PASS, SKIP or FAIL. A block fails when it throws or a command exits
# non-zero; it is skipped when it throws a message starting with 'SKIP:'.
function Invoke-Job([string]$Name, [scriptblock]$Body) {
    Write-Host ''
    Write-Host "=== $Name ==="
    $start = Get-Date
    $status = 'PASS'
    try {
        & $Body
    } catch {
        if ("$($_.Exception.Message)" -like 'SKIP:*') {
            Write-Host "$($_.Exception.Message)"
            $status = 'SKIP'
        } else {
            Write-Host "ERROR: $_"
            $status = 'FAIL'
        }
    }
    $secs = [int]((Get-Date) - $start).TotalSeconds
    $script:Results[$Name] = "$status (${secs}s)"
    if ($status -eq 'FAIL') { $script:Failed = $true }
    Write-Host "--- ${Name}: $status"
}

function Check([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
}

function New-Tone([string]$Python, [string]$Path) {
    & $Python -c "import math, struct, wave; w = wave.open(r'$Path', 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b''.join(struct.pack('<h', int(6000*math.sin(2*math.pi*440*i/16000))) for i in range(32000))); w.close()"
    Check 'making the tone'
}

$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ILFU'
$Lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'I-L-F-U Call Transcriber.lnk'
$Dir = Join-Path $env:LOCALAPPDATA 'ILFU'

# CI job "engine"
Invoke-Job 'engine (lint + tests)' {
    Push-Location (Join-Path $Root 'engine')
    try {
        & $Py -m pip install -q -e '.[dev]'; Check 'install'
        & $Py -m ruff check .; Check 'ruff'
        & $Py -m pytest; Check 'pytest'
    } finally { Pop-Location }
}

# CI job "web-ui"
Invoke-Job 'web-ui (browser tests)' {
    & $Py -m pip install -q -e 'engine[dev]' playwright; Check 'install'
    & $Py -m playwright install chromium; Check 'playwright install'
    Push-Location (Join-Path $Root 'engine')
    try {
        & $Py -m pytest tests/test_web_ui.py -v | Tee-Object -Variable out | Out-Host
        Check 'browser tests'
        # The tests skip themselves when no browser starts; report that as SKIP, not PASS.
        if (-not (($out | Out-String) -match '\d+ passed')) {
            throw 'SKIP: browser tests were skipped (no Chromium?)'
        }
    } finally { Pop-Location }
}

if ($Full) {
    # CI job "speech-smoke"
    Invoke-Job 'speech-smoke' {
        & $Py -m pip install -q -e 'engine[asr]'; Check 'install'
        New-Tone $Py (Join-Path $Work 'tone.wav')
        & ilfu transcribe (Join-Path $Work 'tone.wav') --model tiny --format txt --out (Join-Path $Work 'out.txt')
        Check 'transcription'
        Get-Content (Join-Path $Work 'out.txt')
    }
    # CI jobs "benchmark" and "benchmark-large" (the one-core run needs taskset, so it is left out)
    $cache = Join-Path $Work 'benchmark-cache'
    $summary = Join-Path $Work 'summary.md'
    foreach ($m in 'base', 'small') {
        Invoke-Job "benchmark ($m)" {
            & $Py -m pip install -q -e 'engine[asr]'; Check 'install'
            $report = Join-Path $Work "report-$m.json"
            & ilfu benchmark --model $m --cache $cache --out $report --summary $summary; Check 'benchmark'
            if (Test-Path "benchmark\baseline-$m.json") {
                & ilfu compare "benchmark\baseline-$m.json" $report; Check 'compare'
            } else {
                Write-Host "No baseline committed yet for $m; this run produces it."
            }
        }
    }
    foreach ($m in 'medium', 'large-v3-turbo') {
        Invoke-Job "benchmark-large ($m)" {
            & $Py -m pip install -q -e 'engine[asr]'; Check 'install'
            & ilfu benchmark --model $m --count 10 --cache $cache --out (Join-Path $Work "report-$m.json") --summary $summary
            Check 'benchmark'
        }
    }
}

# CI job "windows-installer"
if ($Installer) {
    Invoke-Job 'windows-installer' {
        if ((Test-Path $Dir) -or (Test-Path $UninstallKey)) {
            throw "I-L-F-U is already installed in $Dir; uninstall it first, this test would remove it"
        }
        & (Join-Path $Root 'windows\install.ps1')
        if (-not (Test-Path "$Dir\venv\Scripts\ilfu.exe")) { throw 'ilfu.exe missing' }
        if (-not (Test-Path "$Dir\uninstall.ps1")) { throw 'uninstall.ps1 missing' }
        if (-not (Test-Path $UninstallKey)) { throw 'Settings entry missing' }
        if (-not (Test-Path $Lnk)) { throw 'Start Menu shortcut missing' }
        & "$Dir\venv\Scripts\ilfu.exe" tier; Check 'tier'
        & "$Dir\venv\Scripts\ilfu.exe" --backend fake record --seconds 1 --out "$Work\rec"; Check 'record'
        if (-not (Test-Path "$Work\rec\mic.wav")) { throw 'recording missing' }

        New-Tone "$Dir\venv\Scripts\python.exe" "$Work\tone.wav"
        & "$Dir\venv\Scripts\ilfu.exe" transcribe "$Work\tone.wav" --model tiny --out "$Work\out.txt"
        if ($LASTEXITCODE -ne 0) { throw 'transcription failed' }
        if (-not (Test-Path "$Work\out.txt")) { throw 'no transcript file' }

        & "$Dir\venv\Scripts\ilfu.exe" setup --model base --accept-terms --save-dir "$Work\ilfu-data"
        if ($LASTEXITCODE -ne 0) { throw 'setup failed' }
        if (-not (Test-Path "$Dir\config.json")) { throw 'config not saved' }

        & "$Dir\venv\Scripts\python.exe" .github/scripts/gui_check.py
        if ($LASTEXITCODE -ne 0) { throw 'window flow failed' }

        & "$Dir\venv\Scripts\ilfu.exe" devices  # informational, like in CI

        & (Join-Path $Root 'windows\uninstall.ps1') -Quiet
        if (Test-Path $Dir) { throw 'install folder still exists' }
        if (Test-Path $UninstallKey) { throw 'Settings entry still exists' }
        if (Test-Path $Lnk) { throw 'shortcut still exists' }
        Write-Host 'Uninstall left nothing behind'
    }
}

# CI job "windows-setup-exe"
if ($SetupExe) {
    Invoke-Job 'windows-setup-exe' {
        if ((Test-Path $Dir) -or (Test-Path $UninstallKey)) {
            throw "I-L-F-U is already installed in $Dir; uninstall it first, this test would remove it"
        }
        $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found at $iscc (choco install innosetup)" }
        & $iscc /DAppVersion=0.0.1 windows\installer\ilfu.iss; Check 'ISCC'
        if (-not (Test-Path dist\ILFU-Setup-0.0.1.exe)) { throw 'installer was not built' }
        Get-Item dist\ILFU-Setup-0.0.1.exe | Select-Object Name, Length

        Start-Process dist\ILFU-Setup-0.0.1.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait
        if (-not (Test-Path "$Dir\venv\Scripts\ilfu.exe")) { throw 'installer did not install the app' }
        if (-not (Test-Path $UninstallKey)) { throw 'Settings entry missing' }
        if (-not (Test-Path $Lnk)) { throw 'Start Menu shortcut missing' }
        & "$Dir\venv\Scripts\ilfu.exe" tier; Check 'tier'
        & "$Dir\venv\Scripts\python.exe" -c "import importlib.resources as r; assert r.files('ilfu').joinpath('web/index.html').is_file(); print('web interface files installed')"
        Check 'web files'

        & "$Dir\uninstall.ps1" -Quiet
        if (Test-Path $Dir) { throw 'install folder still exists' }
        if (Test-Path $UninstallKey) { throw 'Settings entry still exists' }
    }
}

Write-Host ''
Write-Host "=== Summary ($(& $Py --version), Windows) ==="
foreach ($k in $Results.Keys) { Write-Host ('  {0,-36} {1}' -f $k, $Results[$k]) }
if (-not $Full) { Write-Host '  speech-smoke / benchmarks: not run (add -Full; needs Hugging Face access)' }
if (-not $Installer) { Write-Host '  windows-installer: not run (add -Installer)' }
if (-not $SetupExe) { Write-Host '  windows-setup-exe: not run (add -SetupExe; needs Inno Setup 6)' }
if ($Failed) {
    Write-Host 'RESULT: FAIL'
    exit 1
}
Write-Host 'RESULT: PASS'
