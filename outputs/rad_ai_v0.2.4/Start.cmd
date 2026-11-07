@echo off
cd /d "%~dp0"
"%USERPROFILE%\Desktop\sohbet_alpha\.venv\Scripts\python.exe" main.py
if errorlevel 1 pause
