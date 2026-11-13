@echo off
cd /d "%~dp0"
echo Atidarau kelia telefonui is naujo. Jei isoks Windows langas, spausk Taip.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0leisti-telefona.ps1"
if errorlevel 1 (
  echo.
  echo Telefono kelias neatsidare. Be to lango telefonas sio kompiuterio neatidarys.
  echo.
)

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m rrr_agent langas
) else (
  python -m rrr_agent langas
)
if errorlevel 1 (
  echo.
  echo Nepavyko paleisti. Idiek Python is python.org ir pazymek "Add python.exe to PATH".
)
echo.
pause
