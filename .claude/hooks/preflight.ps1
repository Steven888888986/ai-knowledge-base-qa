$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $projectRoot
try {
    py -3 scripts/preflight.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    py -3 scripts/evaluate.py --check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
