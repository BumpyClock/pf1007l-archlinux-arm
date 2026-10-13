<#
.SYNOPSIS
Uploads and installs an immutable frame boot bundle through COM3.
.DESCRIPTION
The bundle must contain exactly four boot payloads and their SHA256SUMS file.
Selection requires both -Select and the matching -BuildId. This command never
reboots the frame and never replaces its shared root or persistent state image.
Use -ValidateOnly to check the local bundle without opening the serial port.
.EXAMPLE
./tools/pf-usb-install.ps1 -BundlePath ./bundle -ProfileId arch-usb-modules-r1 -Select -BuildId working-control-0123456789abcdef
#>
param(
    [Parameter(Mandatory)][string]$BundlePath,
    [Parameter(Mandatory)][ValidatePattern('^arch-usb-[a-z0-9][a-z0-9-]{0,39}\z')][string]$ProfileId,
    [switch]$Select,
    [string]$BuildId,
    [switch]$ValidateOnly,
    [string]$Port = 'COM3',
    [string]$ReceiptDirectory,
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'serial-credentials.ps1')
$limits = [ordered]@{
    'zImage' = 16777216
    'initramfs.cpio.gz' = 16777216
    'sun8i-a33-pf1007l-stage1.dtb' = 65536
    'boot-control.scr' = 16384
    'SHA256SUMS' = 1024
}
if ($Select -and $BuildId -cnotmatch '^working-control-[0-9a-f]{16}\z') {
    throw '-Select requires -BuildId working-control- followed by exactly 16 lowercase hexadecimal digits'
}
if (-not $Select -and $BuildId) { throw '-BuildId requires -Select' }
$bundle = Get-Item -LiteralPath $BundlePath
if (-not $bundle.PSIsContainer) { throw 'BundlePath must be a directory' }
for ($ancestor = $bundle; $null -ne $ancestor; $ancestor = $ancestor.Parent) {
    if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Bundle path contains a reparse point' }
}
$entries = @(Get-ChildItem -LiteralPath $bundle.FullName -Force)
if ($entries.Count -ne 5) { throw 'Bundle requires exactly four payloads and SHA256SUMS' }
$records = [ordered]@{}
foreach ($entry in $entries) {
    if (-not $limits.Contains($entry.Name) -or $entry.PSIsContainer -or
        ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected bundle entry' }
    if ($entry.Length -lt 1 -or $entry.Length -gt $limits[$entry.Name]) { throw ('Payload size differs: ' + $entry.Name) }
    $records[$entry.Name] = [ordered]@{
        size = $entry.Length
        sha256 = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifestBytes = [IO.File]::ReadAllBytes((Join-Path $bundle.FullName 'SHA256SUMS'))
if (@($manifestBytes | Where-Object { $_ -gt 127 -or $_ -eq 13 }).Count) { throw 'SHA256SUMS must be ASCII with LF line endings' }
$manifest = [Text.Encoding]::ASCII.GetString($manifestBytes)
$lines = $manifest.Split("`n")
if ($lines[-1] -eq '') { $lines = $lines[0..($lines.Count - 2)] }
$seen = @{}
if ($lines.Count -ne 4) { throw 'SHA256SUMS requires exactly four entries' }
foreach ($line in $lines) {
    if ($line -cnotmatch '^([0-9a-f]{64})  (zImage|initramfs\.cpio\.gz|sun8i-a33-pf1007l-stage1\.dtb|boot-control\.scr)$') {
        throw 'Invalid SHA256SUMS entry'
    }
    $hash = $Matches[1]
    $name = $Matches[2]
    if ($seen.ContainsKey($name)) { throw 'Duplicate SHA256SUMS entry' }
    if ($records[$name].sha256 -cne $hash) { throw ('Local checksum mismatch: ' + $name) }
    $seen[$name] = $true
}
$scriptBytes = [IO.File]::ReadAllBytes((Join-Path $bundle.FullName 'boot-control.scr'))
$scriptText = [Text.Encoding]::ASCII.GetString($scriptBytes)
$builds = [regex]::Matches($scriptText, '(?m)^setenv build (working-control-[0-9a-f]{16})\r?$')
if ($builds.Count -ne 1) { throw 'Launcher requires one valid build identifier' }
$embeddedBuild = $builds[0].Groups[1].Value
if ($Select -and $BuildId -cne $embeddedBuild) { throw 'BuildId differs from the bundle launcher' }
foreach ($name in @('zImage','initramfs.cpio.gz','sun8i-a33-pf1007l-stage1.dtb')) {
    if (-not $scriptText.Contains($ProfileId + '/' + $name)) { throw ('Launcher payload path differs: ' + $name) }
}
if ($ValidateOnly) {
    [ordered]@{ validated = $true; profile = $ProfileId; build = $embeddedBuild; selected = $false; serial_opened = $false } | ConvertTo-Json
    return
}
$Credential = Get-PfCredential -Credential $Credential
$token = [Guid]::NewGuid().ToString('N')
if (-not $ReceiptDirectory) {
    $ReceiptDirectory = Join-Path $PSScriptRoot ('receipts/install-' + $token)
}
$receiptDir = [IO.Path]::GetFullPath($ReceiptDirectory)
if (Test-Path -LiteralPath $receiptDir) { throw 'ReceiptDirectory must be new to preserve prior evidence' }
New-Item -ItemType Directory -Path $receiptDir | Out-Null
$remoteBundle = '/home/diag/pf-update/bundle-' + $token
$receipt = [ordered]@{
    started_utc = [DateTime]::UtcNow.ToString('o')
    profile = $ProfileId
    build = $embeddedBuild
    bundle = $bundle.FullName
    remote_bundle = $remoteBundle
    files = $records
    installed = $false
    selection_requested = [bool]$Select
    selected = $false
    rebooted = $false
}
try {
    $moves = @()
    foreach ($name in $limits.Keys) {
        $transferReceipt = Join-Path $receiptDir ($name + '.transfer.json')
        $null = & (Join-Path $PSScriptRoot 'pf-usb-transfer.ps1') -InputPath (Join-Path $bundle.FullName $name) `
            -ReceiptPath $transferReceipt -Port $Port -Credential $Credential -MaxBytes $limits[$name] -TransferTimeoutSeconds 120
        $transferred = Get-Content -Raw -LiteralPath $transferReceipt | ConvertFrom-Json
        if ($transferred.verified -ne $true -or $transferred.terminal_restored -ne $true -or
            $transferred.bytes -ne $records[$name].size -or $transferred.remote_sha256 -cne $records[$name].sha256 -or
            $transferred.remote_path -cnotmatch '^/home/diag/pf-update/transfer-[0-9a-f]{32}\.bin\z') {
            throw ('Transfer receipt differs: ' + $name)
        }
        # Remote paths are generated hexadecimal IDs; names come only from the fixed payload list.
        $moves += ('mv -T -- ' + $transferred.remote_path + ' ' + $remoteBundle + '/' + $name)
    }
    $command = '(set -e; umask 077; mkdir ' + $remoteBundle + '; ' + ($moves -join '; ') + '; ' +
        'pkexec --disable-internal-agent /usr/local/sbin/pf-maintenance install ' + $remoteBundle + ' ' + $ProfileId + '; ' +
        "printf '\nPF_USB_INSTALLED_$token\n'"
    if ($Select) {
        $command += '; pkexec --disable-internal-agent /usr/local/sbin/pf-maintenance select ' + $ProfileId + ' ' + $BuildId + '; ' +
            "printf '\nPF_USB_SELECTED_$token\n'"
    }
    $command += '); result=$?; printf ''\nPF_USB_RESULT_TOKEN %s\n'' "$result"'.Replace('TOKEN',$token)
    $commandsPath = Join-Path $receiptDir 'commands.txt'
    $transcriptPath = Join-Path $receiptDir 'console.txt'
    [IO.File]::WriteAllText($commandsPath, $command + "`n", [Text.Encoding]::ASCII)
    $null = & (Join-Path $PSScriptRoot 'capture-frame.ps1') -CommandsFile $commandsPath -OutputPath $transcriptPath -Port $Port -Credential $Credential
    $response = Get-Content -Raw -LiteralPath $transcriptPath
    $receipt.installed = [regex]::IsMatch($response, '(?m)^PF_USB_INSTALLED_' + $token + '\r?$')
    $receipt.selected = [regex]::IsMatch($response, '(?m)^PF_USB_SELECTED_' + $token + '\r?$')
    if (-not [regex]::IsMatch($response, '(?m)^PF_USB_RESULT_' + $token + ' 0\r?$') -or
        -not $receipt.installed -or ($Select -and -not $receipt.selected)) {
        throw 'Remote operation did not confirm success; inspect console.txt before retrying'
    }
} catch {
    $receipt.error = $_.Exception.Message
    throw
} finally {
    $receipt.completed_utc = [DateTime]::UtcNow.ToString('o')
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $receiptDir 'receipt.json')
}
$receipt | ConvertTo-Json -Depth 6
