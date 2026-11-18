@echo off
rem One-click start: runs the backend, which also serves the app.
rem No Node.js needed. Opens http://127.0.0.1:8001 in your browser.
cd /d "%~dp0"
start "Job Hunt" cmd /k "%~dp0start_backend.bat"
echo Starting Job Hunt... the first run installs packages and can take a few minutes.
echo Your browser will open in 15 seconds. If it shows an error, wait until the
echo "Job Hunt" window says "Application startup complete", then refresh.
timeout /t 15 >nul
start "" http://127.0.0.1:8001
