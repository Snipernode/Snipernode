@echo off
setlocal
cd /d "%~dp0"

if exist "dist\discord_tts_attachment_neural_v6.exe" (
  start "" "dist\discord_tts_attachment_neural_v6.exe"
  exit /b 0
)

if exist "dist\discord_tts_attachment_neural_v5.exe" (
  start "" "dist\discord_tts_attachment_neural_v5.exe"
  exit /b 0
)

if exist "dist\discord_tts_attachment_neural_v4.exe" (
  start "" "dist\discord_tts_attachment_neural_v4.exe"
  exit /b 0
)

if exist "dist\discord_tts_attachment_neural_v2.exe" (
  start "" "dist\discord_tts_attachment_neural_v2.exe"
  exit /b 0
)

if exist "dist\discord_tts_attachment_neural.exe" (
  start "" "dist\discord_tts_attachment_neural.exe"
  exit /b 0
)

if exist "dist\discord_tts_attachment.exe" (
  start "" "dist\discord_tts_attachment.exe"
  exit /b 0
)

echo EXE not found at dist\discord_tts_attachment_neural_v6.exe, dist\discord_tts_attachment_neural_v5.exe, dist\discord_tts_attachment_neural_v4.exe, dist\discord_tts_attachment_neural_v2.exe, dist\discord_tts_attachment_neural.exe, or dist\discord_tts_attachment.exe
pause
exit /b 1
