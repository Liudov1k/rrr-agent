@echo off
cd /d "%~dp0"
if "%~1"=="elevated" goto addrule

netsh advfirewall firewall show rule name="RRR forma" >nul 2>&1
if errorlevel 1 (
  echo Telefono kelias uzdarytas. Patvirtink Windows langa, kad telefonas galetu prisijungti.
  echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\rrr-leisti.vbs"
  echo UAC.ShellExecute "cmd.exe", "/c ""%~f0"" elevated", "", "runas", 1 >> "%temp%\rrr-leisti.vbs"
  cscript //nologo "%temp%\rrr-leisti.vbs"
  del "%temp%\rrr-leisti.vbs" >nul 2>&1
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
exit /b

:addrule
netsh advfirewall firewall add rule name="RRR forma" dir=in action=allow protocol=TCP localport=8765 remoteip=localsubnet profile=any
exit /b 0
