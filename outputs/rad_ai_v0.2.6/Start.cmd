@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else (
  "..\..\.venv\Scripts\python.exe" main.py
)
if errorlevel 1 pause
