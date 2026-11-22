# Builds the presenter app installer: apps/demo-panel/build/compose/binaries/main/msi/itor demo panel-<version>.msi
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'C:\Program Files\Java\jdk-17' }
Push-Location "$Root/apps/demo-panel"
try {
  ./gradlew.bat --no-daemon packageMsi
  if ($LASTEXITCODE -ne 0) { throw 'packageMsi failed.' }
  Get-ChildItem build/compose/binaries/main/msi/*.msi | ForEach-Object { Write-Host "Installer: $($_.FullName)" }
} finally { Pop-Location }
