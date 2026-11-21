param([ValidateSet('dev', 'start')][string]$Mode = 'dev')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = "$Root/.venv/Scripts/python.exe"
if (!(Test-Path $Python)) { throw 'Run ./scripts/setup.ps1 first.' }
& $Python "$Root/scripts/local.py" $Mode
exit $LASTEXITCODE
