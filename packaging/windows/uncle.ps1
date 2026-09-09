# Works with Scoop or an existing Git for Windows + python.org installation.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$gitRoot = $null
$pythonRoot = $null
$bash = $null
$python = $null
if (Get-Command scoop -ErrorAction SilentlyContinue) {
    try { $gitRoot = (& scoop prefix git 2>$null | Out-String).Trim() } catch { $gitRoot = $null }
    try { $pythonRoot = (& scoop prefix python 2>$null | Out-String).Trim() } catch { $pythonRoot = $null }
    if ($gitRoot) { $bash = Join-Path $gitRoot 'bin\bash.exe' }
    if ($pythonRoot) { $python = Join-Path $pythonRoot 'python.exe' }
}
if (!$bash -or !(Test-Path $bash)) {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $candidate = Split-Path (Split-Path $git.Source -Parent) -Parent
        if (Test-Path (Join-Path $candidate 'bin\bash.exe')) {
            $gitRoot = $candidate
            $bash = Join-Path $gitRoot 'bin\bash.exe'
        }
    }
}
$pythonCandidates = @($env:UNCLE_WINDOWS_PYTHON, $python)
foreach ($name in @('python.exe', 'python3.exe')) {
    $pythonCandidates += @(Get-Command $name -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
}
$python = $null
foreach ($candidate in $pythonCandidates) {
    if (!$candidate -or !(Test-Path $candidate) -or $candidate -match '[\\/]WindowsApps[\\/]') { continue }
    & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (!$bash -or !(Test-Path $bash) -or !$python) {
    throw 'Install Git for Windows and Python 3.9+ on PATH (or scoop install git python). Disable Microsoft Store Python aliases if they shadow Python.'
}
$pythonRoot = Split-Path $python -Parent
$oldPath = $env:PATH
$oldPython = $env:UNCLE_WINDOWS_PYTHON
$oldBash = $env:UNCLE_WINDOWS_BASH
try {
    $env:UNCLE_WINDOWS_PYTHON = $python
    $env:UNCLE_WINDOWS_BASH = $bash
    $env:PATH = "$PSScriptRoot;$gitRoot\usr\bin;$pythonRoot;$oldPath"
    & $bash --noprofile --norc ($root.Replace('\', '/') + '/uncle') @args
    $status = $LASTEXITCODE
} finally {
    $env:PATH = $oldPath
    $env:UNCLE_WINDOWS_PYTHON = $oldPython
    $env:UNCLE_WINDOWS_BASH = $oldBash
}
exit $status
