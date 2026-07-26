param(
  [string]$Source = "",
  [string]$Destination = "libreoffice"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$destinationPath = Join-Path $root $Destination

function Resolve-ExistingPath($Path) {
  if ($Path -and (Test-Path -LiteralPath $Path)) {
    return (Resolve-Path -LiteralPath $Path).Path
  }
  return ""
}

function Assert-UnderRoot($Path) {
  $fullPath = [System.IO.Path]::GetFullPath($Path)
  $fullRoot = [System.IO.Path]::GetFullPath($root)
  if (-not $fullPath.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write outside project root: $fullPath"
  }
}

$sourceCandidates = @()
if ($Source) {
  $sourceCandidates += $Source
}
if ($env:LIBREOFFICE_HOME) {
  $sourceCandidates += $env:LIBREOFFICE_HOME
}
$sourceCandidates += @(
  "C:\Program Files\LibreOffice",
  "C:\Program Files (x86)\LibreOffice"
)

$sourcePath = ""
foreach ($candidate in $sourceCandidates) {
  $resolved = Resolve-ExistingPath $candidate
  if (-not $resolved) {
    continue
  }
  if (Test-Path -LiteralPath (Join-Path $resolved "program\soffice.exe")) {
    $sourcePath = $resolved
    break
  }
}

if (-not $sourcePath) {
  throw "LibreOffice installation was not found. Install LibreOffice first or pass -Source."
}

Assert-UnderRoot $destinationPath

if (Test-Path -LiteralPath $destinationPath) {
  Remove-Item -LiteralPath $destinationPath -Recurse -Force
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force

$sofficePath = Join-Path $destinationPath "program\soffice.exe"
$requiredRuntimePaths = @(
  $sofficePath,
  (Join-Path $destinationPath "program\soffice.com"),
  (Join-Path $destinationPath "program\services"),
  (Join-Path $destinationPath "program\types\offapi.rdb")
)
foreach ($requiredPath in $requiredRuntimePaths) {
  if (-not (Test-Path -LiteralPath $requiredPath)) {
    throw "LibreOffice runtime copy is incomplete: $requiredPath"
  }
}

$sofficeConsolePath = Join-Path $destinationPath "program\soffice.com"
& $sofficeConsolePath --headless --version | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "LibreOffice runtime startup probe failed with exit code ${LASTEXITCODE}: $sofficeConsolePath"
}

$sizeBytes = (Get-ChildItem -LiteralPath $destinationPath -Recurse -Force | Measure-Object -Property Length -Sum).Sum
$sizeMb = [math]::Round($sizeBytes / 1MB, 2)
Write-Host "LibreOffice runtime ready: $destinationPath ($sizeMb MB)"
