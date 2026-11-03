[CmdletBinding()]
param([string]$Exe = (Join-Path (Split-Path $PSScriptRoot -Parent) 'dist/TaiHoSoThue-Windows.exe'), [string]$Python)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
$exePath = (Resolve-Path -LiteralPath $Exe).Path
$testRoot = Join-Path $root ('.cache/smoke-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $testRoot
# Unicode path, spaces, and a standalone copy with no sidecar files.
$standalone = Join-Path $testRoot ('Thu' + [char]0x1EBF + ' portable')
$null = New-Item -ItemType Directory -Path $standalone
$copied = Join-Path $standalone 'TaiHoSoThue-Windows.exe'
Copy-Item -LiteralPath $exePath -Destination $copied
$fixture = Join-Path $root 'tests/fixtures'
$sourceResult = $null
if ($Python) {
    $sourceReport = Join-Path $testRoot 'source-report.json'
    & $Python -m desktop.main --self-test $fixture --test-output (Join-Path $testRoot 'source-output') --test-report $sourceReport
    if ($LASTEXITCODE -ne 0) { throw 'Source OCR self-test failed' }
    $sourceResult = Get-Content -LiteralPath $sourceReport -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $sourceResult.pass -or $sourceResult.frozen) { throw 'Invalid source OCR reference' }
}
foreach ($index in 1..2) {
    $report = Join-Path $testRoot ('report-' + $index + '.json')
    $output = Join-Path $testRoot ('ket qua ' + $index)
    $arguments = @('--self-test', ('"' + $fixture + '"'), '--test-output', ('"' + $output + '"'), '--test-report', ('"' + $report + '"'))
    $process = Start-Process -FilePath $copied -ArgumentList $arguments -WorkingDirectory $standalone -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(180000)) { throw 'Smoke test timed out; process left for inspection' }
    if ($process.ExitCode -ne 0) { throw ('Frozen self-test failed: ' + $report) }
    $result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $result.pass -or -not $result.frozen -or -not $result.ocr_offline -or -not $result.captcha_fallback_bounded) { throw 'Frozen/OCR acceptance failed' }
    if (-not $result.portal_verification_detected) { throw 'Frozen portal verification detection failed' }
    if (-not $result.persistent_catalog) { throw 'Frozen SQLite persistence failed' }
    if (-not $result.personal_catalog_view) { throw 'Frozen personal catalog UI failed' }
    if (-not $result.portal_regressions -or -not $result.saved_accounts_native) { throw 'Frozen portal/vault regression failed' }
    if ($sourceResult) {
        foreach ($field in @('source_sha', 'core_version', 'ocr_fixture_sha256', 'ocr_text_sha256', 'ocr_model_sha256', 'ocr_charset_sha256')) {
            if ($result.$field -ne $sourceResult.$field) { throw ('Source/frozen OCR differs: ' + $field) }
        }
        if (($result.ocr_providers -join ',') -ne ($sourceResult.ocr_providers -join ',')) { throw 'Source/frozen ONNX provider differs' }
    }
}
$gui = Start-Process -FilePath $copied -ArgumentList @('--quit-after', '1500') -WorkingDirectory $standalone -WindowStyle Hidden -PassThru
if (-not $gui.WaitForExit(60000) -or $gui.ExitCode -ne 0) { throw 'GUI startup failed' }
$previousPlatform = $env:QT_QPA_PLATFORM
$previousScale = $env:QT_SCALE_FACTOR
try {
    $env:QT_QPA_PLATFORM = 'windows'
    foreach ($size in @('1920x1040', '1366x728', '1280x680', '1080x660', '1024x728', '1024x560')) {
      foreach ($scale in @('1', '1.25', '1.5')) {
        $env:QT_SCALE_FACTOR = $scale
        $screenshots = Join-Path $testRoot 'screenshots'
        $arguments = @('--ui-check', ('"' + $screenshots + '"'), '--ui-size', $size)
        $process = Start-Process -FilePath $copied -ArgumentList $arguments -WorkingDirectory $standalone -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(60000) -or $process.ExitCode -ne 0) { throw ('Native UI/DPI check failed: ' + $size + '/' + $scale) }
      }
    }
} finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
    $env:QT_SCALE_FACTOR = $previousScale
}
Write-Output ('PASS: frozen offline pipeline, bundled mapping/OCR, repeated startup; evidence: ' + $testRoot)
Set-Content -LiteralPath (Join-Path $root '.cache/last-smoke-path.txt') -Value $testRoot -Encoding UTF8
$global:LASTEXITCODE = 0
