@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m rrr_agent langas
) else (
  python -m rrr_agent langas
)
if errorlevel 1 (
  echo.
  echo Nepavyko paleisti. Įdiek Python iš python.org ir diegimo metu pažymėk "Add python.exe to PATH".
)
echo.
pause
