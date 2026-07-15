param(
  [string]$PythonVersion = "3.12.10",
  [string]$RuntimeDir = "python-runtime",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runtimePath = Join-Path $root $RuntimeDir
$tmpDir = Join-Path $root "tmp\python-runtime"
$zipPath = Join-Path $tmpDir "python-$PythonVersion-embed-amd64.zip"
$getPipPath = Join-Path $tmpDir "get-pip.py"
$pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"

function Save-Url($Url, $OutFile) {
  if (Test-Path -LiteralPath $OutFile) {
    Remove-Item -LiteralPath $OutFile -Force
  }

  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  if ($curl) {
    & $curl.Source --fail --location --retry 5 --retry-delay 3 --retry-all-errors --output $OutFile $Url
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $OutFile)) {
      return
    }
  }

  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
      Invoke-WebRequest -Uri $Url -OutFile $OutFile
      return
    } catch {
      if ($attempt -eq 5) {
        throw
      }
      Start-Sleep -Seconds (2 * $attempt)
    }
  }
}

function Invoke-Checked($CommandPath, $Arguments) {
  & $CommandPath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $CommandPath $($Arguments -join ' ')"
  }
}

function Test-RuntimeReady($PythonExe) {
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    return $false
  }
  try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe -c "import sys, docx, reportlab, playwright, pypdf, softcopyright; print('embedded-python-ok')" > $null 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    return $exitCode -eq 0
  } catch {
    $ErrorActionPreference = $previousErrorActionPreference
    return $false
  }
}

$existingPythonExe = Join-Path $runtimePath "python.exe"
if (-not $Force -and (Test-RuntimeReady $existingPythonExe)) {
  Write-Host "Python runtime already ready: $runtimePath"
  exit 0
}

if (Test-Path -LiteralPath $runtimePath) {
  Remove-Item -LiteralPath $runtimePath -Recurse -Force
}
if (Test-Path -LiteralPath $tmpDir) {
  Remove-Item -LiteralPath $tmpDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

Write-Host "Downloading Python embeddable runtime: $pythonUrl"
Save-Url $pythonUrl $zipPath

Write-Host "Extracting Python runtime to: $runtimePath"
Expand-Archive -LiteralPath $zipPath -DestinationPath $runtimePath -Force

$pth = Get-ChildItem -LiteralPath $runtimePath -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) {
  throw "Unable to find python ._pth file in $runtimePath"
}

$lines = Get-Content -Encoding UTF8 -LiteralPath $pth.FullName
$updated = @()
foreach ($line in $lines) {
  if ($line -eq "#import site") {
    $updated += "import site"
  } else {
    $updated += $line
  }
}
if ($updated -notcontains "..\backend") {
  $insertAt = [Math]::Max(0, [Array]::IndexOf($updated, "") )
  if ($insertAt -gt 0) {
    $updated = @($updated[0..($insertAt - 1)]) + @("..\backend") + @($updated[$insertAt..($updated.Count - 1)])
  } else {
    $updated += "..\backend"
  }
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($pth.FullName, [string[]]$updated, $utf8NoBom)

Write-Host "Downloading get-pip.py"
Save-Url $getPipUrl $getPipPath

$pythonExe = Join-Path $runtimePath "python.exe"
Write-Host "Installing pip into embedded Python"
Invoke-Checked $pythonExe @($getPipPath, "--no-warn-script-location")

Write-Host "Installing project Python dependencies"
Invoke-Checked $pythonExe @("-m", "pip", "install", "--no-warn-script-location", "-r", (Join-Path $root "requirements.txt"))

Write-Host "Verifying embedded Python"
Invoke-Checked $pythonExe @("-c", "import sys, docx, reportlab, playwright, pypdf; print(sys.version); print('embedded-python-ok')")

Write-Host "Python runtime ready: $runtimePath"
