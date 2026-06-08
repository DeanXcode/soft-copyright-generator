param(
  [string]$Version = "0.1.0",
  [string]$OutputRoot = "release"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$packageName = "soft-copyright-generator-$Version-portable"
$stageRoot = Join-Path $root $OutputRoot
$stageDir = Join-Path $stageRoot $packageName
$zipPath = Join-Path $stageRoot "$packageName.zip"

function Copy-Directory($Source, $Destination) {
  if (-not (Test-Path -LiteralPath $Source)) {
    throw "Missing required path: $Source"
  }
  if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

Push-Location $root
try {
  npm run build

  if (-not (Test-Path -LiteralPath (Join-Path $root "ms-playwright"))) {
    npm run prepare:playwright
  }
  if (-not (Test-Path -LiteralPath (Join-Path $root "python-runtime\python.exe"))) {
    npm run prepare:python
  }

  if (Test-Path -LiteralPath $stageDir) {
    Remove-Item -LiteralPath $stageDir -Recurse -Force
  }
  if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
  }
  New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

  Copy-Directory (Join-Path $root "backend") (Join-Path $stageDir "backend")
  Copy-Directory (Join-Path $root "desktop") (Join-Path $stageDir "desktop")
  Copy-Directory (Join-Path $root "dist") (Join-Path $stageDir "dist")
  Copy-Directory (Join-Path $root "ms-playwright") (Join-Path $stageDir "ms-playwright")
  Copy-Directory (Join-Path $root "python-runtime") (Join-Path $stageDir "python-runtime")
  Copy-Directory (Join-Path $root "config") (Join-Path $stageDir "config")

  Remove-Item -LiteralPath (Join-Path $stageDir "config\production.json") -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $stageDir "config\desktop.local.json") -Force -ErrorAction SilentlyContinue

  foreach ($file in @("index.html", "package.json", "package-lock.json", "requirements.txt", "start-desktop.ps1", "start-desktop.bat", "vite.config.js", "README.md")) {
    Copy-Item -LiteralPath (Join-Path $root $file) -Destination (Join-Path $stageDir $file) -Force
  }

  @'
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $here "ms-playwright"
$env:PYTHONIOENCODING = "utf-8"
npm run electron
'@ | Out-File -Encoding utf8 -FilePath (Join-Path $stageDir "run-desktop.ps1") -Force

  @'
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0run-desktop.ps1"
'@ | Out-File -Encoding ascii -FilePath (Join-Path $stageDir "run-desktop.bat") -Force

  @'
# Portable Package Notes

1. Install Node dependencies on the target machine:

   npm install --omit=dev

2. Copy `config\production.example.json` to `config\production.json` and fill the real API Key if GPT mode is needed.

3. Start:

   run-desktop.bat

The package includes `python-runtime/` and `ms-playwright/`, so material generation and screenshots do not require the target machine to install Python or Chromium separately.
'@ | Out-File -Encoding utf8 -FilePath (Join-Path $stageDir "PORTABLE_README.md") -Force

  Start-Sleep -Milliseconds 500
  Compress-Archive -LiteralPath $stageDir -DestinationPath $zipPath -Force
  Write-Host "Portable package created: $zipPath"
}
finally {
  Pop-Location
}
