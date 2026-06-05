@echo off
setlocal
cd /d "%~dp0"
call npm run build
if errorlevel 1 (
  echo.
  echo Build failed. Press any key to close.
  pause >nul
  exit /b 1
)

call npm run electron
if errorlevel 1 (
  echo.
  echo Electron failed to start. Press any key to close.
  pause >nul
  exit /b 1
)
