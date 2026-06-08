$key = 'C:\Users\marci\.ssh2\id_ed25519.new'
$acl = Get-Acl $key
$acl.SetOwner((New-Object System.Security.Principal.NTAccount('marci')))
$accessRules = $acl.Access
foreach ($r in $accessRules) { 
    $acl.RemoveAccessRule($r) | Out-Null
}
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule('marci', 'FullControl', 'Allow')
$acl.AddAccessRule($rule)
$acl | Set-Acl
Write-Host 'Permissions set successfully'
icacls $key
