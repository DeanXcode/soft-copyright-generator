param(
  [switch]$Apply,
  [int]$KeepSmokeDirectories = 2
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$candidates = New-Object System.Collections.Generic.List[string]

function Add-Candidate([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  if (-not $resolved.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Cleanup target escaped the workspace: $resolved"
  }
  $candidates.Add($resolved)
}

$tmpPath = Join-Path $root "tmp"
if (Test-Path -LiteralPath $tmpPath) {
  Get-ChildItem -LiteralPath $tmpPath -Force | ForEach-Object { Add-Candidate $_.FullName }
}
Add-Candidate (Join-Path $root "release\installer\win-unpacked")
Add-Candidate (Join-Path $root "release\customer-installer\win-unpacked")

$smokeDirectories = Get-ChildItem -LiteralPath (Join-Path $root "release") -Directory -Filter "smoke-*" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending
$smokeDirectories | Select-Object -Skip ([Math]::Max(0, $KeepSmokeDirectories)) | ForEach-Object { Add-Candidate $_.FullName }

if (-not $candidates.Count) {
  Write-Host "No removable intermediate artifacts found."
  exit 0
}

foreach ($candidate in $candidates) {
  if ($Apply) {
    Write-Host "Removing: $candidate"
    Remove-Item -LiteralPath $candidate -Recurse -Force
  } else {
    Write-Host "Would remove: $candidate"
  }
}

if (-not $Apply) {
  Write-Host "Dry run only. Re-run with -Apply to remove the listed intermediate artifacts."
}
