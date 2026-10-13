function Get-PfCredential {
    param([System.Management.Automation.PSCredential]$Credential)
    if (-not $Credential) { $Credential = Get-Credential -UserName 'diag' -Message 'Enter the diag password you set on the frame.' }
    if (-not $Credential -or $Credential.UserName -cne 'diag') { throw 'USB update tools require the diag account' }
    return $Credential
}

function Get-PfPassword {
    param([Parameter(Mandatory)][System.Management.Automation.PSCredential]$Credential)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
    try {
        $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ([string]::IsNullOrEmpty($value) -or $value.Contains("`r") -or $value.Contains("`n")) { throw 'Invalid console password' }
        return $value
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}
