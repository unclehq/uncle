# Scoop exposes this script as `uncle` in PowerShell, cmd, and Git Bash.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$gitRoot = (& scoop prefix git | Out-String).Trim()
$pythonRoot = (& scoop prefix python | Out-String).Trim()
$bash = Join-Path $gitRoot 'bin\bash.exe'
$python = Join-Path $pythonRoot 'python.exe'
if (!(Test-Path $bash) -or !(Test-Path $python)) {
    throw 'Install Scoop dependencies: scoop install git python jq gh'
}
$oldPath = $env:PATH
$oldPython = $env:UNCLE_WINDOWS_PYTHON
try {
    $env:UNCLE_WINDOWS_PYTHON = $python
    $env:PATH = "$PSScriptRoot;$gitRoot\usr\bin;$pythonRoot;$oldPath"
    # Do not change directory: the user's cwd is the project root.
    & $bash --noprofile --norc ($root.Replace('\', '/') + '/uncle') @args
    $status = $LASTEXITCODE
} finally {
    $env:PATH = $oldPath
    $env:UNCLE_WINDOWS_PYTHON = $oldPython
}
exit $status
