# Packs the Python helper into apps/desktop/resources/windows/itor-helper/ (folder with itor-helper.exe).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = "$Root/.venv/Scripts/python.exe"
if (!(Test-Path $Python)) { throw 'Run ./scripts/setup.ps1 first.' }
& $Python -m pip install --quiet pyinstaller==6.22.3 -r "$Root/services/agent/requirements.txt"
# MediaPipe pulls in the full opencv-contrib-python (~110 MB); itor only needs the light headless build to read the webcam.
& $Python -m pip uninstall --quiet -y opencv-contrib-python
& $Python -m pip install --quiet --force-reinstall --no-deps opencv-python-headless==5.1.0.95
Push-Location $Root
try {
  & $Python -m PyInstaller --noconfirm --clean --onedir --noconsole --name itor-helper `
    --paths . --collect-submodules services.agent --collect-submodules uvicorn `
    --collect-binaries mediapipe --collect-data mediapipe --collect-submodules mediapipe.tasks.python `
    --exclude-module matplotlib --exclude-module PIL `
    --add-data "$Root/services/agent/models;services/agent/models" `
    --distpath build/helper --workpath build/helper-work --specpath build `
    services/agent/serve.py
  if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
  $Target = "$Root/apps/desktop/resources/windows/itor-helper"
  if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
  New-Item -ItemType Directory -Force (Split-Path $Target) | Out-Null
  # Not needed to read the webcam (we use DirectShow): saves ~40 MB.
  Get-ChildItem "build/helper/itor-helper/_internal/cv2" -Filter "opencv_videoio_ffmpeg*.dll" | Remove-Item -Force
  Copy-Item -Recurse "build/helper/itor-helper" $Target
  Write-Host "Helper ready: $Target\itor-helper.exe"
} finally { Pop-Location }
