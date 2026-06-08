@echo off
REM Clean up SSH key permissions
set KEY=C:\Users\marci\.ssh2\id_ed25519.new

echo Current permissions:
icacls %KEY%

echo.
echo Removing extra permissions...

REM Remove SYSTEM
icacls %KEY% /remove "NT AUTHORITY\SYSTEM" 2>nul

REM Remove Administrators  
icacls %KEY% /remove "BUILTIN\Administrators" 2>nul

REM Remove marci_x1qrp5l if exists
icacls %KEY% /remove "DESKTOP-97SIN4R\marci_x1qrp5l" 2>nul

REM Remove DESKTOP-97SIN4R\marci deny rule
icacls %KEY% /remove "DESKTOP-97SIN4R\marci" 2>nul

echo.
echo New permissions:
icacls %KEY%
