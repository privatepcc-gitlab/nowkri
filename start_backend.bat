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
  venv\Scripts\python.exe -m pip install --upgrade pip
)

rem --- install packages on first run, and again whenever requirements.txt changes ---
set REQHASH=
set OLDHASH=
for /f %%h in ('venv\Scripts\python.exe -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"') do set REQHASH=%%h
if exist venv\.req_hash set /p OLDHASH=<venv\.req_hash
rem an empty hash (command failed) always counts as "changed", so packages still get installed
set NEEDINSTALL=1
if not "%REQHASH%"=="" if "%REQHASH%"=="%OLDHASH%" set NEEDINSTALL=
if defined NEEDINSTALL (
  echo Installing packages, this takes a minute the first time...
  venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fail
  if not "%REQHASH%"=="" >venv\.req_hash echo %REQHASH%
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
