@echo off
rem SAMPLE for presenting: opens the hiring sample in your browser. Close this window to stop it.
rem Set HIVE_PY to your Python 3.12 with the backend requirements, or create .venv here.
cd /d "%~dp0"
if defined HIVE_PY (set PY=%HIVE_PY%) else (set PY=.venv\Scripts\python.exe)
%PY% samples\hiring_viewer.py
pause
