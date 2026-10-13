<#
.SYNOPSIS
Copies a file over the frame's USB console into the diag account's staging directory.
.DESCRIPTION
Uses a length-framed binary transfer, restores the terminal, and verifies the
remote SHA256 before reporting success. Does not install files or change boot state.
The default limit is the 64 KiB smoke test; larger transfers require -MaxBytes.
#>
param(
    [Parameter(Mandatory)][string]$InputPath,
    [Parameter(Mandatory)][string]$ReceiptPath,
    [string]$Port = 'COM3',
    [ValidateRange(1,268435456)][long]$MaxBytes = 65536,
    [ValidateRange(10,1800)][int]$TransferTimeoutSeconds = 60,
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'serial-credentials.ps1')
$inputFile = Get-Item -LiteralPath $InputPath
if ($inputFile.PSIsContainer -or $inputFile.Length -lt 1 -or $inputFile.Length -gt $MaxBytes) {
    throw 'Input must be a nonempty file within MaxBytes'
}
$bytes = [IO.File]::ReadAllBytes($inputFile.FullName)
$sha = [Security.Cryptography.SHA256]::Create()
try { $expectedHash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant() }
finally { $sha.Dispose() }
$token = [Guid]::NewGuid().ToString('N')
$remotePath = '/home/diag/pf-update/transfer-' + $token + '.bin'
$serial = [IO.Ports.SerialPort]::new($Port,115200,'None',8,'One')
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 5000
$serial.DtrEnable = $true
$serial.Encoding = [Text.UTF8Encoding]::new($false)
$password = $null
$prompt = '\[diag@pf1007l-arch [^\r\n]*\]\$ '
$rawStarted = $false
$restored = $false
$timer = [Diagnostics.Stopwatch]::new()
$receipt = [ordered]@{
    started_utc = [DateTime]::UtcNow.ToString('o')
    port = $Port
    local_path = $inputFile.FullName
    remote_path = $remotePath
    bytes = $bytes.Length
    expected_sha256 = $expectedHash
    verified = $false
    terminal_restored = $false
    bytes_submitted = 0
}

function Set-TransferPhase([string]$Phase) {
    $receipt.phase = $Phase
    $receipt.phase_utc = [DateTime]::UtcNow.ToString('o')
    $parent = Split-Path -Parent $ReceiptPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath $ReceiptPath
}

function Receive-Until([string]$Pattern, [int]$Seconds) {
    $received = ''
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $received += $serial.ReadExisting()
        if ($received -match $Pattern) { return $received }
        if ($received.Length -gt 65536) { throw 'Unexpected excessive console output' }
        Start-Sleep -Milliseconds 20
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Timed out waiting for console response'
}

try {
    Set-TransferPhase 'opening-console'
    $serial.Open()
    $serial.Write("`n")
    $initial = Receive-Until ('login:|' + $prompt) 20
    if ($initial -match 'login:') {
        $serial.Write("diag`n")
        $null = Receive-Until '[Pp]assword:' 10
        $Credential = Get-PfCredential -Credential $Credential
        $password = Get-PfPassword -Credential $Credential
        $serial.Write($password + "`n")
        $null = Receive-Until $prompt 20
    }
    Set-TransferPhase 'preparing-receiver'
    # Only generated hexadecimal identifiers and bounded numbers enter the shell command.
    $command = @'
(set -eu; test "$(id -un)" = diag; test "$HOME" = /home/diag; command -v timeout >/dev/null; command -v sha256sum >/dev/null; umask 077; mkdir -p /home/diag/pf-update; test ! -L /home/diag/pf-update; test -O /home/diag/pf-update; saved=$(stty -g); complete=0; trap 'if test "$complete" = 0; then timeout --foreground 2 cat < /dev/tty > /dev/null || :; fi; stty "$saved"; printf "\nPF_RESTORED_TOKEN\n"' EXIT; trap 'exit 130' INT TERM HUP; set -C; exec 3>REMOTE; stty raw -echo -ixon -ixoff; printf '\nPF_READY_TOKEN\n'; timeout --foreground TIMEOUT head -c LENGTH < /dev/tty >&3; exec 3>&-; count=$(wc -c < REMOTE); test "$count" = LENGTH; hash=$(sha256sum REMOTE); hash=${hash%% *}; complete=1; stty "$saved"; printf '\nPF_DONE_TOKEN %s %s\n' "$count" "$hash")
'@
    $command = $command.Replace('TOKEN',$token).Replace('REMOTE',$remotePath).Replace('TIMEOUT',[string]$TransferTimeoutSeconds).Replace('LENGTH',[string]$bytes.Length)
    $serial.Write($command + "`n")
    $rawStarted = $true
    $null = Receive-Until ('(?m)^PF_READY_' + $token + '\r?$') 15
    Set-TransferPhase 'sending-payload'
    $timer.Start()
    for ($offset = 0; $offset -lt $bytes.Length; $offset += 4096) {
        if ($timer.Elapsed.TotalSeconds -ge $TransferTimeoutSeconds - 5) { throw 'Transfer deadline reached' }
        $serial.Write($bytes, $offset, [Math]::Min(4096,$bytes.Length-$offset))
        $receipt.bytes_submitted = $offset + [Math]::Min(4096,$bytes.Length-$offset)
        if ($receipt.bytes_submitted % 8192 -eq 0) { [Threading.Thread]::Sleep(1) }
    }
    Set-TransferPhase 'draining-host-buffer'
    while ($serial.BytesToWrite -gt 0) {
        if ($timer.Elapsed.TotalSeconds -ge $TransferTimeoutSeconds - 5) { throw 'Host serial buffer did not drain' }
        [Threading.Thread]::Sleep(1)
    }
    Set-TransferPhase 'waiting-for-remote-verification'
    $response = Receive-Until ('(?m)^PF_RESTORED_' + $token + '\r?$') $TransferTimeoutSeconds
    $timer.Stop()
    $restored = $true
    $receipt.terminal_restored = $true
    $match = [regex]::Match($response, '(?m)^PF_DONE_' + $token + ' ([0-9]+) ([0-9a-f]{64})\r?$')
    if (-not $match.Success) { throw 'Remote transfer did not complete' }
    $receipt.remote_sha256 = $match.Groups[2].Value
    if ([long]$match.Groups[1].Value -ne $bytes.Length -or $receipt.remote_sha256 -ne $expectedHash) {
        throw 'Remote byte count or SHA256 mismatch'
    }
    $receipt.verified = $true
    $receipt.elapsed_seconds = [Math]::Round($timer.Elapsed.TotalSeconds,3)
    $receipt.bytes_per_second = [Math]::Round($bytes.Length/$timer.Elapsed.TotalSeconds)
    $serial.Write("`n")
    $null = Receive-Until $prompt 10
    Set-TransferPhase 'complete'
} catch {
    if ($serial.IsOpen) { $serial.DiscardOutBuffer() }
    $receipt.error = $_.Exception.Message
    throw
} finally {
    # Raw mode ignores Ctrl-C. Let the remote head timeout restore its saved state.
    if ($rawStarted -and -not $restored -and $serial.IsOpen) {
        try {
            $null = Receive-Until ('(?m)^PF_RESTORED_' + $token + '\r?$') ($TransferTimeoutSeconds + 5)
            $receipt.terminal_restored = $true
        } catch { $receipt.terminal_restore_error = $_.Exception.Message }
    }
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $password = $null
    $credential = $null
    $receipt.completed_utc = [DateTime]::UtcNow.ToString('o')
    $parent = Split-Path -Parent $ReceiptPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath $ReceiptPath
}
$receipt | ConvertTo-Json
