@echo off
cd /d "%~dp0"
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
