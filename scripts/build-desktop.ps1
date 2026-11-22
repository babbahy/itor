# Builds the employee installer: apps/desktop/build/compose/binaries/main/msi/itor-1.0.0.msi
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
& "$PSScriptRoot/build-helper.ps1"
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'C:\Program Files\Java\jdk-17' }
Push-Location "$Root/apps/desktop"
try {
  ./gradlew.bat --no-daemon packageMsi
  if ($LASTEXITCODE -ne 0) { throw 'packageMsi failed.' }
  Get-ChildItem build/compose/binaries/main/msi/*.msi | ForEach-Object { Write-Host "Installer: $($_.FullName)" }
} finally { Pop-Location }
