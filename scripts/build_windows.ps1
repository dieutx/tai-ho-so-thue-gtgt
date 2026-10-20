[CmdletBinding()]
param([string]$Python, [string]$ToolsPython, [switch]$SkipInstall, [switch]$MeasureOnedir)
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
        & $Python -m pip install -r requirements-desktop.txt -e .
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    }
    if (-not $ToolsPython) {
        $ToolsPython = Join-Path $root '.venv-release-tools/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $ToolsPython)) {
            & $Python -m venv (Join-Path $root '.venv-release-tools')
            if ($LASTEXITCODE -ne 0) { throw 'Tooling venv creation failed' }
        }
        & $ToolsPython -m pip install -r requirements-build-tools.txt
        if ($LASTEXITCODE -ne 0) { throw 'Tooling installation failed' }
    }
    & $Python -m unittest discover -s tests -t .
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $ToolsPython -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
    & $ToolsPython -m mypy gdt_tax
    if ($LASTEXITCODE -ne 0) { throw 'Type checks failed' }
    & $Python scripts/write_release_metadata.py
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata generation failed' }
    $releaseVersion = & $Python -c "from desktop import __version__; print(__version__)"
    if ($releaseVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid desktop version' }
    $measureRoot = Join-Path '.cache/optimization' ('release-' + $releaseVersion)
    if ($MeasureOnedir) {
        $previousBundleMode = $env:TAIHOSOTHUE_ONEDIR
        try {
            $env:TAIHOSOTHUE_ONEDIR = '1'
            & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $measureRoot 'onedir') --workpath .cache/release-build/onedir packaging/TaiHoSoThue.spec
            if ($LASTEXITCODE -ne 0) { throw 'Measurement onedir build failed' }
        } finally { $env:TAIHOSOTHUE_ONEDIR = $previousBundleMode }
    }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath .cache/release-build/onefile packaging/TaiHoSoThue.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $exe = Join-Path $root 'dist/TaiHoSoThue-Windows.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'EXE was not produced' }
    & $Python scripts/audit_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Bundle/security audit failed' }
    if ($MeasureOnedir) {
        & $Python scripts/size_inventory.py $exe --folder (Join-Path $measureRoot 'onedir/TaiHoSoThue-Windows') --output (Join-Path $measureRoot 'inventory.json')
        if ($LASTEXITCODE -ne 0) { throw 'Size inventory failed' }
    }
    & (Join-Path $PSScriptRoot 'smoke_test_windows.ps1') -Exe $exe -Python $Python
    if ($LASTEXITCODE -ne 0) { throw 'Frozen smoke test failed' }
    Get-FileHash -LiteralPath $exe -Algorithm SHA256
} finally { Pop-Location }
