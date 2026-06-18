@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found.
  echo Run setup_tts_attachment.bat first.
  pause
  exit /b 1
)

call .venv\Scripts\activate
python discord_tts_attachment.py
