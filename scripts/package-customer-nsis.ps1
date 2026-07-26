param(
  [string]$SourceConfig = "config\production.json",
  [string]$OutputDir = "release\customer-installer"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourceConfigPath = Join-Path $root $SourceConfig
$customerBuildDir = Join-Path $root "build\customer-config"
$customerConfigPath = Join-Path $customerBuildDir "production.json"
$builderConfigPath = Join-Path $customerBuildDir "electron-builder.customer.json"
$outputPath = Join-Path $root $OutputDir

if (-not (Test-Path -LiteralPath $sourceConfigPath)) {
  throw "Missing customer config: $sourceConfigPath"
}

function ConvertTo-JsonUtf8File($Value, $Path) {
  $json = $Value | ConvertTo-Json -Depth 10
  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, "$json$([Environment]::NewLine)", $encoding)
}

Push-Location $root
try {
  New-Item -ItemType Directory -Force -Path $customerBuildDir | Out-Null

  npm run verify:release
  if ($LASTEXITCODE -ne 0) {
    throw "npm run verify:release failed with exit code $LASTEXITCODE"
  }

  $customerConfig = Get-Content -LiteralPath $sourceConfigPath -Encoding UTF8 -Raw | ConvertFrom-Json
  if (-not $customerConfig.SOFT_MODEL_GPT_BASE_URL) {
    throw "SOFT_MODEL_GPT_BASE_URL is required in $sourceConfigPath"
  }
  if (-not $customerConfig.SOFT_MODEL_GPT_API_KEY) {
    throw "SOFT_MODEL_GPT_API_KEY is required in $sourceConfigPath"
  }
  if (-not $customerConfig.SOFT_MODEL_GPT_NAME) {
    throw "SOFT_MODEL_GPT_NAME is required in $sourceConfigPath"
  }

  $customerConfig | Add-Member -NotePropertyName "SOFT_ACCOUNT_PROVIDER" -NotePropertyValue "newapi" -Force
  $customerConfig | Add-Member -NotePropertyName "SOFT_MODEL_MODE" -NotePropertyValue "gpt" -Force
  $customerConfig | Add-Member -NotePropertyName "SOFT_CUSTOMER_PRESET_CONFIG" -NotePropertyValue "true" -Force
  ConvertTo-JsonUtf8File $customerConfig $customerConfigPath

  $packageConfig = Get-Content -LiteralPath (Join-Path $root "package.json") -Encoding UTF8 -Raw | ConvertFrom-Json
  $buildConfig = $packageConfig.build
  $buildConfig.directories.output = $OutputDir
  $resources = @()
  foreach ($item in $buildConfig.extraResources) {
    $resources += $item
  }
  $resources += [pscustomobject]@{
    from = "build/customer-config/production.json"
    to = "config/production.json"
  }
  $resources += [pscustomobject]@{
    from = "libreoffice"
    to = "libreoffice"
  }
  $buildConfig.extraResources = $resources
  ConvertTo-JsonUtf8File $buildConfig $builderConfigPath

  npm run prepare:runtime
  if ($LASTEXITCODE -ne 0) {
    throw "npm run prepare:runtime failed with exit code $LASTEXITCODE"
  }
  npm run prepare:libreoffice
  if ($LASTEXITCODE -ne 0) {
    throw "npm run prepare:libreoffice failed with exit code $LASTEXITCODE"
  }
  npm run build
  if ($LASTEXITCODE -ne 0) {
    throw "npm run build failed with exit code $LASTEXITCODE"
  }
  $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
  $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
  npx electron-builder --win nsis --config $builderConfigPath
  if ($LASTEXITCODE -ne 0) {
    throw "electron-builder failed with exit code $LASTEXITCODE"
  }

  Write-Host "Customer NSIS installer created under: $outputPath"
}
finally {
  Pop-Location
}
