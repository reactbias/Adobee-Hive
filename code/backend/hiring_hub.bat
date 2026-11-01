@echo off
rem Starts a hub with the CV-based candidates, seeds them, and leaves it running. Then start the frontend
rem (documentation/HIRING.md). Set HIVE_PY to a Python 3.12 that has requirements.txt installed, or create .venv here.
cd /d "%~dp0"
if defined HIVE_PY (set PY=%HIVE_PY%) else (set PY=.venv\Scripts\python.exe)
set FOLDER_ROOT=%~dp0..\..\testdata\candidates
set ADMISSION_POLICY=open
set LLM_PROVIDER=offline
set DUCKDB_PATH=%~dp0data\hiring.duckdb
if exist "%DUCKDB_PATH%" del "%DUCKDB_PATH%"
start "Hive hub" %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 8 /nobreak >nul
%PY% tools\seed_vaults.py --vaults ..\..\testdata\candidates
echo.
echo The hub is on http://127.0.0.1:8000 with the candidates published. Close the "Hive hub" window to stop it.
pause
