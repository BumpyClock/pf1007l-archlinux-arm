param(
    [Parameter(Mandatory)][string]$CommandsFile,
    [Parameter(Mandatory)][string]$OutputPath,
    [string]$Port = 'COM3',
    [System.Management.Automation.PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
$commands = @(Get-Content -LiteralPath $CommandsFile -ErrorAction Stop)
. (Join-Path $PSScriptRoot 'serial-credentials.ps1')
$serial = [System.IO.Ports.SerialPort]::new($Port,115200,'None',8,'One')
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 1500
$serial.DtrEnable = $true
$serial.Encoding = [Text.UTF8Encoding]::new($false)
$password = $null
$script:transcript = ''
$prompt = '\[diag@pf1007l-arch [^\r\n]*\]\$ '

function Receive-Until([string]$Pattern, [int]$Seconds) {
    $received = ''
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $part = $serial.ReadExisting()
        $received += $part
        $script:transcript += $part
        if ($received -match $Pattern) { return $received }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Timed out waiting for console response'
}

function Save-Transcript {
    $clean = $script:transcript
    if ($password) { $clean = $clean.Replace($password, '[REDACTED]') }
    $clean = [regex]::Replace($clean, '\x1b\][\s\S]*?(?:\x07|\x1b\\)', '')
    $clean = [regex]::Replace($clean, '\x1bP[\s\S]*?\x1b\\', '')
    $clean = [regex]::Replace($clean, '\x1b\[[0-?]*[ -/]*[@-~]|\x1b[78]', '')
    $parent = Split-Path -Parent $OutputPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $clean | Set-Content -LiteralPath $OutputPath
}

try {
    $serial.Open()
    $serial.Write("`n")
    $initial = Receive-Until ('login:|' + $prompt) 20
    Save-Transcript
    if ($initial -match 'login:') {
        $serial.Write("diag`n")
        $null = Receive-Until '[Pp]assword:' 10
        $Credential = Get-PfCredential -Credential $Credential
        $password = Get-PfPassword -Credential $Credential
        $serial.Write($password + "`n")
        $null = Receive-Until $prompt 20
    }
    foreach ($command in $commands) {
        if (-not $command.Trim()) { continue }
        $serial.Write($command + "`n")
        $null = Receive-Until $prompt 45
        Save-Transcript
    }
} finally {
    Save-Transcript
    Get-Content -Raw -LiteralPath $OutputPath | Write-Output
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $password = $null
    $credential = $null
}
