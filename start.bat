@echo off
rem Start riggbot from this folder, using the project's .venv if there is one.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    py main.py
)
pause
