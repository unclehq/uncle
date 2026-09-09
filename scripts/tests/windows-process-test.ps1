$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Get-CimInstance {
    param($ClassName, $ErrorAction)
    @(
        @{ ProcessId=101; CommandLine='"C:\Program Files\Git\bin\bash.exe" "C:\work with spaces\stagegate.sh"' },
        @{ ProcessId=102; CommandLine='bash.exe --noprofile --norc C:/work/change-workflow.sh' },
        @{ ProcessId=103; CommandLine='code.exe C:\work\stagegate.sh' },
        @{ ProcessId=104; CommandLine='bash.exe -c "cat stagegate.sh"' },
        @{ ProcessId=105; CommandLine='bash.exe' }
    ) | ForEach-Object { [pscustomobject]$_ }
}
try {
    $ids = @(& (Join-Path $root 'scripts/lib/running-workflow.ps1'))
    if (($ids -join ',') -ne '101,102') { throw "Unexpected driver IDs: $ids" }
} finally { Remove-Item function:Get-CimInstance }
Write-Output 'windows-process-test: command lines, quoted paths, flags, and non-drivers passed'

# Exercise the checkout launcher using ordinary PATH tools even when Scoop is
# installed on the CI runner. No package manager lookup is allowed in this case.
function Get-Command {
    [CmdletBinding()]
    param([string]$Name, [switch]$All)
    if ($Name -eq 'scoop') { return }
    Microsoft.PowerShell.Core\Get-Command @PSBoundParameters
}
try {
    & (Join-Path $root 'packaging/windows/uncle.ps1') --help
    if ($LASTEXITCODE -ne 0) { throw 'Checkout launcher failed without Scoop' }
} finally { Remove-Item function:Get-Command }
Write-Output 'windows-process-test: checkout launcher without Scoop passed'
