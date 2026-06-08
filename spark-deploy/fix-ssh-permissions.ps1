# Fix SSH key permissions for Tectia/SSH2 format key
$keyPath = "C:\Users\marci\.ssh2\id_ed25519"

# Remove all existing ACL entries
$acl = Get-Acl $keyPath
$acl.SetAccessProtectionRule([System.Security.AccessControl.AccessControlType]::Deny, "DESKTOP-97SIN4R\marci_x1qrp5l", [System.Security.AccessControl.FileSystemRights]::FullControl, [System.Security.AccessControl.InheritanceFlags]::None, [System.Security.AccessControl.PropagationFlags]::None)
$acl.SetAccessRuleProtection($true, $false)  # Disable inheritance

# Remove all access rules
foreach ($rule in $acl.Access) {
    $acl.RemoveAccessRule($rule) | Out-Null
}

# Add exclusive access for 'marci' user
$identity = New-Object System.Security.Principal.NTAccount("marci")
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, "FullControl", "Allow")
$acl.SetAccessRule($rule)

# Set owner to marci
$acl.SetOwner($identity)

# Apply the new ACL
$acl | Set-Acl

Write-Host "Permissions fixed for: $keyPath"

# Verify
icacls $keyPath
