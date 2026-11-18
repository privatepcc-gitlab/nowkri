@echo off
title Job Hunt - frontend
cd /d "%~dp0frontend"

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] Node.js is not installed or not on PATH.
  echo Install the LTS version from https://nodejs.org and run this again.
  echo.
  pause
  exit /b 1
)
node --version

if not exist node_modules (
  echo Installing packages, this takes a minute the first time...
  call npm install || goto :fail
)

echo.
echo Frontend starting. Open http://127.0.0.1:5173 in your browser.
echo Keep this window open. Press Ctrl+C to stop.
echo.
call npm run dev
goto :end

:fail
echo.
echo [ERROR] npm install failed. Read the message above.
:end
pause
