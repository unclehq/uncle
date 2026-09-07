# Hermetic native PowerShell tests. Real Scoop install smoke tests run in CI.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$work = Join-Path ([IO.Path]::GetTempPath()) ('uncle-test-' + [Guid]::NewGuid().ToString('N'))
$oldScoop = $env:SCOOP
$env:SCOOP = Join-Path $work 'scoop with spaces'
$global:UncleScoopTestFailure = 0
$global:UncleScoopTestCalls = @()
function scoop {
    $global:UncleScoopTestCalls += ($args -join ' ')
    $global:LASTEXITCODE = $global:UncleScoopTestFailure
    if ($global:UncleScoopTestFailure) { return }
    $current = Join-Path $env:SCOOP 'apps/uncle/current'
    New-Item -ItemType Directory -Force $current | Out-Null
    Set-Content (Join-Path $current 'install.json') '{"bucket":"uncle-github"}'
}
function Assert($condition, $message) { if (!$condition) { throw $message } }
function Invoke-RestMethod {
    param($Headers, $Uri)
    $global:UncleTestGitHubUri = $Uri
    return @{ sha = ('a' * 40); commit = @{ committer = @{ date = '2026-01-01T00:00:00Z' } } }
}
function Invoke-WebRequest {
    param([switch]$UseBasicParsing, $Uri, $OutFile)
    Copy-Item $global:UncleTestGitHubZip $OutFile
}
try {
    foreach ($path in @('install.ps1','packaging/windows/uncle.ps1')) {
        $tokens = $null; $errors = $null
        [Management.Automation.Language.Parser]::ParseFile((Join-Path $root $path), [ref]$tokens, [ref]$errors) | Out-Null
        Assert ($errors.Count -eq 0) "PowerShell parse error: $errors"
    }
    & (Join-Path $root 'install.ps1') -SourceDir $root -DryRun
    Assert ($global:UncleScoopTestCalls.Count -eq 0) 'Dry run invoked Scoop'
    & (Join-Path $root 'install.ps1') -SourceDir $root
    Assert ($global:UncleScoopTestCalls -contains 'install uncle-github/uncle') 'Missing Scoop install'
    $manifest = Get-Content (Join-Path $env:SCOOP 'buckets/uncle-github/bucket/uncle.json') -Raw | ConvertFrom-Json
    $archive = ([Uri]$manifest.url).LocalPath
    Assert (Test-Path $archive) 'Local archive disappeared after installation'
    Assert ($manifest.hash -eq (Get-FileHash $archive -Algorithm SHA256).Hash) 'Incorrect manifest hash'
    Assert ($manifest.extract_dir -eq 'uncle') 'Wrong extraction root'
    Assert ($manifest.depends -contains 'python') 'Missing Python dependency'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $names = $zip.Entries.FullName
        Assert (@($names | Where-Object { $_ -match '(^|/)\.uncle/' }).Count -eq 0) 'Packaged workflow state'
        Assert (@($names | Where-Object { $_ -match 'packaging/windows/uncle.ps1$' }).Count -eq 1) 'Launcher absent'
    } finally { $zip.Dispose() }
    & (Join-Path $root 'install.ps1') -SourceDir $root
    Assert ($global:UncleScoopTestCalls -contains 'update uncle --force') 'Reinstall did not update through Scoop'
    $githubRoot = Join-Path $work ('uncle-' + ('a' * 40))
    New-Item -ItemType Directory -Force (Join-Path $githubRoot 'packaging/windows') | Out-Null
    Copy-Item (Join-Path $root 'VERSION') $githubRoot
    Copy-Item (Join-Path $root 'packaging/windows/scoop.json') (Join-Path $githubRoot 'packaging/windows')
    $global:UncleTestGitHubZip = Join-Path $work 'github.zip'
    Compress-Archive $githubRoot $global:UncleTestGitHubZip
    & (Join-Path $root 'install.ps1') -Repo example/uncle -Ref feature/installer
    $manifest = Get-Content (Join-Path $env:SCOOP 'buckets/uncle-github/bucket/uncle.json') -Raw | ConvertFrom-Json
    Assert ($global:UncleTestGitHubUri.EndsWith('/commits/feature%2Finstaller')) 'Ref not encoded in GitHub request'
    Assert ($manifest.url -eq ('https://github.com/example/uncle/archive/' + ('a' * 40) + '.zip')) 'Archive not commit-pinned'
    Assert ($manifest.hash -eq (Get-FileHash $global:UncleTestGitHubZip -Algorithm SHA256).Hash) 'GitHub archive hash incorrect'
    $global:UncleScoopTestFailure = 31
    $failed = $false
    try { & (Join-Path $root 'install.ps1') -SourceDir $root } catch { $failed = $_.Exception.Message -match 'Scoop failed' }
    Assert $failed 'Scoop failure was ignored'
    $failed = $false
    try { & (Join-Path $root 'install.ps1') -Ref '../invalid' -DryRun } catch { $failed = $true }
    Assert $failed 'Invalid ref accepted'
    Write-Host 'install-windows-test: passed'
    $global:LASTEXITCODE = 0
} finally {
    $env:SCOOP = $oldScoop
    Remove-Item function:scoop
    Remove-Item function:Invoke-RestMethod, function:Invoke-WebRequest
    Remove-Variable UncleScoopTestFailure, UncleScoopTestCalls -Scope Global
    Remove-Variable UncleTestGitHubUri, UncleTestGitHubZip -Scope Global -ErrorAction SilentlyContinue
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
}
