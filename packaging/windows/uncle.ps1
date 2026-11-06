# Works with Scoop or an existing Git for Windows + python.org installation.
$ErrorActionPreference = 'Stop'
# Run a native command quietly and return its exit code. Windows PowerShell 5.1
# turns any stderr output from a native command into a terminating error under
# $ErrorActionPreference = 'Stop' (even with 2>$null), so a Python that prints an
# ImportError traceback would abort the launcher. Probes must never do that.
function Invoke-Quiet {
    param([string]$Exe, [string[]]$Arguments)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Exe @Arguments *> $null; return $LASTEXITCODE }
    catch { return 1 }
    finally { $ErrorActionPreference = $saved }
}
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
$pythonCandidates = @($env:UNCLE_WINDOWS_PYTHON, (Join-Path $root 'venv\Scripts\python.exe'), $python)
foreach ($name in @('python.exe', 'python3.exe')) {
    $pythonCandidates += @(Get-Command $name -All -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
}
# Prefer an interpreter that can import curses: the full-screen UI needs it, and
# the first Python found is often a different install (a private venv, a Scoop
# Python) from the one the user installed windows-curses into. Fall back to the
# first usable Python so Uncle still starts with the line menu.
$python = $null
$fallback = $null
foreach ($candidate in $pythonCandidates) {
    if (!$candidate -or !(Test-Path $candidate) -or $candidate -match '[\\/]WindowsApps[\\/]') { continue }
    if ((Invoke-Quiet $candidate @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)')) -ne 0) { continue }
    if (!$fallback) { $fallback = $candidate }
    if ((Invoke-Quiet $candidate @('-c', 'import curses')) -eq 0) { $python = $candidate; break }
}
if (!$python) { $python = $fallback }
if (!$bash -or !(Test-Path $bash) -or !$python) {
    throw 'Install Git for Windows and Python 3.9+ on PATH (or scoop install git python). Disable Microsoft Store Python aliases if they shadow Python.'
}
# The full-screen UI needs curses, which Windows Python lacks. Repair it in the
# interpreter Uncle will actually run, once, so a Python chosen differently from
# the one the user ran pip with (or an install made before this was handled)
# still ends up with a working UI. Only Uncle's private venv is modified.
# When pip cannot supply it (typically a Python newer than any windows-curses
# wheel) say why, once per Python version, instead of retrying silently on every
# start and leaving only a bare "needs curses".
if ((Invoke-Quiet $python @('-c', 'import curses')) -ne 0 -and ($python -like (Join-Path $root 'venv\*'))) {
    $pyVersion = ((& $python -c 'import sys; print(sys.version.split()[0])' 2>$null) | Out-String).Trim()
    $marker = Join-Path $root 'venv\.windows-curses-unavailable'
    $known = (Test-Path -LiteralPath $marker) -and ((Get-Content -LiteralPath $marker -Raw -ErrorAction SilentlyContinue).Trim() -eq $pyVersion)
    if (!$known) {
        Write-Host 'uncle: installing windows-curses into its Python environment...'
        $saved = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $pipOutput = (& $python -m pip install --disable-pip-version-check windows-curses *>&1 | Out-String) } catch { $pipOutput = [string]$_ }
        finally { $ErrorActionPreference = $saved }
        if ((Invoke-Quiet $python @('-c', 'import curses')) -ne 0) {
            $tail = (($pipOutput -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 4) -join "`n  ")
            Write-Warning "windows-curses could not be installed for Python $pyVersion, so the full-screen UI is unavailable.`n  $tail`n  Install a Python that has a windows-curses wheel (3.9-3.13 at last check), then set UNCLE_WINDOWS_PYTHON to its python.exe."
            Set-Content -LiteralPath $marker -Value $pyVersion -Encoding ASCII
        }
    }
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
