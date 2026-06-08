# =====================================================
# EDM ZCO - Generate new SSH key and deploy
# =====================================================
# Runs in VS Code terminal - enter password when prompted
# =====================================================

$SPARK_IP = "192.168.1.34"
$SPARK_USER = "marcin"
$SPARK_PASSWORD = "ProGam123,,,"
$SSH_KEY_PATH = "C:\Users\marci\.ssh2\id_ed25519"
$KEY_COMMENT = "zco-edm-deploy"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  EDM ZCO - SSH Key Setup & Deploy" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Step 1: Check if existing key works after permission fix
Write-Host ""
Write-Host "[KROK 1] Testowanie obecnego klucza SSH..." -ForegroundColor Yellow
$testResult = ssh -o ConnectTimeout=5 -o BatchMode=yes "${SPARK_USER}@${SPARK_IP}" "echo 'SSH connection OK'" 2>&1
if ($testResult -match "SSH connection OK") {
    Write-Host "  Obecny klucz SSH działa!" -ForegroundColor Green
} else {
    Write-Host "  Obecny klucz nie działa. Generowanie nowego..." -ForegroundColor Yellow
}

# Step 2: Generate new SSH key (Tectia/SSH2 format)
Write-Host ""
Write-Host "[KROK 2] Generowanie nowego klucza SSH..." -ForegroundColor Yellow
$sshKeygenPath = "C:\Windows\System32\OpenSSH\ssh-keygen.exe"
if (Test-Path $sshKeygenPath) {
    # Use OpenSSH keygen
    & $sshKeygenPath -t ed25519 -f "${SSH_KEY_PATH}.new" -N "" -C $KEY_COMMENT
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Nowy klucz wygenerowany: ${SSH_KEY_PATH}.new" -ForegroundColor Green
        
        # Copy public key to Spark
        Write-Host "  Kopiowanie klucza publicznego na Sparka..." -ForegroundColor Yellow
        $pubKeyPath = "${SSH_KEY_PATH}.new.pub"
        if (Test-Path $pubKeyPath) {
            # We need to use scp with password - this will prompt
            Write-Host "  WPISZ HASŁO SSH GDY ZOSTANIESZ POPROSZONY!" -ForegroundColor Red
            Write-Host "  Copying public key to server..." -ForegroundColor Yellow
            scp -o StrictHostKeyChecking=no "$pubKeyPath" "${SPARK_USER}@${SPARK_IP}:/home/${SPARK_USER}/.ssh2/authorized_keys2"
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Public key copied successfully!" -ForegroundColor Green
                
                # Update SSH config to use new key
                Write-Host "  Aktualizacja SSH config..." -ForegroundColor Yellow
                $sshConfigPath = "C:\Users\marci\.ssh\config"
                if (Test-Path $sshConfigPath) {
                    $configContent = Get-Content $sshConfigPath
                    $newConfig = $configContent -replace 'IdentityFile ~/.ssh2/id_ed25519', 'IdentityFile ~/.ssh/${SSH_KEY_PATH}.new'
                    $newConfig | Set-Content $sshConfigPath
                    Write-Host "  SSH config updated!" -ForegroundColor Green
                }
                
                # Set proper permissions on new key
                Write-Host "  Ustawianie uprawnień..." -ForegroundColor Yellow
                $acl = Get-Acl "${SSH_KEY_PATH}.new"
                $acl.SetOwner((New-Object System.Security.Principal.NTAccount("marci")))
                foreach ($rule in $acl.Access) { $acl.RemoveAccessRule($rule) | Out-Null }
                $rule = New-Object System.Security.AccessControl.FileSystemAccessRule("marci", "FullControl", "Allow")
                $acl.AddAccessRule($rule)
                $acl | Set-Acl
                Write-Host "  Uprawnienia ustawione!" -ForegroundColor Green
                
                Write-Host ""
                Write-Host "============================================" -ForegroundColor Cyan
                Write-Host "  Nowy klucz wygenerowany i skonfigurowany!" -ForegroundColor Green
                Write-Host "  Uruchom: pwsh -File spark-deploy/deploy.ps1 all" -ForegroundColor Cyan
                Write-Host "============================================" -ForegroundColor Cyan
            } else {
                Write-Host "  FAILED to copy public key to server" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "  ssh-keygen not found at $sshKeygenPath" -ForegroundColor Red
    
    # Alternative: Use PowerShell to generate key
    Write-Host "  Spróbuję wygenerować klucz ręcznie..." -ForegroundColor Yellow
    Write-Host "  Otwórz PowerShell i wykonaj:" -ForegroundColor Yellow
    Write-Host "    ssh-keygen -t ed25519 -f ${SSH_KEY_PATH}.new -N '' -C ${KEY_COMMENT}" -ForegroundColor Cyan
}
