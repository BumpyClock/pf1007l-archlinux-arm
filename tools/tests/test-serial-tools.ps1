$ErrorActionPreference = 'Stop'
$tools = Split-Path -Parent $PSScriptRoot
. (Join-Path $tools 'serial-credentials.ps1')
foreach ($file in Get-ChildItem -LiteralPath $tools -Filter '*.ps1') {
    $tokens = $null
    $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ('Parse failed: ' + $file.Name) }
    $source = Get-Content -Raw -LiteralPath $file.FullName
    if ($source -match 'serial-credential.json|Ubuntu-26.04|photoframe-arch-sd-work') { throw 'Private-machine dependency present' }
    if ($file.Name -in @('capture-frame.ps1', 'pf-usb-transfer.ps1') -and -not $source.Contains('$serial.Encoding = [Text.UTF8Encoding]::new($false)')) { throw 'Console login encoding must support UTF-8 passwords' }
}
$credential = New-Object Management.Automation.PSCredential('diag', (ConvertTo-SecureString 'synthetic-test-password' -AsPlainText -Force))
if ((Get-PfCredential -Credential $credential).UserName -cne 'diag') { throw 'Credential account mismatch' }
if ((Get-PfPassword -Credential $credential) -cne 'synthetic-test-password') { throw 'Secure credential decoding failed' }
$invalid = New-Object Management.Automation.PSCredential('root', $credential.Password)
$rejected = $false
try { $null = Get-PfCredential -Credential $invalid } catch { $rejected = $true }
if (-not $rejected) { throw 'Root account must be rejected' }
$invalid = New-Object Management.Automation.PSCredential('diag', (ConvertTo-SecureString "bad`nvalue" -AsPlainText -Force))
$rejected = $false
try { $null = Get-PfPassword -Credential $invalid } catch { $rejected = $true }
if (-not $rejected) { throw 'Multiline console password must be rejected' }
$missing = Join-Path $tools ('missing-' + [Guid]::NewGuid().ToString('N'))
$rejected = $false
try { $null = & (Join-Path $tools 'capture-frame.ps1') -CommandsFile $missing -OutputPath $missing -Port 'INVALID_TEST_PORT' -Credential $credential } catch { $rejected = $true }
if (-not $rejected) { throw 'Missing commands file must fail before serial access' }
$rejected = $false
try { $null = & (Join-Path $tools 'pf-usb-transfer.ps1') -InputPath $missing -ReceiptPath $missing -Port 'INVALID_TEST_PORT' -Credential $credential } catch { $rejected = $true }
if (-not $rejected) { throw 'Missing payload must fail before serial access' }
Write-Output 'PASS: parsers, portable credentials, account/password guards, pre-connect file validation'
