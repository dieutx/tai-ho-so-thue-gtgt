[CmdletBinding()]
param([string]$Python, [string]$ToolsPython, [switch]$SkipInstall, [switch]$MeasureOnedir, [switch]$SkipSmoke)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Build requires Windows x64' }
    if (-not $Python) {
        $Python = Join-Path $root '.venv-release/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $Python)) {
            & py -3.11 -m venv (Join-Path $root '.venv-release')
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64 is required on the build machine' }
        }
    }
    & $Python -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8, 'Require CPython 3.11 x64'"
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported build interpreter' }
    if (-not $SkipInstall) {
        & $Python -m pip install --no-deps -r requirements-desktop-windows-py311.lock
        if ($LASTEXITCODE -ne 0) { throw 'Locked runtime installation failed' }
        & $Python -m pip install --no-deps --no-build-isolation -e .
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    }
    if (-not $ToolsPython) {
        $ToolsPython = Join-Path $root '.venv-release-tools/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $ToolsPython)) {
            & $Python -m venv (Join-Path $root '.venv-release-tools')
            if ($LASTEXITCODE -ne 0) { throw 'Tooling venv creation failed' }
        }
        & $ToolsPython -m pip install --no-deps -r requirements-build-tools-windows-py311.lock
        if ($LASTEXITCODE -ne 0) { throw 'Tooling installation failed' }
    }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Runtime dependency graph is incomplete' }
    & $Python scripts/dependency_inventory.py verify --profile runtime
    if ($LASTEXITCODE -ne 0) { throw 'Runtime inventory mismatch' }
    & $ToolsPython scripts/dependency_inventory.py verify --profile tools
    if ($LASTEXITCODE -ne 0) { throw 'Tooling inventory mismatch' }
    & $Python scripts/run_test_gate.py --profile desktop
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $ToolsPython -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
    & $ToolsPython -m mypy gdt_tax tests/test_core_contracts.py
    if ($LASTEXITCODE -ne 0) { throw 'Type checks failed' }
    & $Python scripts/write_release_metadata.py
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata generation failed' }
    $releaseVersion = & $Python -c "from desktop import __version__; print(__version__)"
    if ($releaseVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid desktop version' }
    $metadataVersion = & $Python -c "import json; from pathlib import Path; print(json.loads(Path('desktop/resources/release.json').read_text(encoding='utf-8'))['version'])"
    if ($LASTEXITCODE -ne 0 -or $metadataVersion -ne $releaseVersion) { throw 'Source and generated EXE versions differ' }
    $measureRoot = Join-Path '.cache/optimization' ('release-' + $releaseVersion)
    if ($MeasureOnedir) {
        $previousBundleMode = $env:TAIHOSOTHUE_ONEDIR
        try {
            $env:TAIHOSOTHUE_ONEDIR = '1'
            & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $measureRoot 'onedir') --workpath .cache/release-build/onedir packaging/TaiHoSoThue.spec
            if ($LASTEXITCODE -ne 0) { throw 'Measurement onedir build failed' }
        } finally { $env:TAIHOSOTHUE_ONEDIR = $previousBundleMode }
    }
    $previousBundleMode = $env:TAIHOSOTHUE_ONEDIR
    try {
        $env:TAIHOSOTHUE_ONEDIR = $null
        & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath .cache/release-build/onefile packaging/TaiHoSoThue.spec
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    } finally { $env:TAIHOSOTHUE_ONEDIR = $previousBundleMode }
    $exe = Join-Path $root 'dist/TaiHoSoThue-Windows.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'EXE was not produced' }
    & $Python scripts/audit_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Bundle/security audit failed' }
    if ($MeasureOnedir) {
        & $Python scripts/size_inventory.py $exe --folder (Join-Path $measureRoot 'onedir/TaiHoSoThue-Windows') --output (Join-Path $measureRoot 'inventory.json')
        if ($LASTEXITCODE -ne 0) { throw 'Size inventory failed' }
    }
    if (-not $SkipSmoke) {
        & (Join-Path $PSScriptRoot 'smoke_test_windows.ps1') -Exe $exe -Python $Python
        if ($LASTEXITCODE -ne 0) { throw 'Frozen smoke test failed' }
        & $Python scripts/build_provenance.py
        if ($LASTEXITCODE -ne 0) { throw 'Build provenance verification failed' }
    } else {
        Write-Output 'TEST BUILD: skipped release smoke/provenance gate (not a release artifact)'
    }
    Get-FileHash -LiteralPath $exe -Algorithm SHA256
} finally { Pop-Location }
