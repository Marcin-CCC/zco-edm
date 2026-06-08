@echo off
REM =====================================================
REM EDM ZCO - Deploy to Spark (with SSH setup)
REM =====================================================
REM This script:
REM 1. Copies the SSH key to standard location
REM 2. Fixes permissions
REM 3. Restores SSH config with NVIDIA include
REM 4. Runs deploy
REM =====================================================

echo ============================================
echo   EDM ZCO - Deploy to Spark (with SSH setup)
echo ============================================

REM Step 1: Copy SSH key to standard location
echo.
echo [1/5] Copying SSH key to standard location...
copy /Y "spark-deploy\id_ed25519.spark" "C:\Users\marci\.ssh\id_ed25519"
echo Done.

REM Step 2: Remove deny rule for marci_x1qrp5l
echo.
echo [2/5] Fixing SSH key permissions...
icacls "C:\Users\marci\.ssh\id_ed25519" /remove "DESKTOP-97SIN4R\marci_x1qrp5l" 2>nul
echo Permissions fixed.

REM Step 3: Restore SSH config with NVIDIA include (needed for Sync)
echo.
echo [3/5] Restoring SSH config...
(
echo Include "C:\Users\marci\AppData\Local\NVIDIA Corporation\Sync\config\ssh_config"
echo # Custom SSH config for Spark and GitHub
echo.
echo Host spark
echo   HostName 192.168.1.34
echo   User marcin
echo   IdentityFile C:/Users/marci/.ssh/id_ed25519
echo   IdentitiesOnly yes
echo   AddKeysToAgent yes
echo.
echo Host github.com
echo   HostName github.com
echo   User git
echo   IdentityFile C:/Users/marci/.ssh/id_ed25519
echo   IdentitiesOnly yes
) > "C:\Users\marci\.ssh\config.tmp"

REM Append NVIDIA include content
findstr /V "^Host " "C:\Users\marci\AppData\Local\NVIDIA Corporation\Sync\config\ssh_config" >> "C:\Users\marci\.ssh\config.tmp" 2>nul

move /Y "C:\Users\marci\.ssh\config.tmp" "C:\Users\marci\.ssh\config"
echo SSH config restored.

REM Step 4: Test SSH connection
echo.
echo [4/5] Testing SSH connection...
REM Use ssh with password from sshpass or interactive mode
ssh -o BatchMode=no -o ConnectTimeout=5 marcin@192.168.1.34 "echo SSH_TEST_OK" >nul 2>&1
if %errorlevel% equ 0 (
    echo SSH connection successful!
) else (
    echo SSH connection requires password. Running deploy in interactive mode...
)

REM Step 5: Run the deploy script
echo.
echo [5/5] Running deploy...
echo.
echo !!! WPISZ HASŁO SSH GDY ZOSTANIESZ POPROSZONY !!!
echo.
pwsh -File spark-deploy/deploy.ps1 all

echo.
echo ============================================
echo   Deploy finished!
echo ============================================
