@echo off
REM =====================================================
REM EDM ZCO - Deploy to Spark (CMD wrapper)
REM =====================================================
REM Uruchomi deploy z terminala VS Code — wpiszesz hasło SSH interaktywnie.
REM =====================================================

echo ============================================
echo   EDM ZCO - Deploy to Spark
echo   Uruchomienie przez PowerShell...
echo ============================================

REM Napraw uprawnienia klucza SSH
echo.
echo [KROK 1] Naprawianie uprawnień klucza SSH...
powershell -Command "^
$acl = Get-Acl 'C:\\Users\\marci\\.ssh2\\id_ed25519'; ^
$acl.SetOwner((New-Object System.Security.Principal.NTAccount('marci'))); ^
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule('marci', 'FullControl', 'Allow'); ^
$acl.SetAccessRule($rule); ^
$acl | Set-Acl; ^
Write-Host '  Uprawnienia naprawione.'
"

echo.
echo [KROK 2] Weryfikacja uprawnień...
icacls "C:\Users\marci\.ssh2\id_ed25519"

echo.
echo [KROK 3] Rozpoczynanie deploy...
echo.
echo !!! WPISZ HASŁO SSH GDY ZOSTANIESZ POPROSZONY !!!
echo.
powershell -File spark-deploy/deploy.ps1 all

echo.
echo ============================================
echo   Deploy zakonczony!
echo ============================================
