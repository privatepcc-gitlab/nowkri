@echo off
title Job Hunt - backend
cd /d "%~dp0backend"

rem --- find Python (python or the py launcher) ---
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
  where python >nul 2>nul && set PY=python
)
if not defined PY (
  echo.
  echo [ERROR] Python is not installed or not on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup. Then run this again.
  echo.
  pause
  exit /b 1
)
%PY% --version

if not exist venv\Scripts\python.exe (
  echo Creating virtual environment...
  %PY% -m venv venv || goto :fail
  echo Installing packages, this takes a minute the first time...
  venv\Scripts\python.exe -m pip install --upgrade pip
  venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fail
)

echo.
echo Job Hunt is starting. Open http://127.0.0.1:8001  (API docs: /docs)
echo Keep this window open. Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
goto :end

:fail
echo.
echo [ERROR] Setup failed. Read the message above.
echo If it was a network error, check your internet and run this again.
echo To start fresh, delete the backend\venv folder.
:end
pause
