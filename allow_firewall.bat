@echo off
REM Opens IntraMeet's ports in Windows Firewall on ALL network profiles.
REM Needed because Windows marks a hotspot without internet as a "Public" network
REM and blocks incoming connections there. Run once on the SERVER PC as Administrator.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="IntraMeet TCP" >nul 2>&1
netsh advfirewall firewall delete rule name="IntraMeet UDP" >nul 2>&1
netsh advfirewall firewall add rule name="IntraMeet TCP" dir=in action=allow protocol=TCP localport=12345,12346,12349,12350 profile=any
netsh advfirewall firewall add rule name="IntraMeet UDP" dir=in action=allow protocol=UDP localport=12347,12348,12351 profile=any

echo.
echo IntraMeet firewall rules added. Clients can now connect over Wi-Fi / hotspot.
pause
