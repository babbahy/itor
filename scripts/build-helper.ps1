# Packs the Python helper into apps/desktop/resources/windows/itor-helper/ (folder with itor-helper.exe).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = "$Root/.venv/Scripts/python.exe"
if (!(Test-Path $Python)) { throw 'Run ./scripts/setup.ps1 first.' }
& $Python -m pip install --quiet pyinstaller==6.22.3
Push-Location $Root
try {
  & $Python -m PyInstaller --noconfirm --clean --onedir --noconsole --name itor-helper `
    --paths . --collect-submodules services.agent --collect-submodules uvicorn `
    --distpath build/helper --workpath build/helper-work --specpath build `
    services/agent/serve.py
  if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
  $Target = "$Root/apps/desktop/resources/windows/itor-helper"
  if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
  New-Item -ItemType Directory -Force (Split-Path $Target) | Out-Null
  Copy-Item -Recurse "build/helper/itor-helper" $Target
  Write-Host "Helper ready: $Target\itor-helper.exe"
} finally { Pop-Location }
