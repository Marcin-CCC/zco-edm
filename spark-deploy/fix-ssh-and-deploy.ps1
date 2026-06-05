# Skrypt naprawiający uprawnienia SSH i wykonujący deploy na Spark
# NVIDIA Sync nadpisuje uprawnienia, więc musimy je naprawić przed SSH

$sshDir = "$env:USERPROFILE\.ssh"
$nvidiaSyncDir = "$env:USERPROFILE\AppData\Local\NVIDIA Corporation\Sync\config"

# Resetuj uprawnienia dla wszystkich plików SSH
Write-Host "Resetting SSH file permissions..." -ForegroundColor Cyan
icacls "$sshDir\*" /reset /t /c 2>&1 | Out-Null
icacls "$nvidiaSyncDir\*" /reset /c 2>&1 | Out-Null

# Ustaw bezpieczłe uprawnienia dla kluczy prywatnych
Write-Host "Setting secure permissions for private keys..." -ForegroundColor Cyan
icacls "$sshDir\id_ed25519" /grant:r "$env:USERPROFILE`(T:RR)"; 2>&1 | Out-Null
icacls "$sshDir\id_ed25519" /inheritance:r 2>&1 | Out-Null
icacls "$sshDir\id_ed25519" /grant "$env:USERNAME`:F" 2>&1 | Out-Null

# Deploy na Spark
Write-Host "Deploying to Spark..." -ForegroundColor Green
ssh -F "$sshDir\config" marcin@192.168.1.34 "cd /home/marcin/zco-edm-app && docker compose --profile spark pull && docker compose --profile spark up -d"