param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Release verification failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
  }
}

Push-Location $root
try {
  Write-Host "[1/7] Running Python regression suite"
  Invoke-Checked "python" @("-m", "unittest", "discover", "-s", "tests")

  Write-Host "[2/7] Compiling Python entrypoints"
  Invoke-Checked "python" @(
    "-m", "py_compile",
    "backend\generate_materials.py",
    "backend\softcopyright\generator.py",
    "backend\softcopyright\docgen.py",
    "backend\softcopyright\screenshots.py",
    "backend\softcopyright\llm_manual.py",
    "backend\softcopyright\ai_frontend_codegen.py",
    "backend\softcopyright\llm\provider.py",
    "backend\softcopyright\llm\trace.py",
    "backend\softcopyright\errors.py"
  )

  Write-Host "[3/7] Checking Electron scripts"
  Invoke-Checked "node" @("--check", "desktop\electron\main.cjs")
  Invoke-Checked "node" @("--check", "desktop\electron\preload.cjs")

  Write-Host "[4/7] Building desktop UI"
  Invoke-Checked "npm" @("run", "build")

  Write-Host "[5/7] Auditing Node dependencies"
  Invoke-Checked "node" @("scripts\verify-npm-audit.mjs")

  Write-Host "[6/7] Checking release configuration and tracked secrets"
  Invoke-Checked "node" @("scripts\verify-release-config.mjs")

  Write-Host "[7/7] Checking locked Python dependencies"
  Invoke-Checked "python" @("-m", "pip", "install", "--dry-run", "--require-hashes", "-r", "requirements-lock.txt")

  Write-Host "Release verification passed."
}
finally {
  Pop-Location
}
