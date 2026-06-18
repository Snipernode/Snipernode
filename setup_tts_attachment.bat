@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Setup complete.
echo Run launch_tts_attachment.bat to start.
pause
