$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if ($env:ITOR_PYTHON) {
    & $env:ITOR_PYTHON "$Root/scripts/local.py" setup
} elseif (Test-Path "$Root/.venv/Scripts/python.exe") {
    & "$Root/.venv/Scripts/python.exe" "$Root/scripts/local.py" setup
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$Root/scripts/local.py" setup
} else {
    & python "$Root/scripts/local.py" setup
}
exit $LASTEXITCODE
